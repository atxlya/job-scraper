"""HTTP API. R1 only serves a health check; the dashboard arrives in R2."""

from fastapi import FastAPI
from sqlalchemy import func, select, text

from app.core.db import make_engine, make_session_factory
from app.core.models import ScrapeRun
from app.core.settings import get_settings

app = FastAPI(title="job-scraper")
_sf = make_session_factory(make_engine(get_settings().database_url))


@app.get("/healthz")
def healthz() -> dict:
    with _sf() as s:
        s.execute(text("SELECT 1"))
        last = s.scalar(select(func.max(ScrapeRun.finished_at)))
    return {"db": "ok", "last_run_at": last.isoformat() if last else None}
