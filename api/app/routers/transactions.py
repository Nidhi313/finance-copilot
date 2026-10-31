import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.deps import country_ctx, owned
from app.models import Account, Transaction, User
from app.routers.categories import visible_category
from app.schemas import Page, TransactionIn, TransactionOut, TransactionUpdate
from app.services.categorise import Categoriser

router = APIRouter(prefix="/v1/transactions", tags=["transactions"])


def _out(txn: Transaction, currency: str) -> TransactionOut:
    out = TransactionOut.model_validate(txn)
    out.currency = currency
    return out


@router.get("", response_model=Page[TransactionOut])
def list_transactions(
    account_id: uuid.UUID | None = None,
    country: str | None = None,
    category_id: uuid.UUID | None = None,
    uncategorised: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = (
        select(Transaction, Account.currency)
        .join(Account, Account.id == Transaction.account_id)
        .where(Transaction.user_id == user.id)
    )
    if account_id:
        q = q.where(Transaction.account_id == account_id)
    if country:
        q = q.where(Account.country_code == country.upper())
    if category_id:
        q = q.where(Transaction.category_id == category_id)
    if uncategorised:
        q = q.where(Transaction.category_id.is_(None))
    if date_from:
        q = q.where(Transaction.date >= date_from)
    if date_to:
        q = q.where(Transaction.date <= date_to)
    if search:
        q = q.where(Transaction.description.ilike(f"%{search}%"))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.execute(
        q.order_by(Transaction.date.desc(), Transaction.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return Page(items=[_out(t, cur) for t, cur in rows], total=total, limit=limit, offset=offset)


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(body: TransactionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = owned(db, Account, body.account_id, user)
    category_id = body.category_id
    if category_id:
        visible_category(db, category_id, user)
    else:
        category_id = Categoriser(db, user.id, country_ctx(db, acc.country_code)).category_for(body.description)
    txn = Transaction(
        user_id=user.id,
        account_id=acc.id,
        date=body.date,
        description=body.description,
        amount=body.amount,
        category_id=category_id,
        notes=body.notes,
    )
    db.add(txn)
    db.commit()
    return _out(txn, acc.currency)


@router.patch("/{txn_id}", response_model=TransactionOut)
def update_transaction(
    txn_id: uuid.UUID, body: TransactionUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    txn = owned(db, Transaction, txn_id, user)
    data = body.model_dump(exclude_unset=True, exclude={"clear_category"})
    if data.get("category_id"):
        visible_category(db, data["category_id"], user)
    for k, v in data.items():
        if v is not None:
            setattr(txn, k, v)
    if body.clear_category:
        txn.category_id = None
    db.commit()
    return _out(txn, db.get(Account, txn.account_id).currency)


@router.delete("/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(txn_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Transaction, txn_id, user))
    db.commit()
