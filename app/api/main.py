"""HTTP API and dashboard. Start with: uvicorn app.api.main:create_app --factory"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy import func, select, text
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth
from app.api.auth import LoginThrottle
from app.core.db import make_engine, make_session_factory
from app.core.models import ScrapeRun
from app.core.secrets import session_secret
from app.core.settings import Settings, get_settings
from app.http.client import PoliteClient

SESSION_DAYS = 30


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    sf = make_session_factory(make_engine(settings.database_url))
    with sf() as s:
        secret = session_secret(s)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await app.state.client.aclose()

    app = FastAPI(title="job-scraper", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = sf
    app.state.client = PoliteClient(min_interval_s=settings.http_min_interval_s)
    app.state.throttle = LoginThrottle()
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        session_cookie="js_session",
        max_age=SESSION_DAYS * 24 * 3600,
        same_site="strict",
        https_only=(settings.dashboard_url or "").startswith("https://"),
    )
    app.include_router(auth.router)
    app.include_router(auth.private)

    @app.get("/healthz")
    def healthz(request: Request) -> dict:
        with request.app.state.session_factory() as s:
            s.execute(text("SELECT 1"))
            last = s.scalar(select(func.max(ScrapeRun.finished_at)))
        return {"db": "ok", "last_run_at": last.isoformat() if last else None}

    return app
