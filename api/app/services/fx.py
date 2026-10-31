"""Currency conversion. Rates are stored as units of each currency per 1 USD, so
any pair is two lookups and a new currency is one more rate series."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FxRate

MAX_STALENESS_DAYS = 10  # weekends and holidays have no rates


class MissingRate(LookupError):
    def __init__(self, currency: str, on: date):
        super().__init__(f"No exchange rate for {currency} on or before {on}")
        self.currency = currency
        self.on = on


class FxTable:
    """Loads the rates needed for one request once, then converts in memory."""

    def __init__(self, db: Session, on: date | None = None):
        self.db = db
        self.on = on or date.today()
        self._cache: dict[tuple[str, date], Decimal | None] = {}

    def per_usd(self, currency: str, on: date | None = None) -> Decimal:
        on = on or self.on
        if currency == "USD":
            return Decimal(1)
        key = (currency, on)
        if key not in self._cache:
            row = self.db.execute(
                select(FxRate.per_usd, FxRate.date)
                .where(FxRate.currency == currency, FxRate.date <= on)
                .order_by(FxRate.date.desc())
                .limit(1)
            ).first()
            ok = row is not None and (on - row.date).days <= MAX_STALENESS_DAYS
            self._cache[key] = row.per_usd if ok else None
        rate = self._cache[key]
        if rate is None:
            raise MissingRate(currency, on)
        return rate

    def rate(self, base: str, quote: str, on: date | None = None) -> Decimal:
        """Units of quote per 1 unit of base."""
        if base == quote:
            return Decimal(1)
        return self.per_usd(quote, on) / self.per_usd(base, on)

    def convert(self, amount: Decimal, base: str, quote: str, on: date | None = None) -> Decimal:
        return (amount * self.rate(base, quote, on)).quantize(Decimal("0.01"))


def latest_rate_date(db: Session) -> date | None:
    return db.scalar(select(func.max(FxRate.date)))
