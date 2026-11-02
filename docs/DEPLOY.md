# Deploying to Azure

Every merge to `main` runs CI, publishes the API image, deploys to **staging**, and
then waits for your approval before the same image goes to **production**.

```
merge to main ──> CI (api, docker, web) ──> image to GitHub Container Registry
              ──> staging: Bicep ─> migrations ─> smoke test ─> web app
              ──> [you click Approve] ──> production: same steps, same image
```

## What runs where

| Piece | Azure service | Notes |
|---|---|---|
| API | Container Apps (one per environment) | Scales to zero when idle. Free monthly grant covers this size |
| Migrations | Container Apps Job, run by the pipeline on every deploy | `alembic upgrade head`, seed, exchange rates |
| Exchange rates | Container Apps Job on a daily schedule (19:00 UTC) | `fx-refresh 7` |
| Web app | Static Web Apps, Free plan (one per environment) | East Asia region: the closest one Static Web Apps offers |
| Database | PostgreSQL Flexible Server, Burstable B1ms, 32 GB | One server, two databases: `finance_stg`, `finance_prod` |
| Secrets | Key Vault | The database URL; the apps read it with a managed identity |
| Monitoring | Application Insights + Log Analytics (30 days) | Requests, errors, dependencies, logs |
| Sign-in | Entra External ID | Already set up |
| Images | GitHub Container Registry | Free for public images |

All infrastructure is code: `infra/shared.bicep` (shared pieces) and `infra/app.bicep`
(one environment). Deleting the resource group removes everything.

---

## One-time setup

### 1. Budget alert (do this first)

portal.azure.com > **Cost Management > Budgets > Add**: your subscription, AUD 10 a
month, email alerts at 50% and 100%.

### 2. Azure: run the bootstrap script in Cloud Shell

1. In portal.azure.com, check the top right shows your personal account and
   **Default Directory** (not Finance Copilot).
2. Open **Cloud Shell** (the `>_` icon in the top bar), choose **Bash**. If asked about
   storage, choose **No storage account required**.
3. **Manage files > Upload** and pick `infra/bootstrap.sh` from your laptop.
4. Run:
   ```bash
   bash bootstrap.sh
   ```
   Answer `y` when it shows your subscription. It prints four values at the end.

### 3. GitHub: environments

Repo **Settings > Environments > New environment**:
- `staging`: no rules.
- `production`: tick **Required reviewers**, add yourself (`Nidhi313`). Leave
  **Prevent self-review** unticked, so you can approve your own deploys.

### 4. GitHub: variables and the one secret

Repo **Settings > Secrets and variables > Actions**.

**Variables** tab, **New repository variable** for each:

| Name | Value |
|---|---|
| `AZURE_CLIENT_ID` | from the bootstrap output |
| `AZURE_TENANT_ID` | from the bootstrap output (your Default Directory) |
| `AZURE_SUBSCRIPTION_ID` | from the bootstrap output |
| `AZURE_RESOURCE_GROUP` | `rg-finance-copilot-app` |
| `ENTRA_TENANT_SUBDOMAIN` | `financecopilotbuddy` |
| `ENTRA_TENANT_ID` | the **Finance Copilot** tenant id (`623d72c3-…`) |
| `ENTRA_API_CLIENT_ID` | `finance-copilot-api` client id |
| `ENTRA_WEB_CLIENT_ID` | `finance-copilot-web` client id |
| `ADMIN_EMAILS` | `["you@example.com"]` (the email you sign in with) |

Two different tenant ids, on purpose: `AZURE_TENANT_ID` is where your subscription
lives (for deploying); `ENTRA_TENANT_ID` is the external tenant your users sign in to.

**Secrets** tab, **New repository secret**:

| Name | Value |
|---|---|
| `POSTGRES_ADMIN_PASSWORD` | Generate one in Git Bash: `echo "Fc1-$(openssl rand -hex 16)"` |

Don't save that password anywhere else; the pipeline puts it in Key Vault.

---

## First deploy

1. Merge the pull request that adds this file. The **Deploy** workflow starts
   (Actions tab). The first run takes 15 to 20 minutes, mostly creating Postgres.
2. **It will stop at the staging Bicep step the first time**, because GitHub makes
   new container images private and Azure can't pull them. Fix once:
   GitHub profile > **Packages** > `finance-copilot-api` > **Package settings** >
   **Change visibility** > **Public**. Then in the failed run click
   **Re-run failed jobs**.
3. When staging finishes, the run summary shows the **Web** and **API** URLs.
4. Add both web URLs (staging now, production after step 5) as sign-in redirect URIs:
   Entra admin center, switch to the **Finance Copilot** tenant >
   **App registrations > finance-copilot-web > Authentication > Add Redirect URI**
   (Single-page application). Use the exact `https://….azurestaticapps.net` URL,
   no trailing slash.
5. The run waits at **production**. Click **Review deployments > Approve**.
6. Open the production web URL, sign up, and check the getting-started checklist.

After that, every merge to `main` deploys to staging automatically and waits for your
approval for production.

---

## Costs

- Container Apps, Static Web Apps (Free), Entra External ID: $0 at this size.
- Key Vault: a few cents a month.
- Application Insights / Log Analytics: inside the free monthly allowance at this size.
- **PostgreSQL B1ms is the one real cost.** The Azure free account has covered this
  size for 12 months; the portal shows the server's price under
  **psql-fincop-… > Overview**. Check it after the first deploy, and watch the budget alert.
- Remove everything: `az group delete -n rg-finance-copilot-app` (cannot be undone).

## Before real personal data goes in

Planned hardening, in order:
1. Private networking: Container Apps environment and Postgres in a virtual network,
   public access off.
2. Managed identity sign-in to Postgres instead of a password.
3. Service Bus queue for CSV imports.
4. Alerts on error rate and latency in Application Insights.
5. Custom domain.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing GitHub settings: …` | Add the named variable or secret (step 4) and re-run |
| `AADSTS700213` / `No matching federated identity record` at Azure sign-in | The environment name must be exactly `staging` or `production`, and the repo name in `bootstrap.sh` must match (`Nidhi313/finance-copilot`) |
| `AuthorizationFailed` creating a role assignment | Re-run `bootstrap.sh`; the Role Based Access Control Administrator assignment is missing |
| Staging Bicep fails with an image pull error | Make the GHCR package public (First deploy, step 2) |
| Postgres `LocationIsOfferRestricted` or quota error | The free account can't create that size in Australia East right now. Ask and we'll switch region |
| Key Vault secret not accessible on the very first run | Role assignments take a minute to apply. Re-run failed jobs |
| Sign-in fails on the deployed site with a redirect URI error | Add that exact site URL to `finance-copilot-web` (First deploy, step 4) |
| Site loads but API calls fail with CORS errors | The API allows only its own environment's web URL. Check the run used the right environment |
| First request after a quiet spell is slow | Scale to zero: a replica takes a few seconds to start. Expected |
