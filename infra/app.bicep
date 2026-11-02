// One environment (staging or production) of the app, on top of shared.bicep.
//   az deployment group create -g <rg> -f infra/app.bicep -p environmentName=staging apiImage=... ...

@allowed(['staging', 'production'])
param environmentName string

@description('Full image reference, for example ghcr.io/nidhi313/finance-copilot-api:<git sha>.')
param apiImage string

param location string = resourceGroup().location

@description('Static Web Apps run in a limited set of regions; East Asia is the closest to Australia.')
param webLocation string = 'eastasia'

param postgresAdminLogin string = 'fincopadmin'

@secure()
param postgresAdminPassword string

// Entra External ID (sign-in). None of these are secrets.
param entraTenantSubdomain string
param entraTenantId string
param entraApiClientId string

@description('JSON list of emails allowed to manage country packs, for example ["you@example.com"].')
param adminEmails string = '[]'

var suffix = uniqueString(resourceGroup().id)
var short = environmentName == 'production' ? 'prod' : 'stg'
var tags = { app: 'finance-copilot', environment: environmentName }
var databaseName = 'finance_${short}'

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: 'cae-fincop-${suffix}'
}
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: 'id-fincop-${suffix}'
}
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: 'kv-fincop-${take(suffix, 10)}'
}
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' existing = {
  name: 'psql-fincop-${suffix}'
}
resource insights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: 'appi-fincop-${suffix}'
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: databaseName
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

var databaseUrl = 'postgresql+psycopg://${postgresAdminLogin}:${uriComponent(postgresAdminPassword)}@${postgres.properties.fullyQualifiedDomainName}:5432/${databaseName}?sslmode=require'

resource databaseUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'database-url-${short}'
  properties: { value: databaseUrl }
}

resource web 'Microsoft.Web/staticSites@2023-12-01' = {
  name: 'swa-fincop-${short}-${suffix}'
  location: webLocation
  tags: tags
  sku: { name: 'Free', tier: 'Free' }
  properties: {}
}

var webOrigin = 'https://${web.properties.defaultHostname}'

var secrets = [
  {
    name: 'database-url'
    keyVaultUrl: '${keyVault.properties.vaultUri}secrets/${databaseUrlSecret.name}'
    identity: identity.id
  }
  { name: 'appinsights-connection', value: insights.properties.ConnectionString }
]

var env = [
  { name: 'ENVIRONMENT', value: environmentName }
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection' }
  { name: 'OTEL_SERVICE_NAME', value: 'finance-copilot-api-${short}' }
  { name: 'AUTH_MODE', value: 'entra' }
  { name: 'ENTRA_TENANT_SUBDOMAIN', value: entraTenantSubdomain }
  { name: 'ENTRA_TENANT_ID', value: entraTenantId }
  { name: 'ENTRA_API_CLIENT_ID', value: entraApiClientId }
  { name: 'ADMIN_EMAILS', value: adminEmails }
  { name: 'CORS_ORIGINS', value: '["${webOrigin}"]' }
]

var userIdentity = {
  type: 'UserAssigned'
  userAssignedIdentities: { '${identity.id}': {} }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-fincop-api-${short}'
  location: location
  tags: tags
  identity: userIdentity
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      secrets: secrets
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        // CORS is handled by the API itself (CORS_ORIGINS), so there is one source of truth.
      }
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: env
          probes: [
            { type: 'Liveness', httpGet: { path: '/health', port: 8000 }, periodSeconds: 30 }
            { type: 'Readiness', httpGet: { path: '/ready', port: 8000 }, periodSeconds: 10, failureThreshold: 6 }
          ]
        }
      ]
      // Scale to zero when idle so it costs nothing; the first request after a quiet
      // spell takes a few seconds while a replica starts.
      scale: {
        minReplicas: 0
        maxReplicas: 2
        rules: [{ name: 'http', http: { metadata: { concurrentRequests: '50' } } }]
      }
    }
  }
}

// Run on every deploy, before traffic needs the new schema.
resource migrateJob 'Microsoft.App/jobs@2024-03-01' = {
  name: 'job-fincop-migrate-${short}'
  location: location
  tags: tags
  identity: userIdentity
  properties: {
    environmentId: containerEnv.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 900
      replicaRetryLimit: 1
      manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
      secrets: secrets
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: apiImage
          command: ['sh', '-c', 'alembic upgrade head && python -m app.cli seed && (python -m app.cli fx-refresh 400 || echo "FX refresh skipped")']
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: env
        }
      ]
    }
  }
}

// Daily exchange rates. 19:00 UTC is early morning in Sydney, after the
// reference rates for the previous day are published.
resource fxJob 'Microsoft.App/jobs@2024-03-01' = {
  name: 'job-fincop-fx-${short}'
  location: location
  tags: tags
  identity: userIdentity
  properties: {
    environmentId: containerEnv.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 300
      replicaRetryLimit: 2
      scheduleTriggerConfig: { cronExpression: '0 19 * * *', parallelism: 1, replicaCompletionCount: 1 }
      secrets: secrets
    }
    template: {
      containers: [
        {
          name: 'fx'
          image: apiImage
          command: ['python', '-m', 'app.cli', 'fx-refresh', '7']
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: env
        }
      ]
    }
  }
}

output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output webUrl string = webOrigin
output webName string = web.name
output migrateJobName string = migrateJob.name
