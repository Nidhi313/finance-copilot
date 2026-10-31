"""Idempotent seed: every country, default categories, and the launch country
packs from /country-packs. Safe to run on every start."""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Category, Country, CountryPack
from app.routers.admin import activate_pack, create_pack

PACKS_DIR = Path(__file__).resolve().parents[2] / "country-packs"
if not PACKS_DIR.exists():  # inside the Docker image
    PACKS_DIR = Path(__file__).resolve().parents[1] / "country-packs"

DEFAULT_CATEGORIES = [
    ("Groceries", "expense"),
    ("Eating out", "expense"),
    ("Rent", "expense"),
    ("Utilities", "expense"),
    ("Transport", "expense"),
    ("Shopping", "expense"),
    ("Health", "expense"),
    ("Entertainment", "expense"),
    ("Education", "expense"),
    ("Travel", "expense"),
    ("Insurance", "expense"),
    ("Fees", "expense"),
    ("Gifts and family support", "expense"),
    ("Other", "expense"),
    ("Income", "income"),
    ("Interest", "income"),
    ("Transfers", "transfer"),
]


def seed(db: Session) -> dict:
    countries = json.loads((PACKS_DIR / "countries.json").read_text())
    stmt = insert(Country).values(countries)
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=[Country.code],
            set_={"name": stmt.excluded.name, "currency": stmt.excluded.currency, "locale": stmt.excluded.locale},
        )
    )
    existing = set(db.scalars(select(Category.name).where(Category.user_id.is_(None))))
    for name, kind in DEFAULT_CATEGORIES:
        if name not in existing:
            db.add(Category(user_id=None, name=name, kind=kind))
    db.flush()

    activated = []
    for path in sorted(PACKS_DIR.glob("[A-Z][A-Z].json")):
        code = path.stem
        has_any = db.scalar(select(CountryPack.id).where(CountryPack.country_code == code).limit(1))
        if has_any:
            continue  # after the first seed, packs are managed through the admin API
        row = create_pack(db, code, json.loads(path.read_text()), by="seed")
        activate_pack(db, row, by="seed")
        activated.append(code)
    db.commit()
    return {"countries": len(countries), "packs_seeded": activated}
