import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.deps import country_ctx, owned
from app.models import Account, User, UserCountryLink
from app.schemas import AccountIn, AccountOut, AccountUpdate
from app.services.accounts import balances

router = APIRouter(prefix="/v1/accounts", tags=["accounts"])


def _out(acc: Account, bal) -> AccountOut:
    out = AccountOut.model_validate(acc)
    out.balance = bal
    return out


@router.get("", response_model=list[AccountOut])
def list_accounts(
    country: str | None = None,
    include_archived: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(Account).where(Account.user_id == user.id).order_by(Account.country_code, Account.name)
    if country:
        q = q.where(Account.country_code == country.upper())
    if not include_archived:
        q = q.where(Account.archived.is_(False))
    accounts = db.scalars(q).all()
    bals = balances(db, [a.id for a in accounts])
    return [_out(a, bals[a.id]) for a in accounts]


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(body: AccountIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ctx = country_ctx(db, body.country_code)
    if body.type not in ctx.account_type_keys():
        raise HTTPException(422, f"Unknown account type for {ctx.name}: {body.type}")
    if db.get(UserCountryLink, (user.id, ctx.code)) is None:
        db.add(UserCountryLink(user_id=user.id, country_code=ctx.code, relationships=["holds_accounts"]))
        if user.active_country_code is None:
            user.active_country_code = ctx.code
    acc = Account(
        user_id=user.id,
        country_code=ctx.code,
        name=body.name,
        type=body.type,
        currency=body.currency or ctx.currency,
        institution=body.institution,
        opening_balance=body.opening_balance,
    )
    db.add(acc)
    db.commit()
    return _out(acc, acc.opening_balance)


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acc = owned(db, Account, account_id, user)
    return _out(acc, balances(db, [acc.id])[acc.id])


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: uuid.UUID, body: AccountUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    acc = owned(db, Account, account_id, user)
    data = body.model_dump(exclude_unset=True)
    if "type" in data and data["type"] not in country_ctx(db, acc.country_code).account_type_keys():
        raise HTTPException(422, f"Unknown account type: {data['type']}")
    for k, v in data.items():
        if v is not None:
            setattr(acc, k, v)
    db.commit()
    return _out(acc, balances(db, [acc.id])[acc.id])


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Deletes the account and all its transactions. Archive it instead to keep history."""
    db.delete(owned(db, Account, account_id, user))
    db.commit()
