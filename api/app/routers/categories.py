import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.deps import country_ctx, owned
from app.models import Account, Category, CategoryRule, Transaction, User
from app.schemas import ApplyRulesOut, CategoryIn, CategoryOut, RuleIn, RuleOut
from app.services.categorise import Categoriser

router = APIRouter(tags=["categories"])


def visible_category(db: Session, category_id: uuid.UUID, user: User) -> Category:
    cat = db.get(Category, category_id)
    if cat is None or (cat.user_id is not None and cat.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return cat


@router.get("/v1/categories", response_model=list[CategoryOut])
def list_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cats = db.scalars(
        select(Category).where(or_(Category.user_id.is_(None), Category.user_id == user.id)).order_by(Category.name)
    ).all()
    return [CategoryOut(id=c.id, name=c.name, kind=c.kind, is_default=c.user_id is None) for c in cats]


@router.post("/v1/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cat = Category(user_id=user.id, name=body.name.strip(), kind=body.kind)
    db.add(cat)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a category with that name") from None
    return CategoryOut(id=cat.id, name=cat.name, kind=cat.kind)


@router.delete("/v1/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Category, category_id, user))
    db.commit()


@router.get("/v1/category-rules", response_model=list[RuleOut])
def list_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(CategoryRule).where(CategoryRule.user_id == user.id).order_by(CategoryRule.priority)).all()


@router.post("/v1/category-rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    visible_category(db, body.category_id, user)
    rule = CategoryRule(
        user_id=user.id, pattern=body.pattern.strip(), category_id=body.category_id, priority=body.priority
    )
    db.add(rule)
    db.commit()
    return rule


@router.delete("/v1/category-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, CategoryRule, rule_id, user))
    db.commit()


@router.post("/v1/category-rules/apply", response_model=ApplyRulesOut)
def apply_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Categorise every uncategorised transaction using your rules and the country defaults."""
    rows = db.execute(
        select(Transaction, Account.country_code)
        .join(Account, Account.id == Transaction.account_id)
        .where(Transaction.user_id == user.id, Transaction.category_id.is_(None))
    ).all()
    categorisers: dict[str, Categoriser] = {}
    updated = 0
    for txn, cc in rows:
        if cc not in categorisers:
            categorisers[cc] = Categoriser(db, user.id, country_ctx(db, cc))
        cid = categorisers[cc].category_for(txn.description)
        if cid:
            txn.category_id = cid
            updated += 1
    db.commit()
    return {"categorised": updated, "still_uncategorised": len(rows) - updated}
