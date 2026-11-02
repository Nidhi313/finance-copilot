// Resources shared by staging and production. Deployed into one resource group.
//   az deployment group create -g <rg> -f infra/shared.bicep -p postgresAdminPassword=...
//
// Cost notes (see docs/DEPLOY.md): Container Apps scale to zero and run inside the
// free monthly grant; Postgres is Burstable B1ms with 32 GB, the smallest size and the
// one the Azure free account has covered; Log Analytics keeps 30 days.

@description('Azure region for everything except the Static Web Apps.')
param location string = resourceGroup().location

@description('Admin login for the Postgres server.')
param postgresAdminLogin string = 'fincopadmin'

@secure()
@description('Admin password for the Postgres server. Kept in GitHub secrets and Key Vault only.')
param postgresAdminPassword string

var suffix = uniqueString(resourceGroup().id)
var names = {
  logs: 'log-fincop-${suffix}'
  insights: 'appi-fincop-${suffix}'
  containerEnv: 'cae-fincop-${suffix}'
  identity: 'id-fincop-${suffix}'
  keyVault: 'kv-fincop-${take(suffix, 10)}'
  postgres: 'psql-fincop-${suffix}'
}
var tags = { app: 'finance-copilot' }

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: names.logs
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: names.insights
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: names.containerEnv
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

// The apps read their secrets from Key Vault with this identity. No passwords in app settings.
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: names.identity
  location: location
  tags: tags
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: names.keyVault
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

var keyVaultSecretsUser = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4633458b-17de-408a-b874-0445c86b69e6'
)

resource identityCanReadSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, identity.id, keyVaultSecretsUser)
  scope: keyVault
  properties: {
    roleDefinitionId: keyVaultSecretsUser
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: names.postgres
  location: location
  tags: tags
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    storage: { storageSizeGB: 32, autoGrow: 'Disabled' }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: { publicNetworkAccess: 'Enabled' }
    authConfig: { passwordAuth: 'Enabled', activeDirectoryAuth: 'Disabled' }
  }
}

// Lets Azure services (the Container Apps) reach the server. Connections still need the
// password and TLS. Moving to private networking is listed in docs/DEPLOY.md as the next
// hardening step before real personal data goes in.
resource allowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

output containerEnvName string = containerEnv.name
output identityName string = identity.name
output keyVaultName string = keyVault.name
output postgresName string = postgres.name
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output insightsName string = insights.name
