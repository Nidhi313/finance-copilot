from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import FxRateOut
from app.services.fx import FxTable, MissingRate, latest_rate_date

router = APIRouter(prefix="/v1/fx", tags=["fx"])


@router.get("/rate", response_model=FxRateOut)
def get_rate(
    base: str = Query(pattern=r"^[A-Z]{3}$"),
    quote: str = Query(pattern=r"^[A-Z]{3}$"),
    on: date | None = None,
    db: Session = Depends(get_db),
):
    try:
        rate = FxTable(db, on).rate(base, quote)
    except MissingRate as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from None
    return {"base": base, "quote": quote, "date": on or date.today(), "rate": rate, "rates_as_of": latest_rate_date(db)}
