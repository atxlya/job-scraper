"""Single-user login. See docs/DESIGN.md §7 (Access) and plan decisions D3/D4."""

import time
from collections import deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.deps import bump_session_epoch, password_tag, require_user, session_epoch
from app.core.secrets import verify_password

MAX_FAILURES = 5
WINDOW_S = 600
BLOCK_S = 60


class LoginThrottle:
    """5 wrong passwords within 10 minutes block every login attempt for 60 s."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._failures: deque[float] = deque()

    def _recent(self) -> deque[float]:
        cutoff = self._clock() - WINDOW_S
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()
        return self._failures

    def blocked(self) -> bool:
        recent = self._recent()
        return len(recent) >= MAX_FAILURES and self._clock() < recent[-1] + BLOCK_S

    def fail(self) -> None:
        self._failures.append(self._clock())

    def reset(self) -> None:
        self._failures.clear()


class LoginBody(BaseModel):
    password: str


router = APIRouter(prefix="/api")
private = APIRouter(prefix="/api", dependencies=[Depends(require_user)])


@router.post("/login", status_code=204)
def login(body: LoginBody, request: Request) -> Response:
    password_hash = request.app.state.settings.dashboard_password_hash
    if not password_hash:
        raise HTTPException(
            503, "No dashboard password is set. Run: python -m app.cli set-password"
        )
    throttle: LoginThrottle = request.app.state.throttle
    if throttle.blocked():
        raise HTTPException(429, "Too many wrong passwords. Try again in a minute.")
    if not verify_password(password_hash, body.password):
        throttle.fail()
        raise HTTPException(401, "Wrong password")
    throttle.reset()
    with request.app.state.session_factory() as s:
        epoch = session_epoch(s)
    request.session.update({"user": "me", "pw": password_tag(request), "epoch": epoch})
    return Response(status_code=204)


@private.post("/logout", status_code=204)
def logout(request: Request, everywhere: bool = False) -> Response:
    """Ends this browser's session; with ?everywhere=true, every device's."""
    if everywhere:
        with request.app.state.session_factory() as s:
            bump_session_epoch(s)
    request.session.clear()
    return Response(status_code=204)


@private.get("/openapi.json", include_in_schema=False)
def openapi(request: Request) -> dict:
    return request.app.openapi()


@private.get("/docs", include_in_schema=False)
def docs() -> Response:
    from fastapi.openapi.docs import get_swagger_ui_html  # noqa: PLC0415

    return get_swagger_ui_html(openapi_url="/api/openapi.json", title="job-scraper API")


@private.get("/me")
def me() -> dict:
    return {"ok": True}
