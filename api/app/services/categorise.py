"""Pick a category for a transaction description.

Order: the user's own rules (by priority), then the country pack's default rules.
Within each set, longer patterns win, so "uber eats" beats "uber"."""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.countries.context import CountryContext
from app.models import Category, CategoryRule


class Categoriser:
    def __init__(self, db: Session, user_id: uuid.UUID, ctx: CountryContext):
        cats = db.scalars(select(Category).where(or_(Category.user_id.is_(None), Category.user_id == user_id))).all()
        # A user's own category with the same name takes precedence over the default.
        by_name: dict[str, uuid.UUID] = {}
        for c in sorted(cats, key=lambda c: c.user_id is not None):
            by_name[c.name.lower()] = c.id
        user_rules = db.scalars(
            select(CategoryRule).where(CategoryRule.user_id == user_id).order_by(CategoryRule.priority)
        ).all()
        self.rules: list[tuple[str, uuid.UUID]] = [
            (r.pattern.lower(), r.category_id) for r in sorted(user_rules, key=lambda r: (r.priority, -len(r.pattern)))
        ]
        for r in sorted(ctx.category_rules, key=lambda r: -len(r.pattern)):
            cid = by_name.get(r.category.lower())
            if cid:
                self.rules.append((r.pattern.lower(), cid))

    def category_for(self, description: str) -> uuid.UUID | None:
        d = description.lower()
        for pattern, cid in self.rules:
            if pattern in d:
                return cid
        return None
