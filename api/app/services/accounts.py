import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Transaction


def balances(db: Session, account_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    """Opening balance plus the sum of all transactions, per account."""
    if not account_ids:
        return {}
    sums = dict(
        db.execute(
            select(Transaction.account_id, func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.account_id.in_(account_ids))
            .group_by(Transaction.account_id)
        ).all()
    )
    openings = dict(db.execute(select(Account.id, Account.opening_balance).where(Account.id.in_(account_ids))).all())
    return {aid: Decimal(openings[aid]) + Decimal(sums.get(aid, 0)) for aid in account_ids}
