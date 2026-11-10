"""Dashboard password hashing and the cookie-signing secret."""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy.orm import Session

from app.core.models import Setting

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def session_secret(session: Session) -> str:
    """Generated once and kept in the DB, so restarts don't log the user out."""
    row = session.get(Setting, "session_secret")
    if row is None:
        row = Setting(key="session_secret", value={"value": secrets.token_urlsafe(48)})
        session.add(row)
        session.commit()
    return row.value["value"]
