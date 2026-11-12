"""FastAPI dependencies shared by the routers."""

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.core.models import Setting

IST = ZoneInfo("Asia/Kolkata")

# Bumped by "log out everywhere": sessions signed with an older epoch are refused.
EPOCH_KEY = "session_epoch"


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as s:
        yield s


def password_tag(request: Request) -> str:
    """A short fingerprint of the password hash: a new password ends every old session."""
    pw_hash = request.app.state.settings.dashboard_password_hash or ""
    return hashlib.sha256(pw_hash.encode()).hexdigest()[:16]


def session_epoch(s: Session) -> int:
    row = s.get(Setting, EPOCH_KEY)
    return int(row.value.get("n", 0)) if row else 0


def bump_session_epoch(s: Session) -> None:
    row = s.get(Setting, EPOCH_KEY)
    if row is None:
        s.add(Setting(key=EPOCH_KEY, value={"n": 1}))
    else:
        row.value = {"n": int(row.value.get("n", 0)) + 1}
    s.commit()


def logged_in(request: Request) -> bool:
    session = request.session
    if session.get("user") != "me" or session.get("pw") != password_tag(request):
        return False
    with request.app.state.session_factory() as s:
        return session.get("epoch", 0) == session_epoch(s)


def require_user(request: Request) -> None:
    if not logged_in(request):
        raise HTTPException(401, "Not logged in")


def now() -> datetime:
    return datetime.now(UTC)


def ist_midnight(at: datetime) -> datetime:
    """Start of today in India: where "New today" begins, for the stats tile and the filter."""
    return datetime.combine(at.astimezone(IST).date(), time(), IST)
