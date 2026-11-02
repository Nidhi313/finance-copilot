import io
import json
import zipfile
from datetime import date, timedelta
from decimal import Decimal as D

TODAY = date.today()


def link(client, code, rel=("lives_here",)):
    r = client.put(f"/v1/me/countries/{code}", json={"relationships": list(rel)})
    assert r.status_code == 200, r.text
    return r.json()


def account(client, country, name="Everyday", type_="bank", opening="0", **extra):
    r = client.post(
        "/v1/accounts", json={"country_code": country, "name": name, "type": type_, "opening_balance": opening, **extra}
    )
    assert r.status_code == 201, r.text
    return r.json()


def category_id(client, name):
    return next(c["id"] for c in client.get("/v1/categories").json() if c["name"] == name)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}


def test_every_country_is_available_and_packs_are_marked(client):
    countries = {c["code"]: c for c in client.get("/v1/countries").json()}
    assert len(countries) > 240
    assert countries["AU"]["has_pack"] and countries["IN"]["has_pack"]
    assert not countries["NZ"]["has_pack"]


def test_country_context_basic_vs_pack(client):
    au = client.get("/v1/countries/AU").json()
    nz = client.get("/v1/countries/nz").json()
    assert au["fy_start"] == {"month": 7, "day": 1}
    assert "super" in {t["key"] for t in au["account_types"]}
    assert au["calculator_labels"]["regular_investing"] == "Dollar-cost averaging"
    assert nz["currency"] == "NZD" and nz["has_pack"] is False
    assert nz["fy_start"] == {"month": 1, "day": 1}
    assert client.get("/v1/countries/XX").status_code == 422


def test_user_can_belong_to_many_countries(client):
    link(client, "AU", ["tax_resident", "lives_here"])
    link(client, "IN", ["citizen", "holds_accounts"])
    me = link(client, "AE", ["sends_money_to"])
    assert [c["country_code"] for c in me["countries"]] == ["AU", "IN", "AE"]
    assert me["active_country_code"] == "AU"
    me = client.patch("/v1/me", json={"active_country_code": "IN", "home_currency": "INR"}).json()
    assert me["active_country_code"] == "IN" and me["home_currency"] == "INR"
    assert client.patch("/v1/me", json={"active_country_code": "JP"}).status_code == 422


def test_accounts_validate_types_against_country(client):
    account(client, "AU", "Super", "super")
    account(client, "NZ", "Kiwi savings", "savings")  # basic support, no pack
    r = client.post("/v1/accounts", json={"country_code": "NZ", "name": "x", "type": "super"})
    assert r.status_code == 422
    accs = client.get("/v1/accounts").json()
    assert {a["currency"] for a in accs} == {"AUD", "NZD"}
    # creating an account links the country automatically
    assert {c["country_code"] for c in client.get("/v1/me").json()["countries"]} == {"AU", "NZ"}


def test_transactions_balance_and_auto_category(client):
    acc = account(client, "AU", opening="1000")
    r = client.post(
        "/v1/transactions",
        json={"account_id": acc["id"], "date": str(TODAY), "description": "WOOLWORTHS METRO", "amount": "-85.40"},
    )
    assert r.status_code == 201
    assert r.json()["category_id"] == category_id(client, "Groceries")
    assert r.json()["currency"] == "AUD"
    assert D(client.get(f"/v1/accounts/{acc['id']}").json()["balance"]) == D("914.60")
    page = client.get("/v1/transactions", params={"country": "AU", "search": "woolworths"}).json()
    assert page["total"] == 1


def test_users_cannot_see_others_rows(client, db):
    from app.models import Account, User

    other = User(email="someone@else", home_currency="AUD")
    db.add(other)
    db.flush()
    acc = Account(user_id=other.id, country_code="AU", name="Theirs", type="bank", currency="AUD")
    db.add(acc)
    db.commit()
    assert client.get(f"/v1/accounts/{acc.id}").status_code == 404
    r = client.post(
        "/v1/transactions", json={"account_id": str(acc.id), "date": str(TODAY), "description": "x", "amount": "1"}
    )
    assert r.status_code == 404


def test_csv_import_preview_then_import_is_idempotent(client):
    acc = account(client, "AU")
    csv_bytes = (
        b'28/10/2026,"-85.40","WOOLWORTHS 1234","+914.60"\n27/10/2026,"-12.00","UBER EATS","+1000.00"\nbad,row\n'
    )
    files = {"file": ("cba.csv", csv_bytes, "text/csv")}
    form = {"account_id": acc["id"], "preset_id": "commbank_transactions"}
    preview = client.post("/v1/imports/preview", data=form, files=files).json()
    assert preview["parsed"] == 2 and len(preview["errors"]) == 1
    assert preview["rows"][1]["category_id"] == category_id(client, "Eating out")
    assert client.get("/v1/transactions").json()["total"] == 0  # preview saves nothing

    first = client.post("/v1/imports", data=form, files=files).json()["import"]
    assert first["rows_imported"] == 2 and first["rows_failed"] == 1
    again = client.post("/v1/imports", data=form, files=files).json()["import"]
    assert again["rows_imported"] == 0 and again["rows_duplicate"] == 2
    assert client.get("/v1/transactions").json()["total"] == 2


def test_csv_import_with_own_mapping_for_any_bank(client):
    acc = account(client, "NZ")
    mapping = {
        "has_header": True,
        "date_column": "When",
        "date_format": "%Y-%m-%d",
        "description_columns": ["Payee", "Memo"],
        "amount_column": "Amount",
    }
    csv_bytes = b"When,Payee,Memo,Amount\n2026-10-01,Countdown,groceries,-55.10\n"
    r = client.post(
        "/v1/imports",
        files={"file": ("kiwibank.csv", csv_bytes)},
        data={"account_id": acc["id"], "mapping": json.dumps(mapping), "save_mapping_as": "Kiwibank"},
    )
    assert r.status_code == 201, r.text
    saved = client.get("/v1/csv-mappings").json()
    assert saved[0]["name"] == "Kiwibank"
    r = client.post(
        "/v1/imports/preview",
        files={"file": ("k.csv", csv_bytes)},
        data={"account_id": acc["id"], "saved_mapping_id": saved[0]["id"]},
    )
    assert r.json()["rows"][0]["description"] == "Countdown groceries"


def test_csv_import_rejects_unknown_preset_and_two_mappings(client):
    acc = account(client, "NZ")
    files = {"file": ("x.csv", b"a\n")}
    r = client.post("/v1/imports/preview", files=files, data={"account_id": acc["id"], "preset_id": "hdfc_statement"})
    assert r.status_code == 422  # HDFC preset belongs to India, not NZ
    r = client.post(
        "/v1/imports/preview", files=files, data={"account_id": acc["id"], "preset_id": "x", "mapping": "{}"}
    )
    assert r.status_code == 422


def test_net_worth_across_countries_flags_missing_rates(client, add_rates):
    add_rates(TODAY, AUD="1.5", INR="84")
    account(client, "AU", opening="1500")
    account(client, "IN", opening="84000")
    account(client, "NZ", opening="100")  # no NZD rate stored
    nw = client.get("/v1/reports/net-worth", params={"currency": "USD"}).json()
    assert D(nw["total"]) == D("2000.00")
    assert D(nw["by_country"]["AU"]) == D("1000.00") and D(nw["by_country"]["IN"]) == D("1000.00")
    assert nw["missing_rates"] == ["NZD"]
    aud = client.get("/v1/reports/net-worth", params={"currency": "AUD"}).json()
    assert D(aud["total"]) == D("3000.00")


def test_budgets_and_spending(client, add_rates):
    add_rates(TODAY, AUD="1.5")
    acc = account(client, "AU")
    groceries = category_id(client, "Groceries")
    for amt in ("-100", "-50.50"):
        client.post(
            "/v1/transactions",
            json={"account_id": acc["id"], "date": str(TODAY), "description": "Coles", "amount": amt},
        )
    client.post(
        "/v1/transactions",
        json={"account_id": acc["id"], "date": str(TODAY), "description": "Salary", "amount": "3000"},
    )
    r = client.put("/v1/budgets", json={"country_code": "AU", "category_id": groceries, "amount": "400"})
    assert r.status_code == 200 and r.json()["currency"] == "AUD"
    status = client.get("/v1/budgets/status", params={"country": "AU"}).json()
    assert D(status[0]["spent"]) == D("150.50") and D(status[0]["remaining"]) == D("249.50")
    spending = client.get("/v1/reports/spending", params={"country": "AU"}).json()
    assert spending["by_category"][0]["category"] == "Groceries"
    assert D(spending["spending"]) == D("150.50") and D(spending["income"]) == D("3000.00")
    income = category_id(client, "Income")
    assert (
        client.put("/v1/budgets", json={"country_code": "AU", "category_id": income, "amount": "1"}).status_code == 422
    )


def test_remittance_shows_true_cost(client, add_rates):
    day = TODAY - timedelta(days=3)
    add_rates(day, AUD="1.5", INR="84")  # market: 1 AUD = 56 INR
    r = client.post(
        "/v1/remittances",
        json={
            "date": str(day),
            "from_country_code": "AU",
            "to_country_code": "IN",
            "amount_sent": "1010",
            "fee": "10",
            "amount_received": "55000",
            "provider": "BankX",
        },
    ).json()
    assert r["from_currency"] == "AUD" and r["to_currency"] == "INR"
    assert D(r["market_rate"]) == D("56.0000")
    # 55000 INR is worth 982.14 AUD at market, so the transfer cost 27.86, of which 10 was the fee
    assert D(r["total_cost"]) == D("27.86")
    assert D(r["rate_margin_cost"]) == D("17.86")
    summary = client.get("/v1/remittances/summary", params={"currency": "AUD"}).json()
    assert D(summary["total_cost"]) == D("27.86") and summary["cost_by_provider"]["BankX"]


def test_remittance_without_market_rate_still_saves(client):
    r = client.post(
        "/v1/remittances",
        json={
            "date": "2020-01-01",
            "from_country_code": "AU",
            "to_country_code": "IN",
            "amount_sent": "100",
            "amount_received": "5000",
        },
    )
    assert r.status_code == 201 and r.json()["total_cost"] is None


def test_goal_progress_from_linked_account(client, add_rates):
    add_rates(TODAY, AUD="1.5", INR="84")
    acc = account(client, "AU", "Savings", "savings", opening="3000")
    target_date = date(TODAY.year + 1, TODAY.month, 1)
    g = client.post(
        "/v1/goals",
        json={
            "name": "Trip home",
            "target_amount": "4000",
            "currency": "AUD",
            "target_date": str(target_date),
            "account_id": acc["id"],
        },
    ).json()
    assert D(g["current"]) == D("3000.00") and D(g["percent"]) == D("75.0")
    assert D(g["monthly_needed"]) > 0


def test_calculators_use_country_labels_and_disclaimers(client):
    body = {"monthly_amount": "500", "annual_return_pct": "8", "years": 10}
    au = client.post("/v1/calculators/regular-investing", json={**body, "country_code": "AU"}).json()
    ind = client.post("/v1/calculators/regular-investing", json={**body, "country_code": "IN"}).json()
    nz = client.post("/v1/calculators/regular-investing", json={**body, "country_code": "NZ"}).json()
    assert au["label"] == "Dollar-cost averaging" and ind["label"].startswith("SIP")
    assert nz["label"] == "Regular investing" and nz["currency"] == "NZD"
    assert au["result"] == ind["result"]  # same maths everywhere
    assert "SEBI" in ind["disclaimer"] and "not financial advice" in nz["disclaimer"]


def test_emergency_fund_uses_own_data(client, add_rates):
    first_of_month = TODAY.replace(day=1)
    for back in range(1, 4):
        add_rates(first_of_month - timedelta(days=1 + 31 * (back - 1)), AUD="1.5")
    add_rates(TODAY, AUD="1.5")
    acc = account(client, "AU", "Everyday")
    account(client, "AU", "Rainy day", "savings", opening="6000")
    for back in range(1, 4):
        d = first_of_month - timedelta(days=1 + 31 * (back - 1))
        client.post(
            "/v1/transactions",
            json={"account_id": acc["id"], "date": str(d.replace(day=10)), "description": "Rent", "amount": "-2000"},
        )
    r = client.post("/v1/calculators/emergency-fund", json={"country_code": "AU", "months_target": 6}).json()
    assert D(r["result"]["monthly_expenses_used"]) == D("2000.00")
    assert D(r["result"]["months_covered"]) == D("3.0")


def test_admin_adds_a_country_pack_as_data_with_no_code_change(client):
    assert client.get("/v1/countries/NZ").json()["has_pack"] is False
    content = {
        "schema_version": 1,
        "fy_start": {"month": 4, "day": 1},
        "account_types": [{"key": "kiwisaver", "label": "KiwiSaver"}],
        "calculator_labels": {"regular_investing": "Regular investing"},
        "category_rules": [{"pattern": "countdown", "category": "Groceries"}],
        "compliance": {"disclaimer": "General information only, not financial advice."},
    }
    draft = client.post("/v1/admin/country-packs", json={"country_code": "NZ", "content": content}).json()
    assert draft["status"] == "draft" and draft["version"] == 1
    assert client.get("/v1/countries/NZ").json()["has_pack"] is False  # drafts do nothing
    client.post(f"/v1/admin/country-packs/{draft['id']}/activate")
    nz = client.get("/v1/countries/NZ").json()
    assert nz["has_pack"] and nz["fy_start"]["month"] == 4
    acc = account(client, "NZ", "KiwiSaver", "kiwisaver")
    t = client.post(
        "/v1/transactions",
        json={"account_id": acc["id"], "date": str(TODAY), "description": "COUNTDOWN AKL", "amount": "-20"},
    ).json()
    assert t["category_id"] == category_id(client, "Groceries")

    v2 = client.post("/v1/admin/country-packs", json={"country_code": "NZ", "content": content}).json()
    client.post(f"/v1/admin/country-packs/{v2['id']}/activate")
    statuses = {
        p["version"]: p["status"] for p in client.get("/v1/admin/country-packs", params={"country": "NZ"}).json()
    }
    assert statuses == {1: "retired", 2: "active"}


def test_admin_rejects_invalid_packs(client):
    bad = {"fy_start": {"month": 13, "day": 1}, "account_types": [], "compliance": {"disclaimer": "short"}}
    assert client.post("/v1/admin/country-packs", json={"country_code": "NZ", "content": bad}).status_code == 422
    unknown_cat = {
        "fy_start": {"month": 1, "day": 1},
        "account_types": [{"key": "bank2", "label": "x"}],
        "category_rules": [{"pattern": "abc", "category": "Yachts"}],
        "compliance": {"disclaimer": "General information only, not financial advice."},
    }
    r = client.post("/v1/admin/country-packs", json={"country_code": "NZ", "content": unknown_cat})
    assert r.status_code == 422 and "Yachts" in r.text


def test_export_and_delete_account(client):
    link(client, "AU")
    account(client, "AU")
    r = client.get("/v1/me/export")
    assert r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert {"profile.csv", "accounts.csv", "transactions.csv", "remittances.csv"} <= set(names)
    assert client.delete("/v1/me").status_code == 204
    assert client.get("/v1/accounts").json() == []  # a fresh demo user


def test_fx_ingest_with_a_fake_provider(db):
    from app.services.fx import FxTable
    from app.services.fx_ingest import ingest

    class Fake:
        name = "fake"

        def rates_per_usd(self, start, end):
            return {start: {"AUD": D("1.5"), "INR": D("84")}}

    assert ingest(db, Fake(), TODAY, TODAY) == 2
    assert ingest(db, Fake(), TODAY, TODAY) == 2  # upsert, no duplicates
    assert FxTable(db).rate("AUD", "INR") == D("56")


def test_frankfurter_response_parsing():
    import httpx

    from app.providers.fx import FrankfurterProvider

    def handler(request):
        assert request.url.params["base"] == "USD"
        return httpx.Response(
            200,
            json=[
                {"date": "2026-10-30", "base": "USD", "quote": "AUD", "rate": 1.52},
                {"date": "2026-10-30", "base": "USD", "quote": "INR", "rate": 84.1},
            ],
        )

    p = FrankfurterProvider(base_url="https://fx.test/v2", client=httpx.Client(transport=httpx.MockTransport(handler)))
    out = p.rates_per_usd(date(2026, 10, 30), date(2026, 10, 30))
    assert out[date(2026, 10, 30)] == {"AUD": D("1.52"), "INR": D("84.1")}


def test_demo_data_for_a_signed_in_user_then_clear(client, db):
    from app.demo import DemoError, clear_user_data, load_demo_data
    from app.models import User, UserCountryLink

    user = User(email="Nidhi@Example.com", auth_subject="oid-1", home_currency="AUD", active_country_code="IN")
    db.add(user)
    db.flush()
    db.add(UserCountryLink(user_id=user.id, country_code="IN", relationships=["citizen"]))
    db.commit()

    msg = load_demo_data(db, "nidhi@example.com")
    assert "5 accounts" in msg
    db.refresh(user)
    assert user.active_country_code == "IN"  # their own choice is kept
    assert {c.country_code for c in user.countries} == {"AU", "IN"}
    assert "already has accounts" in load_demo_data(db, "nidhi@example.com")

    assert "Cleared data" in clear_user_data(db, "nidhi@example.com")
    assert "5 accounts" in load_demo_data(db, "nidhi@example.com")  # clean start works again

    import pytest

    with pytest.raises(DemoError, match="Sign in to the app once first"):
        load_demo_data(db, "nobody@example.com")


def test_telemetry_is_off_without_a_connection_string(monkeypatch):
    from app.config import settings
    from app.telemetry import setup_telemetry

    monkeypatch.setattr(settings, "applicationinsights_connection_string", "")
    assert setup_telemetry() is False
