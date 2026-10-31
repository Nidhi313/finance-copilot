"""The shape of a country pack. Packs are data; this schema is the contract every
pack must meet before it can be saved, so a bad pack is rejected at the door."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FyStart(Strict):
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)


class AccountType(Strict):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,29}$")
    label: str = Field(min_length=1, max_length=50)


class CategoryRuleDefault(Strict):
    pattern: str = Field(min_length=2, max_length=100)
    category: str = Field(min_length=1, max_length=50)


Column = str | int


class CsvMapping(Strict):
    """How to read one bank's CSV export. Columns are header names when the file
    has a header row, or 0-based positions when it does not."""

    has_header: bool = True
    delimiter: str = Field(default=",", min_length=1, max_length=1)
    date_column: Column
    date_format: str = "%d/%m/%Y"
    description_columns: list[Column] = Field(min_length=1)
    amount_column: Column | None = None
    debit_column: Column | None = None
    credit_column: Column | None = None
    # Credit-card exports often show purchases as positive numbers.
    invert_amounts: bool = False
    decimal_separator: Literal[".", ","] = "."

    @model_validator(mode="after")
    def _amount_columns(self):
        single = self.amount_column is not None
        split = self.debit_column is not None or self.credit_column is not None
        if single == split:
            raise ValueError("set either amount_column, or debit_column and/or credit_column")
        if not self.has_header:
            cols = [
                self.date_column,
                *self.description_columns,
                self.amount_column,
                self.debit_column,
                self.credit_column,
            ]
            if any(isinstance(c, str) for c in cols if c is not None):
                raise ValueError("without a header row, columns must be 0-based positions")
        return self


class CsvPreset(Strict):
    id: str = Field(pattern=r"^[a-z0-9_]{2,50}$")
    bank_name: str
    # False until the format has been checked against a real export from that bank.
    verified: bool = False
    mapping: CsvMapping


class Compliance(Strict):
    disclaimer: str = Field(min_length=20)
    # India: education content may only use prices at least 90 days old.
    min_price_data_age_days: int = Field(default=0, ge=0)


class CountryPackContent(Strict):
    schema_version: Literal[1] = 1
    fy_start: FyStart
    account_types: list[AccountType] = Field(min_length=1)
    calculator_labels: dict[str, str] = Field(default_factory=dict)
    category_rules: list[CategoryRuleDefault] = Field(default_factory=list)
    csv_presets: list[CsvPreset] = Field(default_factory=list)
    compliance: Compliance
    # Filled in by later releases. Present now so the shape is stable.
    market: dict | None = None
    retirement_schemes: list[dict] = Field(default_factory=list)
    lessons: list[dict] = Field(default_factory=list)

    @field_validator("calculator_labels")
    @classmethod
    def _known_calculators(cls, v: dict[str, str]):
        unknown = set(v) - KNOWN_CALCULATORS
        if unknown:
            raise ValueError(f"unknown calculators: {sorted(unknown)}")
        return v

    @model_validator(mode="after")
    def _unique_keys(self):
        for name, keys in (
            ("account type", [t.key for t in self.account_types]),
            ("csv preset", [p.id for p in self.csv_presets]),
        ):
            if len(keys) != len(set(keys)):
                raise ValueError(f"duplicate {name} keys")
        return self


KNOWN_CALCULATORS = {"compound_growth", "regular_investing", "emergency_fund", "loan_repayment"}
