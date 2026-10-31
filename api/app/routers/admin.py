"""Platform admin: country packs and the FX job trigger.

Adding or changing a country pack is a data operation: create a draft version,
review it, activate it. No code change and no deploy."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.countries.pack_schema import CountryPackContent
from app.db import get_db
from app.deps import country_ctx
from app.models import Category, CountryPack, User
from app.providers.fx import get_provider
from app.schemas import PackIn, PackOut
from app.services.fx_ingest import refresh

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def validate_pack(db: Session, content: dict) -> CountryPackContent:
    try:
        pack = CountryPackContent.model_validate(content)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False)) from None
    defaults = {c.lower() for c in db.scalars(select(Category.name).where(Category.user_id.is_(None)))}
    unknown = sorted({r.category for r in pack.category_rules if r.category.lower() not in defaults})
    if unknown:
        raise HTTPException(422, f"Rules use unknown categories: {unknown}")
    return pack


def create_pack(db: Session, country_code: str, content: dict, by: str) -> CountryPack:
    ctx = country_ctx(db, country_code)
    pack = validate_pack(db, content)
    version = (db.scalar(select(func.max(CountryPack.version)).where(CountryPack.country_code == ctx.code)) or 0) + 1
    row = CountryPack(
        country_code=ctx.code, version=version, status="draft", content=pack.model_dump(mode="json"), created_by=by
    )
    db.add(row)
    db.flush()
    return row


def activate_pack(db: Session, row: CountryPack, by: str) -> CountryPack:
    current = db.scalar(
        select(CountryPack).where(CountryPack.country_code == row.country_code, CountryPack.status == "active")
    )
    if current and current.id != row.id:
        current.status = "retired"
        db.flush()
    row.status = "active"
    row.activated_by = by
    row.activated_at = datetime.now(UTC)
    return row


@router.get("/country-packs", response_model=list[PackOut])
def list_packs(country: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    q = select(CountryPack).order_by(CountryPack.country_code, CountryPack.version.desc())
    if country:
        q = q.where(CountryPack.country_code == country.upper())
    return db.scalars(q).all()


@router.post("/country-packs", response_model=PackOut, status_code=status.HTTP_201_CREATED)
def create_pack_draft(body: PackIn, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Create a new draft version of a country's pack. It does nothing until activated."""
    row = create_pack(db, body.country_code, body.content, admin.email)
    db.commit()
    return row


@router.post("/country-packs/{pack_id}/activate", response_model=PackOut)
def activate(pack_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Make this version live for its country. The previous active version is retired, not deleted."""
    row = db.get(CountryPack, pack_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pack not found")
    validate_pack(db, row.content)
    activate_pack(db, row, admin.email)
    db.commit()
    return row


@router.post("/fx/refresh")
def fx_refresh(
    days: int = Query(default=7, ge=1, le=800), db: Session = Depends(get_db), _: User = Depends(require_admin)
):
    """Trigger the exchange-rate job by hand. Normally it runs on a schedule."""
    try:
        n = refresh(db, get_provider(), days)
    except Exception as e:  # noqa: BLE001 - surface provider failures to the admin
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"FX provider failed: {e}") from None
    return {"rates_stored": n}
