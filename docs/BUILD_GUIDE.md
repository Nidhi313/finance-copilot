# Build guide: Release 1

How to get the app running on your Windows machine, push it to GitHub, and
understand what each phase built. Read the phase notes before interviews: every
design choice here is something you should be able to explain.

---

## 1. One-time setup (Windows, Git Bash)

| Tool | Check | If missing |
|---|---|---|
| Docker Desktop (WSL 2 backend) | `docker --version` and `docker compose version` | Install from docker.com, restart, start Docker Desktop |
| Node.js 20 or 22 LTS | `node --version` | Install the LTS build from nodejs.org |
| Python 3.11.9 | `python --version` | Already set up with pyenv-win |
| Git | `git --version` | Already set up |

Port check: the app uses **5432** (Postgres), **8000** (API) and **5173** (web).
If you already run Postgres locally, stop it or change the left-hand port in
`docker-compose.yml` (for example `"5433:5432"`) and in the test URL.

---

## 2. Run it

From the unzipped `finance-copilot` folder:

```bash
# Terminal 1: database + API
docker compose up --build
```

Wait for `Uvicorn running on http://0.0.0.0:8000`. On the first start it also
prints `{'countries': 248, 'packs_seeded': ['AU', 'IN']}` and the number of
exchange rates stored. Open http://localhost:8000/docs to see every endpoint.

```bash
# Terminal 2: sample data (optional, recommended for a first look)
docker compose exec api python -m app.cli demo-data

# Terminal 2: web app
npm install
npm run dev
```

Open http://localhost:5173.

Try this path through the app:
1. Overview: net worth across Australia and India, this month's spending, budgets.
2. Switch to India in the top bar. Every screen changes to India's context.
3. Transactions > Import a statement: pick the CommBank preset and
   `samples/commbank_sample.csv`. Import it twice; the second time nothing is duplicated.
4. Import `samples/other_bank_sample.csv` with "My bank isn't listed": click the
   header row, map the columns, save the format.
5. Calculators: the same calculator is "SIP" in India mode and "Dollar-cost
   averaging" in Australia mode, with each country's disclaimer.
6. Settings: add New Zealand. It works straight away with basic support.

Without demo data you start at onboarding instead, which is also worth seeing once.
To reset everything: `docker compose down -v` (deletes the database volume).

---

## 3. Push to GitHub

Create an empty repo called `finance-copilot` on github.com (no README, no
licence). Then, inside the folder:

```bash
git remote add origin https://github.com/Nidhi313/finance-copilot.git
git push -u origin main
```

The repo already has three commits authored as you. The push starts the CI run
in the Actions tab: lint, migration check, 50 API tests on a real Postgres,
Docker build and boot, and the web typecheck, tests and build. All of it passed
here except the Docker job, which needs Docker and will run for the first time
on GitHub. If it fails, send me the log.

---

## 4. Run the tests yourself

```bash
docker compose up -d db
cd api
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements-dev.txt
pytest                 # 50 tests
ruff check app tests
cd ..
npm test               # web tests
npm run typecheck
```

---

## 5. What each phase built

### Phase 0: skeleton and pipeline
`docker-compose.yml`, `api/Dockerfile`, `.github/workflows/ci.yml`, `api/app/config.py`, `api/app/db.py`

- Settings come from environment variables (`pydantic-settings`), so the same
  image runs locally and on Azure with different config.
- Dependencies are pinned (`requirements.txt`) and split from dev tools
  (`requirements-dev.txt`), so the production image stays small.
- CI runs tests against a real Postgres service container, and checks that the
  migrations match the models (`alembic check`).
- The Docker image runs as a non-root user and has a health check.

**Interview angle:** "CI catches a model change without a migration before it merges."

### Phase 1: data model and country packs
`api/app/models.py`, `api/alembic/versions/0001_initial_schema.py`, `api/app/countries/`, `country-packs/`, `api/app/routers/admin.py`

- All 248 countries are seeded with currency and locale (basic support).
- A country pack is a JSON document validated by `pack_schema.py`, stored
  versioned in `country_packs`. Draft, then activate; the old version is retired.
  A partial unique index guarantees one active pack per country.
- `CountryContext` is the only place that knows about countries. The rest of the
  code asks it for account types, CSV presets, labels and disclaimers.
- `user_country_links` is many-to-many with a relationship list per link.

**Interview angle:** "Adding a country is a data operation through an admin API,
not a deploy. The test suite runs the same checks against every pack."

### Phase 2: Track API
`api/app/routers/`, `api/app/services/csv_import.py`, `categorise.py`, `reports.py`, `fx.py`

- Money is `Numeric(19,4)` plus a currency code, sent as a decimal string in JSON.
- CSV import is preview, then import. Each row gets a hash of date, amount,
  description and its occurrence number in the file, and Postgres
  `ON CONFLICT DO NOTHING` skips rows already imported. Two identical coffees on
  the same day stay two rows.
- Categorisation: your rules first (by priority), then the country pack's rules,
  longest pattern first.
- Exchange rates are stored per USD, so any pair is two lookups. Missing rates
  are reported, never guessed.
- Remittance cost = what you paid minus what arrived was worth at the market rate.
- Every row is scoped to its owner; another user's id returns 404, not 403.

**Interview angle:** "Idempotent imports, exact decimal money, and a remittance
cost model that separates the visible fee from the rate margin."

### Phase 3: Plan calculators and FX job
`api/app/calculators/engine.py`, `api/app/providers/fx.py`, `api/app/services/fx_ingest.py`, `api/app/cli.py`

- Calculators are pure functions with tests against known values (EMI of
  100,000 at 12% over 12 months is 8,884.88).
- The country changes only the label, currency and disclaimer, never the maths.
- FX providers are plugins behind one interface. Ingestion is a job
  (`python -m app.cli fx-refresh`), never inside a user request.

### Phase 4: web app
`web/src/`, `packages/api-client/`

- The TypeScript client is generated from FastAPI's OpenAPI spec, so a
  backend change that breaks the frontend fails `npm run typecheck`.
- TanStack Query handles fetching and caching; the country switcher updates the
  profile and every screen refetches for the new country.
- Money is formatted with the country's locale (India shows 2,50,000).
- All calculation happens in the API, so a mobile app will show identical numbers.

---

## 6. Known gaps (planned)

- Sign-in is a local demo user. The API refuses that mode outside local and test.
- No Azure yet: Bicep, Container Apps, Postgres, Key Vault, Service Bus, deploy pipeline.
- CSV import runs in the request (5 MB cap); it moves to a queue on Azure.
- Bank presets are marked unverified until tested against real exports.
- Retirement explainers wait for figures checked against official sources.

---

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| `port is already allocated` | Something else uses 5432/8000; stop it or change the port in `docker-compose.yml` |
| "Cannot reach the API" in the browser | Check terminal 1; open http://localhost:8000/ready |
| `FX refresh failed` at startup | No internet or the provider is down; the app runs, net worth shows "not included yet". Retry with `docker compose exec api python -m app.cli fx-refresh 400` |
| API code changes don't reload | Restart with `docker compose restart api` |
| Tests can't connect | `docker compose up -d db` first |
