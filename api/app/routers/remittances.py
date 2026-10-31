"""Money sent between your countries, and what each transfer really cost.

Total cost = what you paid minus what the money you received was worth at the
market rate that day. It includes the visible fee and the hidden margin in the
exchange rate the provider gave you."""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.deps import country_ctx, owned
from app.models import Remittance, User
from app.schemas import RemittanceIn, RemittanceOut, RemittanceSummaryOut
from app.services.fx import FxTable, MissingRate

router = APIRouter(prefix="/v1/remittances", tags=["remittances"])
FOUR = Decimal("0.0001")
CENT = Decimal("0.01")


def with_costs(r: Remittance, fx: FxTable) -> RemittanceOut:
    out = RemittanceOut.model_validate(r)
    out.effective_rate = (r.amount_received / r.amount_sent).quantize(FOUR)
    try:
        market = fx.rate(r.from_currency, r.to_currency, r.date)
    except MissingRate:
        return out
    worth = r.amount_received / market  # value of what arrived, in the sending currency
    total_cost = r.amount_sent - worth
    out.market_rate = market.quantize(FOUR)
    out.total_cost = total_cost.quantize(CENT)
    out.rate_margin_cost = (total_cost - r.fee).quantize(CENT)
    out.cost_percent = (total_cost / r.amount_sent * 100).quantize(Decimal("0.01"))
    return out


@router.get("", response_model=list[RemittanceOut])
def list_remittances(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fx = FxTable(db)
    rows = db.scalars(select(Remittance).where(Remittance.user_id == user.id).order_by(Remittance.date.desc()))
    return [with_costs(r, fx) for r in rows]


@router.post("", response_model=RemittanceOut, status_code=status.HTTP_201_CREATED)
def create_remittance(body: RemittanceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    src, dst = country_ctx(db, body.from_country_code), country_ctx(db, body.to_country_code)
    r = Remittance(
        user_id=user.id,
        date=body.date,
        from_country_code=src.code,
        to_country_code=dst.code,
        from_currency=body.from_currency or src.currency,
        to_currency=body.to_currency or dst.currency,
        amount_sent=body.amount_sent,
        fee=body.fee,
        amount_received=body.amount_received,
        provider=body.provider,
        note=body.note,
    )
    db.add(r)
    db.commit()
    return with_costs(r, FxTable(db))


@router.delete("/{remittance_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_remittance(remittance_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Remittance, remittance_id, user))
    db.commit()


@router.get("/summary", response_model=RemittanceSummaryOut)
def remittance_summary(
    currency: str | None = Query(default=None, pattern=r"^[A-Z]{3}$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Totals across all transfers, in one currency (default: your home currency)."""
    target = currency or user.home_currency
    fx = FxTable(db)
    totals = {"sent": Decimal(0), "fees": Decimal(0), "rate_margin": Decimal(0), "total_cost": Decimal(0)}
    counted, skipped = 0, 0
    by_provider: dict[str, Decimal] = {}
    for r in db.scalars(select(Remittance).where(Remittance.user_id == user.id)):
        c = with_costs(r, fx)
        try:
            if c.total_cost is None:
                raise MissingRate(r.to_currency, r.date)
            rate = fx.rate(r.from_currency, target, r.date)
            totals["sent"] += r.amount_sent * rate
            totals["fees"] += r.fee * rate
            totals["rate_margin"] += c.rate_margin_cost * rate
            cost = c.total_cost * rate
            totals["total_cost"] += cost
            key = r.provider or "Not recorded"
            by_provider[key] = by_provider.get(key, Decimal(0)) + cost
            counted += 1
        except MissingRate:
            skipped += 1
    return {
        "currency": target,
        "transfers_counted": counted,
        "transfers_without_market_rate": skipped,
        **{k: v.quantize(CENT) for k, v in totals.items()},
        "cost_percent": (totals["total_cost"] / totals["sent"] * 100).quantize(CENT) if totals["sent"] else None,
        "cost_by_provider": {k: v.quantize(CENT) for k, v in sorted(by_provider.items(), key=lambda kv: -kv[1])},
    }
