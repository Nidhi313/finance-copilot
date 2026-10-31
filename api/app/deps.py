import uuid
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.countries.context import CountryContext, UnknownCountry, get_country_context
from app.models import User

M = TypeVar("M")


def owned(db: Session, model: type[M], obj_id: uuid.UUID, user: User) -> M:
    """Load a row that belongs to the current user, or 404. Never 403, so other
    users' ids cannot be probed."""
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "user_id", None) != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


def country_ctx(db: Session, code: str) -> CountryContext:
    try:
        return get_country_context(db, code)
    except UnknownCountry:
        raise HTTPException(422, f"Unknown country code {code}") from None
