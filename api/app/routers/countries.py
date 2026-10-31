from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import country_ctx
from app.models import Country, CountryPack
from app.schemas import CountryContextOut, CountryOut

router = APIRouter(prefix="/v1/countries", tags=["countries"])


@router.get("", response_model=list[CountryOut])
def list_countries(db: Session = Depends(get_db)):
    """Every country. All have basic support; has_pack marks full support."""
    packed = set(db.scalars(select(CountryPack.country_code).where(CountryPack.status == "active")))
    return [
        CountryOut(code=c.code, name=c.name, currency=c.currency, locale=c.locale, has_pack=c.code in packed)
        for c in db.scalars(select(Country).order_by(Country.name))
    ]


@router.get("/{code}", response_model=CountryContextOut)
def get_country(code: str, db: Session = Depends(get_db)):
    ctx = country_ctx(db, code)
    return CountryContextOut(**{k: getattr(ctx, k) for k in CountryContextOut.model_fields})
