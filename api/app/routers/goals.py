import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.deps import owned
from app.models import Account, Goal, User
from app.schemas import GoalIn, GoalOut
from app.services.accounts import balances
from app.services.fx import FxTable, MissingRate

router = APIRouter(prefix="/v1/goals", tags=["goals"])


def _progress(db: Session, g: Goal, fx: FxTable) -> GoalOut:
    out = GoalOut.model_validate(g)
    current: Decimal | None = g.saved_amount
    if g.account_id:
        acc = db.get(Account, g.account_id)
        try:
            current = fx.convert(balances(db, [acc.id])[acc.id], acc.currency, g.currency)
        except MissingRate:
            current = None
    out.current = current
    if current is not None and g.target_amount > 0:
        out.percent = min(Decimal(100), current / g.target_amount * 100).quantize(Decimal("0.1"))
        if g.target_date and g.target_date > date.today():
            months_left = max(
                1, (g.target_date.year - date.today().year) * 12 + g.target_date.month - date.today().month
            )
            out.monthly_needed = (max(Decimal(0), g.target_amount - current) / months_left).quantize(Decimal("0.01"))
    return out


@router.get("", response_model=list[GoalOut])
def list_goals(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fx = FxTable(db)
    return [_progress(db, g, fx) for g in db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.name))]


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
def create_goal(body: GoalIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.account_id:
        owned(db, Account, body.account_id, user)
    g = Goal(user_id=user.id, **body.model_dump())
    db.add(g)
    db.commit()
    return _progress(db, g, FxTable(db))


@router.put("/{goal_id}", response_model=GoalOut)
def update_goal(
    goal_id: uuid.UUID, body: GoalIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    g = owned(db, Goal, goal_id, user)
    if body.account_id:
        owned(db, Account, body.account_id, user)
    for k, v in body.model_dump().items():
        setattr(g, k, v)
    db.commit()
    return _progress(db, g, FxTable(db))


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Goal, goal_id, user))
    db.commit()
