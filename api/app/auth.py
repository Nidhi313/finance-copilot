"""Who is making the request.

Two modes, chosen by AUTH_MODE:

- "dev": every request is one local demo user, so the app runs with no sign-in
  setup. Refused outside local, test and CI environments.
- "entra": the web app signs people in with Microsoft Entra External ID and sends
  an access token. We verify the token's signature, issuer, audience, expiry and
  scope, then find the person by their Entra object id, creating their account on
  first sign-in. Every query is scoped to that user, so each person sees only
  their own data. Passwords never reach this API.
"""

import threading
import time

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)
METADATA_TTL_SECONDS = 24 * 60 * 60


class TokenVerifier:
    """Checks Entra access tokens against the tenant's published signing keys."""

    def __init__(self, metadata_url: str, audiences: list[str], required_scope: str):
        self.metadata_url = metadata_url
        self.audiences = audiences
        self.required_scope = required_scope
        self._lock = threading.Lock()
        self._issuer: str | None = None
        self._jwks: jwt.PyJWKClient | None = None
        self._loaded_at = 0.0

    def _load(self) -> None:
        with self._lock:
            if self._jwks and time.monotonic() - self._loaded_at < METADATA_TTL_SECONDS:
                return
            meta = httpx.get(self.metadata_url, timeout=10).raise_for_status().json()
            self._issuer = meta["issuer"]
            self._jwks = jwt.PyJWKClient(meta["jwks_uri"], cache_keys=True)
            self._loaded_at = time.monotonic()

    def verify(self, token: str) -> dict:
        self._load()
        key = self._jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=self.audiences,
            issuer=self._issuer,
            options={"require": ["exp", "iat", "iss", "aud"]},
            leeway=60,
        )
        scopes = set((claims.get("scp") or "").split())
        if self.required_scope not in scopes:
            raise jwt.InvalidTokenError(f"token is missing the {self.required_scope} scope")
        return claims


_verifier: TokenVerifier | None = None


def get_verifier() -> TokenVerifier:
    global _verifier
    if _verifier is None:
        cid = settings.entra_api_client_id
        _verifier = TokenVerifier(settings.entra_metadata_url, [cid, f"api://{cid}"], settings.entra_required_scope)
    return _verifier


def _unauthorised(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def _dev_user(db: Session) -> User:
    if settings.environment not in {"local", "test", "ci"}:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Dev sign-in is disabled outside local")
    user = db.scalar(select(User).where(User.email == settings.demo_user_email))
    if user is None:
        user = User(email=settings.demo_user_email, display_name="Demo user", home_currency="AUD")
        db.add(user)
        db.commit()
    return user


def user_from_claims(db: Session, claims: dict) -> User:
    subject = claims.get("oid") or claims.get("sub")
    if not subject:
        raise _unauthorised("Token has no user id")
    user = db.scalar(select(User).where(User.auth_subject == subject))
    if user is not None:
        return user
    email = claims.get("email") or claims.get("preferred_username")
    user = User(auth_subject=subject, email=email, display_name=(claims.get("name") or "")[:100])
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # two first requests at once, or the email is already taken
        db.rollback()
        user = db.scalar(select(User).where(User.auth_subject == subject))
        if user is None:
            user = User(auth_subject=subject, email=None, display_name=(claims.get("name") or "")[:100])
            db.add(user)
            db.commit()
    return user


def get_current_user(
    db: Session = Depends(get_db),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> User:
    if settings.auth_mode == "dev":
        return _dev_user(db)
    if creds is None:
        raise _unauthorised("Sign in required")
    try:
        claims = get_verifier().verify(creds.credentials)
    except (jwt.PyJWTError, KeyError) as e:
        raise _unauthorised(f"Invalid token: {e}") from None
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sign-in service unreachable") from None
    return user_from_claims(db, claims)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.email or user.email not in settings.admin_emails:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user
