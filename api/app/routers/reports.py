from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.deps import country_ctx
from app.models import Account, User
from app.schemas import NetWorthAccount, NetWorthOut, SpendingOut
from app.services.accounts import balances
from app.services.fx import FxTable, MissingRate, latest_rate_date
from app.services.reports import parse_month, spending_report

router = APIRouter(prefix="/v1/reports", tags=["reports"])


@router.get("/net-worth", response_model=NetWorthOut)
def net_worth(
    currency: str | None = Query(default=None, pattern=r"^[A-Z]{3}$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Everything you hold across all your countries, in one currency (default: your home currency).
    Accounts whose currency has no exchange rate yet are listed but left out of the total."""
    target = currency or user.home_currency
    accounts = db.scalars(select(Account).where(Account.user_id == user.id, Account.archived.is_(False))).all()
    bals = balances(db, [a.id for a in accounts])
    fx = FxTable(db)
    total = Decimal("0.00")
    by_country: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    missing: set[str] = set()
    rows = []
    for a in accounts:
        try:
            converted = fx.convert(bals[a.id], a.currency, target)
            total += converted
            by_country[a.country_code] += converted
        except MissingRate:
            converted = None
            missing.add(a.currency)
        rows.append(
            NetWorthAccount(
                account_id=a.id,
                name=a.name,
                country_code=a.country_code,
                currency=a.currency,
                balance=bals[a.id],
                converted=converted,
            )
        )
    return NetWorthOut(
        currency=target,
        total=total,
        by_country=dict(by_country),
        accounts=rows,
        missing_rates=sorted(missing),
        rates_as_of=latest_rate_date(db),
    )


@router.get("/spending", response_model=SpendingOut)
def spending(
    country: str,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    currency: str | None = Query(default=None, pattern=r"^[A-Z]{3}$"),
    months: int = Query(default=6, ge=1, le=24),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Spending by category for one month, and income vs spending for the months before it."""
    ctx = country_ctx(db, country)
    try:
        first = parse_month(month)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return spending_report(db, user.id, ctx.code, first, currency or ctx.currency, months)
