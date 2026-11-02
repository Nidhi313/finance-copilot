import csv
import io
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.deps import country_ctx
from app.models import (
    Account,
    Budget,
    Category,
    CategoryRule,
    CsvMapping,
    Goal,
    Remittance,
    Transaction,
    User,
    UserCountryLink,
)
from app.schemas import CountryLinkIn, GettingStartedOut, GettingStartedStep, MeOut, MeUpdate

router = APIRouter(prefix="/v1/me", tags=["profile"])


@router.get("", response_model=MeOut)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.patch("", response_model=MeOut)
def update_me(body: MeUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.active_country_code is not None:
        if body.active_country_code not in {c.country_code for c in user.countries}:
            raise HTTPException(422, "Add the country to your profile first")
        user.active_country_code = body.active_country_code
    if body.home_currency is not None:
        user.home_currency = body.home_currency
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.onboarding_dismissed is not None:
        user.onboarding_dismissed = body.onboarding_dismissed
    db.commit()
    db.refresh(user)
    return user


@router.get("/getting-started", response_model=GettingStartedOut)
def getting_started(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A new user's first steps, each ticked off from their own data."""

    def has(model) -> bool:
        return db.scalar(select(model.user_id).where(model.user_id == user.id).limit(1)) is not None

    steps = [
        GettingStartedStep(key="countries", done=has(UserCountryLink)),
        GettingStartedStep(key="account", done=has(Account)),
        GettingStartedStep(key="transactions", done=has(Transaction)),
        GettingStartedStep(key="budget", done=has(Budget)),
        GettingStartedStep(key="transfer", done=has(Remittance)),
        GettingStartedStep(key="goal", done=has(Goal)),
    ]
    done = sum(s.done for s in steps)
    return GettingStartedOut(dismissed=user.onboarding_dismissed, steps=steps, done_count=done, total=len(steps))


@router.put("/countries/{code}", response_model=MeOut)
def link_country(code: str, body: CountryLinkIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Add a country to your profile, or change your relationship to it. Any country works."""
    ctx = country_ctx(db, code)
    link = db.get(UserCountryLink, (user.id, ctx.code))
    if link is None:
        db.add(UserCountryLink(user_id=user.id, country_code=ctx.code, relationships=list(body.relationships)))
        if user.active_country_code is None:
            user.active_country_code = ctx.code
    else:
        link.relationships = list(body.relationships)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/countries/{code}", response_model=MeOut)
def unlink_country(code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    code = code.upper()
    in_use = db.scalar(select(Account.id).where(Account.user_id == user.id, Account.country_code == code).limit(1))
    if in_use:
        raise HTTPException(status.HTTP_409_CONFLICT, "You still have accounts in this country")
    link = db.get(UserCountryLink, (user.id, code))
    if link:
        db.delete(link)
        if user.active_country_code == code:
            remaining = [c.country_code for c in user.countries if c.country_code != code]
            user.active_country_code = remaining[0] if remaining else None
        db.commit()
        db.refresh(user)
    return user


EXPORT_TABLES = [
    ("accounts", Account),
    ("transactions", Transaction),
    ("categories", Category),
    ("category_rules", CategoryRule),
    ("budgets", Budget),
    ("remittances", Remittance),
    ("goals", Goal),
    ("csv_mappings", CsvMapping),
    ("countries", UserCountryLink),
]


@router.get(
    "/export",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}, "description": "Zip of CSV files"}},
)
def export_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Everything stored about you, as a zip of CSV files."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        profile = io.StringIO()
        w = csv.writer(profile)
        w.writerow(["email", "display_name", "home_currency", "active_country_code", "created_at"])
        w.writerow([user.email or "", user.display_name, user.home_currency, user.active_country_code, user.created_at])
        zf.writestr("profile.csv", profile.getvalue())
        for name, model in EXPORT_TABLES:
            cols = [c.name for c in model.__table__.columns]
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(cols)
            for row in db.scalars(select(model).where(model.user_id == user.id)):
                w.writerow([getattr(row, c) for c in cols])
            zf.writestr(f"{name}.csv", out.getvalue())
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="my-finance-data.zip"'},
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Permanently delete your account and everything linked to it."""
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
