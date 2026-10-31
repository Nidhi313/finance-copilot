"""The shared country-pack suite. Every pack, the seed files and every pack stored
in the database, must pass the same checks, so a new country added as data
cannot break the rules the code relies on."""

import json

import pytest
from sqlalchemy import select

from app.countries.context import get_country_context
from app.countries.pack_schema import CountryPackContent
from app.models import Category, CountryPack
from app.seed import PACKS_DIR
from app.services.csv_import import parse_csv

SEED_FILES = sorted(PACKS_DIR.glob("[A-Z][A-Z].json"))


def all_packs(db):
    packs = [(p.stem, json.loads(p.read_text())) for p in SEED_FILES]
    packs += [(p.country_code, p.content) for p in db.scalars(select(CountryPack))]
    return packs


def test_seed_files_exist():
    assert {p.stem for p in SEED_FILES} >= {"AU", "IN"}


def test_every_pack_meets_the_contract(db):
    defaults = {c.lower() for c in db.scalars(select(Category.name).where(Category.user_id.is_(None)))}
    for code, content in all_packs(db):
        pack = CountryPackContent.model_validate(content)
        assert pack.compliance.disclaimer, code
        for rule in pack.category_rules:
            assert rule.category.lower() in defaults, f"{code}: unknown category {rule.category}"
        for rule in pack.category_rules:
            assert rule.pattern == rule.pattern.lower(), f"{code}: patterns are lower case"


def test_every_country_resolves_with_or_without_a_pack(db):
    """Basic support for all countries: every one has a currency, account types,
    calculator labels and a disclaimer."""
    from app.models import Country

    for code in db.scalars(select(Country.code)):
        ctx = get_country_context(db, code)
        assert len(ctx.currency) == 3
        assert {"bank", "savings", "cash"} <= ctx.account_type_keys()
        assert set(ctx.calculator_labels) == {
            "compound_growth",
            "regular_investing",
            "emergency_fund",
            "loan_repayment",
        }
        assert ctx.disclaimer


@pytest.mark.parametrize("path", SEED_FILES, ids=lambda p: p.stem)
def test_presets_reject_garbage_without_crashing(path):
    pack = CountryPackContent.model_validate(json.loads(path.read_text()))
    for preset in pack.csv_presets:
        try:
            r = parse_csv("not,a,real\nstatement,file,at all\n", preset.mapping)
            assert r.rows == []
        except ValueError:
            pass
