"""Fetch exchange rates and store them. Runs as a scheduled job (locally:
`python -m app.cli fx-refresh`), never inside a user request."""

from datetime import date, timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import FxRate
from app.providers.fx import FxProvider


def ingest(db: Session, provider: FxProvider, start: date, end: date) -> int:
    data = provider.rates_per_usd(start, end)
    rows = [
        {"date": d, "currency": cur, "per_usd": rate, "source": provider.name}
        for d, rates in data.items()
        for cur, rate in rates.items()
        if len(cur) == 3 and rate > 0
    ]
    if not rows:
        return 0
    stmt = insert(FxRate).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[FxRate.date, FxRate.currency],
        set_={"per_usd": stmt.excluded.per_usd, "source": stmt.excluded.source},
    )
    db.execute(stmt)
    db.commit()
    return len(rows)


def refresh(db: Session, provider: FxProvider, days: int = 30) -> int:
    end = date.today()
    return ingest(db, provider, end - timedelta(days=days), end)
