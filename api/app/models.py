"""Database tables.

Rules that hold everywhere:
- Money is Numeric (exact decimal) plus a 3-letter currency code. Never float.
- Country is data (country_code columns), never a branch in code.
- Exchange rates are stored as units of a currency per 1 USD.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

Money = Numeric(19, 4)
JsonType = JSON().with_variant(JSONB(), "postgresql")


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Country(Base):
    """Every ISO country, with basic support (currency + locale). Seeded from data."""

    __tablename__ = "countries"
    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3))
    locale: Mapped[str] = mapped_column(String(20))


class CountryPack(Base):
    """Full support for a country, stored as versioned data. Rows are never edited:
    a change is a new version. Only one version per country can be active."""

    __tablename__ = "country_packs"
    __table_args__ = (
        UniqueConstraint("country_code", "version"),
        Index(
            "one_active_pack_per_country",
            "country_code",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft | active | retired
    content: Mapped[dict] = mapped_column(JsonType)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_by: Mapped[str | None] = mapped_column(String(255))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    # Entra object id of the person. Empty only for the local demo user.
    auth_subject: Mapped[str | None] = mapped_column(String(100), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(100), default="")
    home_currency: Mapped[str] = mapped_column(String(3), default="AUD")
    active_country_code: Mapped[str | None] = mapped_column(ForeignKey("countries.code"))
    onboarding_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    countries: Mapped[list["UserCountryLink"]] = relationship(
        cascade="all, delete-orphan", order_by="UserCountryLink.created_at"
    )


class UserCountryLink(Base):
    """A person can belong to many countries, each with its own relationship."""

    __tablename__ = "user_country_links"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"), primary_key=True)
    relationships: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(String(3))
    institution: Mapped[str] = mapped_column(String(100), default="")
    opening_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Category(Base):
    """user_id NULL means a default category shared by everyone."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(10), default="expense")  # expense | income | transfer


class CategoryRule(Base):
    __tablename__ = "category_rules"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    pattern: Mapped[str] = mapped_column(String(100))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    priority: Mapped[int] = mapped_column(Integer, default=100)


class Import(Base):
    __tablename__ = "imports"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(100))
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Transaction(Base):
    """amount is signed: negative is money out, positive is money in.
    The currency is the account's currency."""

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "dedupe_hash"),
        Index("ix_transactions_user_date", "user_id", "date"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[Decimal] = mapped_column(Money)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    notes: Mapped[str] = mapped_column(Text, default="")
    import_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("imports.id", ondelete="SET NULL"))
    dedupe_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CsvMapping(Base):
    """A user's saved column mapping for a bank that has no preset."""

    __tablename__ = "csv_mappings"
    __table_args__ = (UniqueConstraint("user_id", "name"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    mapping: Mapped[dict] = mapped_column(JsonType)


class Budget(Base):
    """A monthly budget for one category in one country, in that country's currency
    unless the user chose another."""

    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "country_code", "category_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))


class FxRate(Base):
    __tablename__ = "fx_rates"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    per_usd: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    source: Mapped[str] = mapped_column(String(30))


class Remittance(Base):
    """amount_sent is everything paid, including the fee, in from_currency."""

    __tablename__ = "remittances"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    from_country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    to_country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"))
    from_currency: Mapped[str] = mapped_column(String(3))
    to_currency: Mapped[str] = mapped_column(String(3))
    amount_sent: Mapped[Decimal] = mapped_column(Money)
    fee: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    amount_received: Mapped[Decimal] = mapped_column(Money)
    provider: Mapped[str] = mapped_column(String(100), default="")
    note: Mapped[str] = mapped_column(Text, default="")


class Goal(Base):
    """Progress comes from a linked account's balance, or from saved_amount if no account."""

    __tablename__ = "goals"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    target_amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    target_date: Mapped[date | None] = mapped_column(Date)
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    saved_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
