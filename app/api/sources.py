"""Stats strip, scraper health and "Add company" (docs/DESIGN.md §3, §7)."""

import re
from datetime import datetime, time
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.adapters  # noqa: F401  (registers adapters)
from app.adapters.base import ADAPTERS
from app.api.deps import get_session, now, require_user
from app.api.schemas import AddCompany, AddResult, DetectedOut, SourceHealth, Stats, UrlBody
from app.core.models import Company, Job, JobUserState, Source, TagHistory
from app.sources import detect as detection
from app.sources.checks import evaluate

router = APIRouter(prefix="/api", dependencies=[Depends(require_user)])
IST = ZoneInfo("Asia/Kolkata")
Sess = Annotated[Session, Depends(get_session)]
Now = Annotated[datetime, Depends(now)]
NOT_SUPPORTED = "Not a Workday, Eightfold, Oracle HCM, Lever or Greenhouse careers URL."


def _tech():
    return (Job.is_tech.is_(True), Job.is_internship.is_(True), Job.state == "open")


@router.get("/stats")
def stats(s: Sess, at: Now) -> Stats:
    midnight = datetime.combine(at.astimezone(IST).date(), time(), IST)
    tags = dict(s.execute(select(JobUserState.tag, func.count()).group_by(JobUserState.tag)).all())
    return Stats(
        new_today=s.scalar(select(func.count()).where(*_tech(), Job.first_seen_at >= midnight)),
        open_tech=s.scalar(select(func.count()).where(*_tech())),
        companies=s.scalar(
            select(func.count(func.distinct(Source.company_id))).where(Source.enabled.is_(True))
        ),
        liked=tags.get("liked", 0),
        applied=tags.get("applied", 0),
        last_applied_at=s.scalar(
            select(func.max(TagHistory.at)).where(TagHistory.to_tag == "applied")
        ),
    )


def _status(src: Source) -> str:
    if src.consecutive_failures:
        return "failing"
    return "ok" if src.last_success_at else "never_run"


@router.get("/sources")
def sources(s: Sess) -> list[SourceHealth]:
    rows = [
        SourceHealth(
            key=src.key,
            company=name,
            adapter=src.adapter,
            origin=src.origin,
            enabled=src.enabled,
            status=_status(src),
            last_success_at=src.last_success_at,
            last_job_count=src.last_job_count,
            last_error=src.last_error,
            consecutive_failures=src.consecutive_failures,
        )
        for src, name in s.execute(select(Source, Company.name).join(Company))
    ]
    order = {"failing": 0, "ok": 1, "never_run": 2}
    return sorted(rows, key=lambda r: (order[r.status], r.company.lower(), r.key))


@router.post("/sources/detect")
def detect_url(body: UrlBody) -> DetectedOut:
    d = detection.detect(body.url)
    if d is None:
        raise HTTPException(422, NOT_SUPPORTED)
    return DetectedOut(adapter=d.adapter, config=d.config, key_hint=d.key_hint)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "company"


@router.post("/sources", status_code=201)
async def add_company(body: AddCompany, request: Request) -> AddResult:
    """Test-fetch first; save the source only if the test finds real jobs (§3)."""
    d = detection.detect(body.url)
    if d is None or d.adapter not in ADAPTERS:
        raise HTTPException(422, NOT_SUPPORTED)
    key = _slug(body.company_name)
    sf = request.app.state.session_factory
    with sf() as s:
        if s.scalars(select(Source).where(Source.key == key)).first():
            raise HTTPException(409, f"A source called “{key}” already exists.")
        same = next(
            (
                src
                for src in s.scalars(select(Source).where(Source.adapter == d.adapter))
                if d.config.items() <= (src.config or {}).items()  # extra keys allowed
            ),
            None,
        )
        if same is not None:  # the same careers site under another name
            raise HTTPException(409, f"This careers site is already added as “{same.key}”.")
    try:
        result = await ADAPTERS[d.adapter]().list_jobs(
            request.app.state.client, d.config, "incremental"
        )
        problems = evaluate(result, "incremental", d.config)
    except Exception as e:  # noqa: BLE001 - any failure means "don't save", with the reason
        problems = [f"{type(e).__name__}: {e}"[:300]]
    if problems:
        raise HTTPException(422, "Test fetch failed: " + "; ".join(problems))
    with sf() as s:
        company = s.scalars(select(Company).where(Company.slug == key)).first()
        if company is None:
            company = Company(slug=key, name=body.company_name.strip())
            s.add(company)
            s.flush()
        s.add(
            Source(
                company_id=company.id,
                key=key,
                adapter=d.adapter,
                config=d.config,
                origin="dashboard",
            )
        )
        try:
            s.commit()
        except IntegrityError as e:  # a second click saved it while this one was testing
            s.rollback()
            raise HTTPException(409, f"A source called “{key}” already exists.") from e
    return AddResult(
        key=key, jobs_found=len(result.jobs), sample_titles=[j.title for j in result.jobs[:5]]
    )
