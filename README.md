# Finance Copilot

One app for people whose money lives in more than one country: track accounts and
spending, plan with calculators, and see what transfers home really cost.
Australia and India have local detail at launch; every other country works with
basic support, and new countries are added as data, not code.

The app shows people their own data, simulates decisions and explains how money
works. It never recommends a product, stock, fund or trade.

**Status:** Release 1 (Track and Plan) running locally, with sign-in through
Microsoft Entra External ID. Azure deployment and the remaining releases are next.

## What's here

| Feature | Where |
|---|---|
| Any number of countries per person, with your relationship to each | Settings |
| Country switcher that changes every screen | Top bar |
| Accounts in any currency, net worth across all countries in one currency | Accounts, Overview |
| Transactions, auto-categorised by your rules then the country's defaults | Transactions |
| CSV import: bank presets, or a column mapper for any bank; re-importing never duplicates | Transactions > Import |
| Monthly budgets per country | Budgets |
| Remittance log: fee plus the margin hidden in the exchange rate | Money sent home |
| Savings goals, linked to an account or tracked by hand | Goals |
| Calculators: regular investing (SIP / dollar-cost averaging), compound growth, loan (EMI), emergency fund | Calculators |
| Export all your data, delete your account | Settings |
| Sign-in (Entra External ID); each person sees only their own data | Sign-in page |
| Getting-started checklist that ticks off from your own data | Overview |

## Stack

FastAPI, SQLAlchemy, Alembic, PostgreSQL · React with Vite and TypeScript · typed API
client generated from the OpenAPI spec (`packages/api-client`, shared with a future
mobile app) · Docker Compose locally · GitHub Actions CI (lint, tests against real
Postgres, migration check, Docker build and boot, web typecheck/test/build).
Exchange rates from [Frankfurter](https://frankfurter.dev), stored against USD.

## Run it locally

You need Docker Desktop, Node.js 20+ and Git.

```bash
# 1. Database and API (migrates, seeds countries and packs, fetches a year of exchange rates)
docker compose up --build
#    API docs: http://localhost:8000/docs

# 2. Optional: sample data for the demo user (in a second terminal)
docker compose exec api python -m app.cli demo-data

# 3. Web app (third terminal)
npm install
npm run dev
#    http://localhost:5173
```

Sample statements to try the import with are in `samples/`.

### Sign-in

By default the app runs without sign-in as one local demo user (`AUTH_MODE=dev`).
To sign in for real with Microsoft Entra External ID, copy `api/.env.example` to
`api/.env` and `web/.env.example` to `web/.env.local`, fill in the tenant values,
set both modes to `entra`, and restart `docker compose up` and `npm run dev`.
The API checks every token's signature, issuer, audience, expiry and scope, and
creates each person's account on first sign-in. Setup steps are in the build guide. A full walkthrough, including what each phase built, is in [docs/BUILD_GUIDE.md](docs/BUILD_GUIDE.md).

### Tests

```bash
docker compose up -d db            # tests use a separate finance_test database, created automatically
cd api
python -m venv .venv
source .venv/Scripts/activate      # Git Bash on Windows; macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
ruff check app tests

cd .. && npm test && npm run typecheck
```

### After changing the API

```bash
cd api && python -m app.openapi > ../packages/api-client/openapi.json && cd ..
npm run gen:api
```

### After changing a model

```bash
cd api
alembic revision --autogenerate -m "what changed"   # review the file it writes
alembic upgrade head
```

### Jobs

```bash
python -m app.cli seed               # countries, categories, launch country packs (safe to repeat)
python -m app.cli fx-refresh 7       # exchange rates for the last 7 days
python -m app.cli demo-data          # sample data for the demo user
```

## How it's built

```
api/                 FastAPI backend
  app/countries/     country context: basic support plus the active country pack
  app/calculators/   pure, parameter-driven calculators
  app/providers/     data source plugins (FX today, market data later)
  app/services/      CSV parsing, categorisation, reports, FX conversion
  app/routers/       REST endpoints under /v1
  alembic/           migrations
  tests/             pytest against real Postgres
country-packs/       all countries + seed packs for AU and India (see its README)
packages/api-client/ typed TypeScript client generated from OpenAPI
web/                 React app
samples/             CSV files for trying the import
```

Rules the code keeps:

- No `if country == ...` anywhere. Country behaviour comes from data.
- Money is an exact decimal plus a currency code, sent over the API as a string.
- Exchange rates are stored against USD; any pair is calculated from two lookups.
- Calculations live in the backend, so every client gets the same numbers.

## Not done yet

- **Azure deployment** (Container Apps, Postgres, Key Vault, Service Bus, Bicep,
  deploy pipeline).
- **CSV imports run inside the request** (5 MB limit). They move to a queue on Azure.
- **Bank presets are unverified** until tested against real exports.
- **Retirement explainers**, waiting on figures checked against official sources.
- Practise (market overview, paper trading) and Learn are Releases 2 and 3.
