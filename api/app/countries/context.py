"""Resolve what the app knows about a country: basic support for every country,
plus whatever its active country pack adds. Nothing else in the code branches on
a country code; it asks for a CountryContext instead."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.countries.pack_schema import AccountType, CountryPackContent, CsvPreset, FyStart
from app.models import Country, CountryPack

BASIC_ACCOUNT_TYPES = [
    AccountType(key="bank", label="Bank account"),
    AccountType(key="savings", label="Savings account"),
    AccountType(key="cash", label="Cash"),
    AccountType(key="credit_card", label="Credit card"),
    AccountType(key="investment", label="Investment account"),
    AccountType(key="retirement", label="Retirement account"),
    AccountType(key="other", label="Other"),
]

BASIC_CALCULATOR_LABELS = {
    "compound_growth": "Compound growth",
    "regular_investing": "Regular investing",
    "emergency_fund": "Emergency fund",
    "loan_repayment": "Loan repayment",
}

BASIC_DISCLAIMER = (
    "This is general information and a simulation based on the numbers you entered. "
    "It is not financial advice and does not consider your personal circumstances."
)


@dataclass
class CountryContext:
    code: str
    name: str
    currency: str
    locale: str
    has_pack: bool
    pack_version: int | None
    fy_start: FyStart
    account_types: list[AccountType]
    calculator_labels: dict[str, str]
    category_rules: list = field(default_factory=list)
    csv_presets: list[CsvPreset] = field(default_factory=list)
    disclaimer: str = BASIC_DISCLAIMER
    min_price_data_age_days: int = 0

    def account_type_keys(self) -> set[str]:
        return {t.key for t in self.account_types}


class UnknownCountry(LookupError):
    pass


def active_pack(db: Session, code: str) -> CountryPack | None:
    return db.scalar(select(CountryPack).where(CountryPack.country_code == code, CountryPack.status == "active"))


def get_country_context(db: Session, code: str) -> CountryContext:
    code = code.upper()
    country = db.get(Country, code)
    if country is None:
        raise UnknownCountry(code)
    pack = active_pack(db, code)
    if pack is None:
        return CountryContext(
            code=country.code,
            name=country.name,
            currency=country.currency,
            locale=country.locale,
            has_pack=False,
            pack_version=None,
            fy_start=FyStart(month=1, day=1),
            account_types=list(BASIC_ACCOUNT_TYPES),
            calculator_labels=dict(BASIC_CALCULATOR_LABELS),
        )
    content = CountryPackContent.model_validate(pack.content)
    # A pack adds local account types on top of the basic ones, never removes them,
    # so every feature keeps working for every country.
    pack_keys = {t.key for t in content.account_types}
    account_types = content.account_types + [t for t in BASIC_ACCOUNT_TYPES if t.key not in pack_keys]
    return CountryContext(
        code=country.code,
        name=country.name,
        currency=country.currency,
        locale=country.locale,
        has_pack=True,
        pack_version=pack.version,
        fy_start=content.fy_start,
        account_types=account_types,
        calculator_labels={**BASIC_CALCULATOR_LABELS, **content.calculator_labels},
        category_rules=content.category_rules,
        csv_presets=content.csv_presets,
        disclaimer=content.compliance.disclaimer,
        min_price_data_age_days=content.compliance.min_price_data_age_days,
    )
