# Country packs

Every country in `countries.json` (all ISO countries) has **basic support**:
accounts in its currency, transactions, budgets, net worth, transfers, the
general calculators and CSV import through the column mapper.

A **country pack** adds local detail: account types, bank CSV presets, calculator
names, category rules, compliance text, and later market data and lessons. Packs
are data, validated against `api/app/countries/pack_schema.py`.

The files here (`AU.json`, `IN.json`) seed a fresh database. After that, packs are
managed through the admin API with no code change and no deploy:

1. `POST /v1/admin/country-packs` with `{"country_code": "NZ", "content": {...}}`
   creates a draft version. Drafts change nothing.
2. Review it (`GET /v1/admin/country-packs?country=NZ`).
3. `POST /v1/admin/country-packs/{id}/activate` makes it live. The previous
   version is retired, not deleted.

Every pack must pass the shared suite in `api/tests/test_country_packs.py`.

CSV presets start with `"verified": false`. Set it to `true` only after testing
against a real export from that bank.
