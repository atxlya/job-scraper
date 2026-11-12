"""HTTP API and dashboard. Start with: uvicorn app.api.main:create_app --factory"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, select, text
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth, jobs, sources
from app.api.auth import LoginThrottle
from app.api.deps import logged_in
from app.core.db import make_engine, make_session_factory
from app.core.models import ScrapeRun
from app.core.secrets import session_secret
from app.core.settings import Settings, get_settings
from app.http.client import PoliteClient

SESSION_DAYS = 30
PUBLIC_API = {"/api/login"}
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def create_app(settings: Settings | None = None, web_dist: Path = WEB_DIST) -> FastAPI:
    settings = settings or get_settings()
    sf = make_session_factory(make_engine(settings.database_url))
    with sf() as s:
        secret = session_secret(s)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await app.state.client.aclose()

    # The API docs are served behind login, under /api (auth.py), not at /docs.
    app = FastAPI(
        title="job-scraper", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.settings = settings
    app.state.session_factory = sf
    app.state.client = PoliteClient(min_interval_s=settings.http_min_interval_s)
    app.state.throttle = LoginThrottle()

    @app.middleware("http")
    async def lock_api(request: Request, call_next):
        # Locked by default: an /api route added without the login dependency is still
        # closed. Runs inside SessionMiddleware (added after it, so it wraps this one).
        if request.url.path.startswith("/api") and request.url.path not in PUBLIC_API:
            if not logged_in(request):
                return JSONResponse({"detail": "Not logged in"}, status_code=401)
        return await call_next(request)

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
    app.include_router(jobs.router)
    app.include_router(sources.router)

    @app.get("/healthz")
    def healthz(request: Request) -> dict:
        with request.app.state.session_factory() as s:
            s.execute(text("SELECT 1"))
            last = s.scalar(select(func.max(ScrapeRun.finished_at)))
        return {"db": "ok", "last_run_at": last.isoformat() if last else None}

    if (web_dist / "index.html").is_file():
        _serve_web(app, web_dist.resolve())
    return app


def _serve_web(app: FastAPI, dist: Path) -> None:
    """The built React app: hashed assets cached forever, every other page gets index.html.
    Served without login, like the home-screen manifest and icons: none of it holds data."""
    index = dist / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def web(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not Found")
        f = (dist / path).resolve()
        if path and f.is_file() and f.is_relative_to(dist):
            immutable = path.startswith("assets/")
            cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
            # Not left to the system's MIME table, which a slim image may not have.
            media = "application/manifest+json" if f.suffix == ".webmanifest" else None
            return FileResponse(f, headers={"Cache-Control": cache}, media_type=media)
        if path.startswith("assets/"):
            raise HTTPException(404, "Not Found")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
