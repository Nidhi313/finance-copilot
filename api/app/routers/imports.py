"""CSV import in two steps: preview (nothing saved) then import.

Today the import runs inside the request, capped at 5 MB. When the app moves to
Azure it moves onto a Service Bus queue so large files never block a request."""

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.countries.pack_schema import CsvMapping
from app.db import get_db
from app.deps import country_ctx, owned
from app.models import Account, Import, Transaction, User
from app.models import CsvMapping as SavedMapping
from app.schemas import ImportOut, ImportPreviewOut, ImportResultOut, ImportRowOut, SavedMappingOut
from app.services.categorise import Categoriser
from app.services.csv_import import CsvFormatError, decode, parse_csv

router = APIRouter(tags=["imports"])
PREVIEW_ROWS = 20


def _resolve_mapping(
    db: Session,
    user: User,
    account: Account,
    preset_id: str | None,
    mapping_json: str | None,
    saved_mapping_id: uuid.UUID | None,
) -> tuple[CsvMapping, str]:
    given = sum(x is not None for x in (preset_id, mapping_json, saved_mapping_id))
    if given != 1:
        raise HTTPException(422, "Send exactly one of preset_id, mapping or saved_mapping_id")
    if preset_id:
        ctx = country_ctx(db, account.country_code)
        for p in ctx.csv_presets:
            if p.id == preset_id:
                return p.mapping, f"preset:{p.id}"
        raise HTTPException(422, f"No preset {preset_id!r} for {ctx.name}")
    if saved_mapping_id:
        saved = owned(db, SavedMapping, saved_mapping_id, user)
        return CsvMapping.model_validate(saved.mapping), f"saved:{saved.name}"
    try:
        return CsvMapping.model_validate(json.loads(mapping_json)), "mapping"
    except (ValueError, ValidationError) as e:
        raise HTTPException(422, f"Invalid mapping: {e}") from None


async def _read(file: UploadFile) -> str:
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is larger than 5 MB")
    try:
        return decode(data)
    except CsvFormatError as e:
        raise HTTPException(422, str(e)) from None


def _parse(text: str, mapping: CsvMapping):
    try:
        return parse_csv(text, mapping)
    except CsvFormatError as e:
        raise HTTPException(422, str(e)) from None


@router.post("/v1/imports/preview", response_model=ImportPreviewOut)
async def preview_import(
    file: UploadFile = File(...),
    account_id: uuid.UUID = Form(...),
    preset_id: str | None = Form(default=None),
    mapping: str | None = Form(default=None, description="CsvMapping as JSON"),
    saved_mapping_id: uuid.UUID | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Parse the file and show what would be imported. Nothing is saved."""
    account = owned(db, Account, account_id, user)
    m, _ = _resolve_mapping(db, user, account, preset_id, mapping, saved_mapping_id)
    result = _parse(await _read(file), m)
    cat = Categoriser(db, user.id, country_ctx(db, account.country_code))
    rows = [
        ImportRowOut(
            line=r.line,
            date=r.date,
            description=r.description,
            amount=r.amount,
            category_id=cat.category_for(r.description),
        )
        for r in result.rows[:PREVIEW_ROWS]
    ]
    return ImportPreviewOut(
        header=result.header, rows=rows, total_lines=result.total_lines, parsed=len(result.rows), errors=result.errors
    )


@router.post("/v1/imports", response_model=ImportResultOut, status_code=status.HTTP_201_CREATED)
async def run_import(
    file: UploadFile = File(...),
    account_id: uuid.UUID = Form(...),
    preset_id: str | None = Form(default=None),
    mapping: str | None = Form(default=None),
    saved_mapping_id: uuid.UUID | None = Form(default=None),
    save_mapping_as: str | None = Form(default=None, max_length=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import the file into the account. Safe to repeat: rows already imported are skipped."""
    account = owned(db, Account, account_id, user)
    m, source = _resolve_mapping(db, user, account, preset_id, mapping, saved_mapping_id)
    result = _parse(await _read(file), m)
    if not result.rows and result.errors:
        raise HTTPException(422, {"message": "No rows could be read with this mapping", "errors": result.errors})

    imp = Import(
        user_id=user.id,
        account_id=account.id,
        filename=(file.filename or "upload.csv")[:255],
        source=source,
        rows_total=result.total_lines,
        rows_failed=len(result.errors),
    )
    db.add(imp)
    db.flush()
    cat = Categoriser(db, user.id, country_ctx(db, account.country_code))
    values = [
        {
            "id": uuid.uuid4(),
            "user_id": user.id,
            "account_id": account.id,
            "date": r.date,
            "description": r.description,
            "amount": r.amount,
            "category_id": cat.category_for(r.description),
            "notes": "",
            "import_id": imp.id,
            "dedupe_hash": r.dedupe_hash,
        }
        for r in result.rows
    ]
    inserted = 0
    if values:
        stmt = (
            insert(Transaction)
            .values(values)
            .on_conflict_do_nothing(index_elements=[Transaction.account_id, Transaction.dedupe_hash])
            .returning(Transaction.id)
        )
        inserted = len(db.execute(stmt).all())
    imp.rows_imported = inserted
    imp.rows_duplicate = len(values) - inserted
    if save_mapping_as and source == "mapping":
        existing = db.scalar(
            select(SavedMapping).where(SavedMapping.user_id == user.id, SavedMapping.name == save_mapping_as)
        )
        if existing:
            existing.mapping = m.model_dump()
        else:
            db.add(SavedMapping(user_id=user.id, name=save_mapping_as, mapping=m.model_dump()))
    db.commit()
    return ImportResultOut(import_=ImportOut.model_validate(imp), errors=result.errors)


@router.get("/v1/imports", response_model=list[ImportOut])
def list_imports(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Import).where(Import.user_id == user.id).order_by(Import.created_at.desc())).all()


@router.get("/v1/csv-mappings", response_model=list[SavedMappingOut])
def list_saved_mappings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(SavedMapping).where(SavedMapping.user_id == user.id).order_by(SavedMapping.name)).all()


@router.delete("/v1/csv-mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_mapping(mapping_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, SavedMapping, mapping_id, user))
    db.commit()
