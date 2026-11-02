"""Sign-in with Entra External ID, tested with locally generated keys so no
network or Azure tenant is needed."""

import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import auth
from app.config import Settings, settings

ISSUER = "https://tenant-id.ciamlogin.com/tenant-id/v2.0"
API_ID = "11111111-2222-3333-4444-555555555555"


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


SIGNING_KEY = _key()
OTHER_KEY = _key()


class _FakeJwks:
    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": SIGNING_KEY.public_key()})()


def make_token(oid="user-a", key=SIGNING_KEY, **overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": API_ID,
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
        "oid": oid,
        "sub": f"sub-{oid}",
        "scp": "access_as_user",
        "email": f"{oid or 'x'}@example.com",
        "name": (oid or "x").title(),
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})


@pytest.fixture
def entra(monkeypatch):
    verifier = auth.TokenVerifier("https://unused", [API_ID, f"api://{API_ID}"], "access_as_user")
    verifier._issuer = ISSUER
    verifier._jwks = _FakeJwks()
    verifier._loaded_at = time.monotonic()
    monkeypatch.setattr(settings, "auth_mode", "entra")
    monkeypatch.setattr(auth, "_verifier", verifier)


def h(token):
    return {"Authorization": f"Bearer {token}"}


def test_no_token_is_401(client, entra):
    r = client.get("/v1/me")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_first_sign_in_creates_the_user_once(client, entra):
    a = client.get("/v1/me", headers=h(make_token("user-a"))).json()
    again = client.get("/v1/me", headers=h(make_token("user-a"))).json()
    assert a["id"] == again["id"]
    assert a["email"] == "user-a@example.com" and a["display_name"] == "User-A"
    assert a["countries"] == [] and a["onboarding_dismissed"] is False


def test_each_person_sees_only_their_own_data(client, entra):
    ta, tb = h(make_token("user-a")), h(make_token("user-b"))
    acc = client.post("/v1/accounts", headers=ta, json={"country_code": "AU", "name": "A's account", "type": "bank"})
    assert acc.status_code == 201
    assert [x["name"] for x in client.get("/v1/accounts", headers=ta).json()] == ["A's account"]
    assert client.get("/v1/accounts", headers=tb).json() == []
    assert client.get(f"/v1/accounts/{acc.json()['id']}", headers=tb).status_code == 404


def test_api_uri_audience_is_accepted(client, entra):
    assert client.get("/v1/me", headers=h(make_token(aud=f"api://{API_ID}"))).status_code == 200


@pytest.mark.parametrize(
    "bad",
    [
        {"aud": "someone-elses-api"},
        {"iss": "https://evil.example.com/v2.0"},
        {"exp": int(time.time()) - 3600},
        {"scp": "something.else"},
        {"scp": None},
        {"oid": None, "sub": None},
    ],
)
def test_bad_tokens_are_rejected(client, entra, bad):
    assert client.get("/v1/me", headers=h(make_token(**bad))).status_code == 401


def test_token_signed_with_another_key_is_rejected(client, entra):
    assert client.get("/v1/me", headers=h(make_token(key=OTHER_KEY))).status_code == 401


def test_garbage_token_is_rejected(client, entra):
    assert client.get("/v1/me", headers=h("not-a-jwt")).status_code == 401


def test_users_without_email_claim_still_work(client, entra):
    r = client.get("/v1/me", headers=h(make_token("no-email", email=None)))
    assert r.status_code == 200 and r.json()["email"] is None


def test_admin_needs_listed_email(client, entra, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", ["boss@example.com"])
    assert client.get("/v1/admin/country-packs", headers=h(make_token("user-a"))).status_code == 403
    assert (
        client.get("/v1/admin/country-packs", headers=h(make_token("boss", email="boss@example.com"))).status_code
        == 200
    )


def test_dev_mode_refused_outside_local(client, monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    assert client.get("/v1/me").status_code == 500


def test_settings_check_catches_missing_entra_config():
    with pytest.raises(RuntimeError, match="ENTRA_TENANT_ID"):
        Settings(auth_mode="entra", entra_tenant_subdomain="x", entra_api_client_id=str(uuid.uuid4())).check()
    with pytest.raises(RuntimeError, match="AUTH_MODE"):
        Settings(auth_mode="magic").check()
    Settings(auth_mode="entra", entra_tenant_subdomain="x", entra_tenant_id="t", entra_api_client_id="c").check()


def test_verifier_loads_issuer_and_keys_from_metadata(monkeypatch):
    import httpx

    def fake_get(url, timeout):
        assert url == "https://contoso.ciamlogin.com/tid/v2.0/.well-known/openid-configuration"
        return httpx.Response(
            200, json={"issuer": ISSUER, "jwks_uri": "https://keys.example/jwks"}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    s = Settings(auth_mode="entra", entra_tenant_subdomain="contoso", entra_tenant_id="tid", entra_api_client_id="c")
    v = auth.TokenVerifier(s.entra_metadata_url, ["c"], "access_as_user")
    v._load()
    assert v._issuer == ISSUER and v._jwks is not None


def test_getting_started_ticks_off_from_real_data(client):
    gs = client.get("/v1/me/getting-started").json()
    assert gs["done_count"] == 0 and gs["total"] == 6 and gs["dismissed"] is False
    client.put("/v1/me/countries/AU", json={"relationships": ["lives_here"]})
    client.post("/v1/accounts", json={"country_code": "AU", "name": "A", "type": "bank"})
    done = {s["key"] for s in client.get("/v1/me/getting-started").json()["steps"] if s["done"]}
    assert done == {"countries", "account"}
    client.patch("/v1/me", json={"onboarding_dismissed": True})
    assert client.get("/v1/me/getting-started").json()["dismissed"] is True
