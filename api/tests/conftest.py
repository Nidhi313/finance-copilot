"""Tests run against a real Postgres database, never mocks.

Locally: `docker compose up -d db` provides it. CI: a Postgres service container.
Point TEST_DATABASE_URL elsewhere if needed. The test database is created if
missing and rebuilt from the migrations at the start of each run."""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://finance:finance@localhost:5432/finance_test")
os.environ["DATABASE_URL"] = TEST_URL
os.environ["ENVIRONMENT"] = "test"


def _ensure_database(url: str) -> None:
    u = make_url(url)
    admin = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("select 1 from pg_database where datname = :n"), {"n": u.database}).scalar()
        if not exists:
            conn.execute(text(f'create database "{u.database}"'))
    admin.dispose()


_ensure_database(TEST_URL)

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from alembic import command  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.seed import seed  # noqa: E402

USER_TABLES = [
    "transactions",
    "imports",
    "csv_mappings",
    "budgets",
    "category_rules",
    "goals",
    "remittances",
    "accounts",
    "user_country_links",
    "fx_rates",
]


@pytest.fixture(scope="session", autouse=True)
def database():
    with engine.begin() as conn:
        conn.execute(text("drop schema public cascade; create schema public;"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.upgrade(cfg, "head")
    with SessionLocal() as db:
        seed(db)
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with engine.begin() as conn:
        conn.execute(text(f"truncate {', '.join(USER_TABLES)} cascade"))
        conn.execute(text("delete from categories where user_id is not null"))
        conn.execute(text("delete from users"))
        # Packs created by tests go; the seeded launch packs stay.
        conn.execute(text("delete from country_packs where created_by <> 'seed'"))
        conn.execute(text("update country_packs set status = 'active' where created_by = 'seed'"))


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture
def add_rates(db):
    """Insert exchange rates (units per 1 USD) for a date."""
    from app.models import FxRate

    def _add(on, **rates):
        for cur, r in rates.items():
            db.merge(FxRate(date=on, currency=cur, per_usd=r, source="test"))
        db.commit()

    return _add
