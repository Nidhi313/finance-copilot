"""Who is making the request.

Local development runs as one demo user so the app works with no sign-in setup.
Production uses Microsoft Entra External ID tokens; that mode is wired in before
the first deployment and refuses to run until then, so the demo mode can never
reach a public environment by accident."""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User


def get_current_user(db: Session = Depends(get_db)) -> User:
    if settings.auth_mode != "dev":
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Only dev sign-in exists so far")
    if settings.environment not in {"local", "test", "ci"}:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Dev sign-in is disabled outside local")
    user = db.scalar(select(User).where(User.email == settings.demo_user_email))
    if user is None:
        user = User(email=settings.demo_user_email, display_name="Demo user", home_currency="AUD")
        db.add(user)
        db.commit()
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.email not in settings.admin_emails:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user
