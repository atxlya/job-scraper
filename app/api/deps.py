"""FastAPI dependencies shared by the routers."""

from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as s:
        yield s


def require_user(request: Request) -> None:
    if request.session.get("user") != "me":
        raise HTTPException(401, "Not logged in")


def now() -> datetime:
    return datetime.now(UTC)
