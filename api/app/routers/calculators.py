"""Planning calculators. The maths is the same for every country; the country
only changes the label (SIP vs dollar-cost averaging), the currency and the
disclaimer. Results are simulations, never recommendations."""

from dataclasses import asdict, is_dataclass
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.calculators import engine
from app.db import get_db
from app.deps import country_ctx
from app.models import Account, User
from app.schemas import CalcOut, CompoundGrowthIn, EmergencyFundIn, LoanRepaymentIn, RegularInvestingIn
from app.services.accounts import balances
from app.services.fx import FxTable, MissingRate
from app.services.reports import average_monthly_spending

router = APIRouter(prefix="/v1/calculators", tags=["calculators"])
EMERGENCY_ACCOUNT_TYPES = {"savings", "cash"}


def _plain(obj):
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_plain(v) for v in obj]
    return obj


def _out(db: Session, key: str, country: str, inputs: dict, result: dict) -> CalcOut:
    ctx = country_ctx(db, country)
    return CalcOut(
        calculator=key,
        label=ctx.calculator_labels[key],
        currency=ctx.currency,
        disclaimer=ctx.disclaimer,
        inputs=inputs,
        result=_plain(result),
    )


@router.post("/compound-growth", response_model=CalcOut)
def compound_growth(body: CompoundGrowthIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    result = engine.compound_growth(body.principal, body.monthly_contribution, body.annual_rate_pct, body.years)
    return _out(db, "compound_growth", body.country_code, body.model_dump(mode="json"), result)


@router.post("/regular-investing", response_model=CalcOut)
def regular_investing(body: RegularInvestingIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    result = engine.regular_investing(body.monthly_amount, body.annual_return_pct, body.years, body.annual_step_up_pct)
    return _out(db, "regular_investing", body.country_code, body.model_dump(mode="json"), result)


@router.post("/loan-repayment", response_model=CalcOut)
def loan_repayment(body: LoanRepaymentIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    result = engine.loan_repayment(body.principal, body.annual_rate_pct, body.years, body.extra_monthly)
    return _out(db, "loan_repayment", body.country_code, body.model_dump(mode="json"), result)


@router.post("/emergency-fund", response_model=CalcOut)
def emergency_fund(body: EmergencyFundIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Uses your own data for anything you leave empty: average spending over the last
    3 full months, and the balance of your savings and cash accounts in that country."""
    ctx = country_ctx(db, body.country_code)
    inputs = body.model_dump(mode="json")
    sources = {}
    expenses = body.monthly_expenses
    if expenses is None:
        expenses = average_monthly_spending(db, user.id, ctx.code, ctx.currency)
        sources["monthly_expenses"] = "average of your last 3 full months" if expenses else "no spending data yet"
        expenses = expenses or Decimal(0)
    savings = body.current_savings
    if savings is None:
        accs = db.scalars(
            select(Account).where(
                Account.user_id == user.id,
                Account.country_code == ctx.code,
                Account.archived.is_(False),
                Account.type.in_(EMERGENCY_ACCOUNT_TYPES),
            )
        ).all()
        bals = balances(db, [a.id for a in accs])
        fx = FxTable(db)
        savings = Decimal(0)
        used = []
        for a in accs:
            try:
                savings += fx.convert(bals[a.id], a.currency, ctx.currency)
                used.append(a.name)
            except MissingRate:
                pass
        sources["current_savings"] = f"savings and cash accounts: {', '.join(used) or 'none'}"
    result = engine.emergency_fund(expenses, body.months_target, savings)
    result["monthly_expenses_used"] = expenses
    result["sources"] = sources
    return _out(db, "emergency_fund", ctx.code, inputs, result)
