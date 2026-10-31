import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.deps import country_ctx, owned
from app.models import Budget, Category, User
from app.routers.categories import visible_category
from app.schemas import BudgetIn, BudgetOut, BudgetStatusOut
from app.services.reports import parse_month, spent_by_category

router = APIRouter(prefix="/v1/budgets", tags=["budgets"])


@router.get("", response_model=list[BudgetOut])
def list_budgets(country: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(Budget).where(Budget.user_id == user.id)
    if country:
        q = q.where(Budget.country_code == country.upper())
    return db.scalars(q).all()


@router.put("", response_model=BudgetOut)
def upsert_budget(body: BudgetIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create or change the monthly budget for one category in one country."""
    ctx = country_ctx(db, body.country_code)
    cat = visible_category(db, body.category_id, user)
    if cat.kind != "expense":
        raise HTTPException(422, "Budgets are for expense categories")
    budget = db.scalar(
        select(Budget).where(Budget.user_id == user.id, Budget.country_code == ctx.code, Budget.category_id == cat.id)
    )
    if budget is None:
        budget = Budget(user_id=user.id, country_code=ctx.code, category_id=cat.id)
        db.add(budget)
    budget.amount = body.amount
    budget.currency = body.currency or budget.currency or ctx.currency
    db.commit()
    return budget


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(budget_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Budget, budget_id, user))
    db.commit()


@router.get("/status", response_model=list[BudgetStatusOut])
def budget_status(
    country: str,
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Spent vs remaining for each budget in a country, for one month (default: this month)."""
    ctx = country_ctx(db, country)
    first = parse_month(month)
    budgets = db.scalars(select(Budget).where(Budget.user_id == user.id, Budget.country_code == ctx.code)).all()
    names = {c.id: c.name for c in db.scalars(select(Category))}
    cache: dict[str, dict] = {}
    out = []
    for b in budgets:
        if b.currency not in cache:
            cache[b.currency], _ = spent_by_category(db, user.id, ctx.code, first, b.currency)
        spent = max(Decimal("0.00"), cache[b.currency].get(b.category_id, Decimal("0.00")))
        out.append(
            BudgetStatusOut(
                budget_id=b.id,
                category_id=b.category_id,
                category=names.get(b.category_id, "?"),
                currency=b.currency,
                budget=b.amount,
                spent=spent,
                remaining=b.amount - spent,
                percent_used=(spent / b.amount * 100).quantize(Decimal("0.1")) if b.amount else Decimal(0),
            )
        )
    return sorted(out, key=lambda s: -s.percent_used)
