"""Request and response shapes for the REST API. Money is sent as a decimal
string (for example "1234.50") so no precision is lost in JSON."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.countries.pack_schema import AccountType, CsvMapping, CsvPreset, FyStart

T = TypeVar("T")

CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
Amount = Annotated[Decimal, Field(max_digits=15, decimal_places=4)]
Positive = Annotated[Decimal, Field(ge=0, max_digits=15, decimal_places=4)]
RELATIONSHIPS = ("tax_resident", "citizen", "lives_here", "holds_accounts", "sends_money_to")
Relationship = Literal["tax_resident", "citizen", "lives_here", "holds_accounts", "sends_money_to"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# Countries
class CountryOut(ORM):
    code: str
    name: str
    currency: str
    locale: str
    has_pack: bool = False


class CountryContextOut(BaseModel):
    code: str
    name: str
    currency: str
    locale: str
    has_pack: bool
    pack_version: int | None
    fy_start: FyStart
    account_types: list[AccountType]
    calculator_labels: dict[str, str]
    csv_presets: list[CsvPreset]
    disclaimer: str


# Profile
class CountryLinkOut(ORM):
    country_code: str
    relationships: list[str]


class MeOut(ORM):
    id: uuid.UUID
    email: str
    display_name: str
    home_currency: str
    active_country_code: str | None
    countries: list[CountryLinkOut]


class MeUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    home_currency: CurrencyCode | None = None
    active_country_code: CountryCode | None = None


class CountryLinkIn(BaseModel):
    relationships: list[Relationship] = Field(default_factory=list)


# Accounts
class AccountIn(BaseModel):
    country_code: CountryCode
    name: str = Field(min_length=1, max_length=100)
    type: str
    currency: CurrencyCode | None = None  # defaults to the country's currency
    institution: str = Field(default="", max_length=100)
    opening_balance: Amount = Decimal(0)


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: str | None = None
    institution: str | None = Field(default=None, max_length=100)
    opening_balance: Amount | None = None
    archived: bool | None = None


class AccountOut(ORM):
    id: uuid.UUID
    country_code: str
    name: str
    type: str
    currency: str
    institution: str
    opening_balance: Decimal
    archived: bool
    balance: Decimal = Decimal(0)


# Categories
class CategoryOut(ORM):
    id: uuid.UUID
    name: str
    kind: str
    is_default: bool = False


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    kind: Literal["expense", "income", "transfer"] = "expense"


class RuleIn(BaseModel):
    pattern: str = Field(min_length=2, max_length=100)
    category_id: uuid.UUID
    priority: int = Field(default=100, ge=0, le=1000)


class RuleOut(ORM):
    id: uuid.UUID
    pattern: str
    category_id: uuid.UUID
    priority: int


# Transactions
class TransactionIn(BaseModel):
    account_id: uuid.UUID
    date: dt.date
    description: str = Field(min_length=1, max_length=500)
    amount: Amount
    category_id: uuid.UUID | None = None
    notes: str = Field(default="", max_length=2000)


class TransactionUpdate(BaseModel):
    date: dt.date | None = None
    description: str | None = Field(default=None, min_length=1, max_length=500)
    amount: Amount | None = None
    category_id: uuid.UUID | None = None
    clear_category: bool = False
    notes: str | None = Field(default=None, max_length=2000)


class TransactionOut(ORM):
    id: uuid.UUID
    account_id: uuid.UUID
    date: dt.date
    description: str
    amount: Decimal
    currency: str = ""
    category_id: uuid.UUID | None
    notes: str
    import_id: uuid.UUID | None


# Imports
class ImportRowOut(BaseModel):
    line: int
    date: dt.date
    description: str
    amount: Decimal
    category_id: uuid.UUID | None = None


class ImportPreviewOut(BaseModel):
    header: list[str] | None
    rows: list[ImportRowOut]
    total_lines: int
    parsed: int
    errors: list[dict]


class ImportOut(ORM):
    id: uuid.UUID
    account_id: uuid.UUID
    filename: str
    source: str
    rows_total: int
    rows_imported: int
    rows_duplicate: int
    rows_failed: int


class ImportResultOut(BaseModel):
    import_: ImportOut = Field(alias="import")
    errors: list[dict]
    model_config = ConfigDict(populate_by_name=True)


class SavedMappingOut(ORM):
    id: uuid.UUID
    name: str
    mapping: CsvMapping


# Budgets
class BudgetIn(BaseModel):
    country_code: CountryCode
    category_id: uuid.UUID
    amount: Positive
    currency: CurrencyCode | None = None


class BudgetOut(ORM):
    id: uuid.UUID
    country_code: str
    category_id: uuid.UUID
    amount: Decimal
    currency: str


class BudgetStatusOut(BaseModel):
    budget_id: uuid.UUID
    category_id: uuid.UUID
    category: str
    currency: str
    budget: Decimal
    spent: Decimal
    remaining: Decimal
    percent_used: Decimal


# Reports
class NetWorthAccount(BaseModel):
    account_id: uuid.UUID
    name: str
    country_code: str
    currency: str
    balance: Decimal
    converted: Decimal | None


class NetWorthOut(BaseModel):
    currency: str
    total: Decimal
    by_country: dict[str, Decimal]
    accounts: list[NetWorthAccount]
    missing_rates: list[str]
    rates_as_of: dt.date | None


class SpendingOut(BaseModel):
    country_code: str
    currency: str
    month: str
    by_category: list[dict]
    monthly: list[dict]
    income: Decimal
    spending: Decimal
    missing_rates: list[str]


# Remittances
class RemittanceIn(BaseModel):
    date: dt.date
    from_country_code: CountryCode
    to_country_code: CountryCode
    from_currency: CurrencyCode | None = None
    to_currency: CurrencyCode | None = None
    amount_sent: Positive = Field(description="Everything you paid, including the fee")
    fee: Positive = Decimal(0)
    amount_received: Positive
    provider: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=2000)

    @field_validator("amount_sent", "amount_received")
    @classmethod
    def _non_zero(cls, v: Decimal):
        if v <= 0:
            raise ValueError("must be more than zero")
        return v


class RemittanceOut(ORM):
    id: uuid.UUID
    date: dt.date
    from_country_code: str
    to_country_code: str
    from_currency: str
    to_currency: str
    amount_sent: Decimal
    fee: Decimal
    amount_received: Decimal
    provider: str
    note: str
    effective_rate: Decimal | None = None
    market_rate: Decimal | None = None
    total_cost: Decimal | None = None
    rate_margin_cost: Decimal | None = None
    cost_percent: Decimal | None = None


# Goals
class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    target_amount: Positive
    currency: CurrencyCode
    target_date: dt.date | None = None
    account_id: uuid.UUID | None = None
    saved_amount: Positive = Decimal(0)


class GoalOut(ORM):
    id: uuid.UUID
    name: str
    target_amount: Decimal
    currency: str
    target_date: dt.date | None
    account_id: uuid.UUID | None
    saved_amount: Decimal
    current: Decimal | None = None
    percent: Decimal | None = None
    monthly_needed: Decimal | None = None


# Calculators
Years = Annotated[int, Field(ge=1, le=60)]
Rate = Annotated[Decimal, Field(ge=0, le=100)]


class CalcBase(BaseModel):
    country_code: CountryCode


class CompoundGrowthIn(CalcBase):
    principal: Positive = Decimal(0)
    monthly_contribution: Positive = Decimal(0)
    annual_rate_pct: Rate
    years: Years


class RegularInvestingIn(CalcBase):
    monthly_amount: Positive
    annual_return_pct: Rate
    years: Years
    annual_step_up_pct: Rate = Decimal(0)


class EmergencyFundIn(CalcBase):
    months_target: int = Field(default=6, ge=1, le=24)
    monthly_expenses: Positive | None = Field(
        default=None, description="Leave empty to use your average spending over the last 3 full months"
    )
    current_savings: Positive | None = Field(
        default=None, description="Leave empty to use the balance of your savings and cash accounts"
    )


class LoanRepaymentIn(CalcBase):
    principal: Positive
    annual_rate_pct: Rate
    years: Years
    extra_monthly: Positive = Decimal(0)


class CalcOut(BaseModel):
    calculator: str
    label: str
    currency: str
    disclaimer: str
    inputs: dict
    result: dict


# Admin
class PackIn(BaseModel):
    country_code: CountryCode
    content: dict


class PackOut(ORM):
    id: uuid.UUID
    country_code: str
    version: int
    status: str
    content: dict
    created_by: str
    activated_by: str | None


class RemittanceSummaryOut(BaseModel):
    currency: str
    transfers_counted: int
    transfers_without_market_rate: int
    sent: Decimal
    fees: Decimal
    rate_margin: Decimal
    total_cost: Decimal
    cost_percent: Decimal | None
    cost_by_provider: dict[str, Decimal]


class FxRateOut(BaseModel):
    base: str
    quote: str
    date: dt.date
    rate: Decimal
    rates_as_of: dt.date | None


class ApplyRulesOut(BaseModel):
    categorised: int
    still_uncategorised: int
