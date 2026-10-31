"""Spending, budgets and net worth. Amounts are converted with the exchange rate
at the end of each month (or today for the current month)."""

import calendar
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Category, Transaction
from app.services.fx import FxTable, MissingRate

ZERO = Decimal("0.00")


def parse_month(s: str | None) -> date:
    if not s:
        t = date.today()
        return date(t.year, t.month, 1)
    try:
        y, m = s.split("-")
        return date(int(y), int(m), 1)
    except ValueError:
        raise ValueError("month must look like 2026-10") from None


def month_end(first: date) -> date:
    return date(first.year, first.month, calendar.monthrange(first.year, first.month)[1])


def add_months(first: date, n: int) -> date:
    idx = first.year * 12 + first.month - 1 + n
    return date(idx // 12, idx % 12 + 1, 1)


def rate_date(first: date) -> date:
    return min(month_end(first), date.today())


def category_kinds(db: Session) -> dict[uuid.UUID, tuple[str, str]]:
    return {c.id: (c.name, c.kind) for c in db.scalars(select(Category))}


def country_transactions(db: Session, user_id: uuid.UUID, country: str, start: date, end: date):
    return db.execute(
        select(Transaction.date, Transaction.amount, Transaction.category_id, Account.currency)
        .join(Account, Account.id == Transaction.account_id)
        .where(
            Transaction.user_id == user_id,
            Account.country_code == country,
            Transaction.date >= start,
            Transaction.date <= end,
        )
    ).all()


def spending_report(db: Session, user_id: uuid.UUID, country: str, month: date, currency: str, months: int = 6) -> dict:
    fx = FxTable(db)
    kinds = category_kinds(db)
    start = add_months(month, -(months - 1))
    rows = country_transactions(db, user_id, country, start, month_end(month))
    missing: set[str] = set()
    monthly: dict[date, dict[str, Decimal]] = {
        add_months(start, i): {"income": ZERO, "spending": ZERO} for i in range(months)
    }
    by_cat: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for d, amount, cat_id, cur in rows:
        first = date(d.year, d.month, 1)
        try:
            value = fx.convert(amount, cur, currency, rate_date(first))
        except MissingRate:
            missing.add(cur)
            continue
        name, kind = kinds.get(cat_id, ("Uncategorised", "expense"))
        if kind == "transfer":
            continue
        if value < 0:
            monthly[first]["spending"] += -value
            if first == month:
                by_cat[name] += -value
        else:
            monthly[first]["income"] += value
    total = sum(by_cat.values(), ZERO)
    return {
        "country_code": country,
        "currency": currency,
        "month": month.strftime("%Y-%m"),
        "by_category": [
            {"category": k, "amount": v, "percent": (v / total * 100).quantize(Decimal("0.1")) if total else ZERO}
            for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])
        ],
        "monthly": [{"month": k.strftime("%Y-%m"), **v} for k, v in monthly.items()],
        "income": monthly[month]["income"],
        "spending": monthly[month]["spending"],
        "missing_rates": sorted(missing),
    }


def average_monthly_spending(
    db: Session, user_id: uuid.UUID, country: str, currency: str, months: int = 3
) -> Decimal | None:
    """Average over the last `months` full months. None if there is no spending data."""
    this_month = parse_month(None)
    report = spending_report(db, user_id, country, add_months(this_month, -1), currency, months)
    values = [m["spending"] for m in report["monthly"]]
    if not any(values):
        return None
    return (sum(values, ZERO) / len(values)).quantize(Decimal("0.01"))


def spent_by_category(
    db: Session, user_id: uuid.UUID, country: str, month: date, currency: str
) -> tuple[dict[uuid.UUID | None, Decimal], set[str]]:
    fx = FxTable(db)
    out: dict[uuid.UUID | None, Decimal] = defaultdict(lambda: ZERO)
    missing: set[str] = set()
    for _d, amount, cat_id, cur in country_transactions(db, user_id, country, month, month_end(month)):
        try:
            out[cat_id] += -fx.convert(amount, cur, currency, rate_date(month))
        except MissingRate:
            missing.add(cur)
    return out, missing
