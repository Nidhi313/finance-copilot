#!/usr/bin/env bash
# One-time Azure setup for the deploy pipeline. Run it in Azure Cloud Shell (Bash),
# signed in to your Default Directory (the one with your subscription), NOT the
# Finance Copilot external tenant.
#
#   bash bootstrap.sh
#
# It creates:
#   - the resource group the app is deployed into
#   - an app registration GitHub Actions signs in as, trusted only for this repo's
#     "staging" and "production" environments (OIDC: no passwords or keys)
#   - two role assignments for it, limited to that resource group
# Safe to run again: it reuses anything that already exists.
set -euo pipefail

GITHUB_REPO="${GITHUB_REPO:-Nidhi313/finance-copilot}"
RG="${RG:-rg-finance-copilot-app}"
LOCATION="${LOCATION:-australiaeast}"
APP_NAME="${APP_NAME:-finance-copilot-github-deploy}"

SUB_ID=$(az account show --query id -o tsv)
SUB_NAME=$(az account show --query name -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
echo "Subscription: $SUB_NAME ($SUB_ID)"
echo "Directory:    $TENANT_ID"
read -r -p "Is this your personal subscription and Default Directory? [y/N] " ok
[[ "$ok" =~ ^[Yy]$ ]] || { echo "Switch with: az account set --subscription <id>"; exit 1; }

echo "Registering resource providers (first time takes a few minutes)..."
for ns in Microsoft.App Microsoft.OperationalInsights Microsoft.Insights Microsoft.DBforPostgreSQL \
          Microsoft.Web Microsoft.KeyVault Microsoft.ManagedIdentity; do
  az provider register --namespace "$ns" -o none
done

echo "Resource group $RG in $LOCATION..."
az group create -n "$RG" -l "$LOCATION" --tags app=finance-copilot -o none
SCOPE=$(az group show -n "$RG" --query id -o tsv)

APP_ID=$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv)
if [ -z "$APP_ID" ]; then
  echo "Creating app registration $APP_NAME..."
  APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
fi
az ad sp show --id "$APP_ID" -o none 2>/dev/null || az ad sp create --id "$APP_ID" -o none

for env in staging production; do
  name="github-$env"
  if ! az ad app federated-credential list --id "$APP_ID" --query "[?name=='$name'].name" -o tsv | grep -q .; then
    echo "Trusting GitHub environment '$env'..."
    az ad app federated-credential create --id "$APP_ID" -o none --parameters "{
      \"name\": \"$name\",
      \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"repo:$GITHUB_REPO:environment:$env\",
      \"audiences\": [\"api://AzureADTokenExchange\"]
    }"
  fi
done

# Contributor to create resources; RBAC Administrator so Bicep can let the app's
# managed identity read Key Vault secrets. Both only on this resource group.
for role in "Contributor" "Role Based Access Control Administrator"; do
  az role assignment create --assignee "$APP_ID" --role "$role" --scope "$SCOPE" -o none 2>/dev/null || true
done

cat <<OUT

Done. Add these as GitHub repository VARIABLES
(Settings > Secrets and variables > Actions > Variables):

  AZURE_CLIENT_ID        $APP_ID
  AZURE_TENANT_ID        $TENANT_ID
  AZURE_SUBSCRIPTION_ID  $SUB_ID
  AZURE_RESOURCE_GROUP   $RG

Then follow docs/DEPLOY.md for the remaining variables and the Postgres password secret.
OUT
