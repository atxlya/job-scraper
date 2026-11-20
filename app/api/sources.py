"""Stats strip, scraper health and "Add company" (docs/DESIGN.md §3, §7)."""

import re
from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.adapters  # noqa: F401  (registers adapters)
from app.adapters.base import ADAPTERS
from app.api.deps import get_session, ist_midnight, now, require_user
from app.api.schemas import (
    AddCompany,
    AddResult,
    DetectedOut,
    LastRun,
    Night,
    RunOut,
    Schedule,
    ScheduleBody,
    SourceHealth,
    Stats,
    UrlBody,
)
from app.core.models import Company, Job, JobUserState, ScrapeRun, Source, TagHistory
from app.core.schedule import (
    TZ,
    ScheduleConfig,
    ScheduleError,
    load_schedule,
    next_daily,
    save_schedule,
)
from app.sources import detect as detection
from app.sources.checks import evaluate

router = APIRouter(prefix="/api", dependencies=[Depends(require_user)])
Sess = Annotated[Session, Depends(get_session)]
Now = Annotated[datetime, Depends(now)]
NOT_SUPPORTED = "Not a Workday, Eightfold, Oracle HCM, Lever or Greenhouse careers URL."


def _tech():
    return (Job.is_tech.is_(True), Job.is_internship.is_(True), Job.state == "open")


@router.get("/stats")
def stats(s: Sess, at: Now) -> Stats:
    midnight = ist_midnight(at)
    tags = dict(s.execute(select(JobUserState.tag, func.count()).group_by(JobUserState.tag)).all())
    rejected = s.scalar(
        select(func.count()).where(JobUserState.tag == "applied", JobUserState.stage == "rejected")
    )
    return Stats(
        new_today=s.scalar(select(func.count()).where(*_tech(), Job.first_seen_at >= midnight)),
        open_tech=s.scalar(select(func.count()).where(*_tech())),
        companies=s.scalar(
            select(func.count(func.distinct(Source.company_id))).where(Source.enabled.is_(True))
        ),
        liked=tags.get("liked", 0),
        applied=tags.get("applied", 0) - (rejected or 0),
        rejected=rejected or 0,
        last_applied_at=s.scalar(
            # The move into Applied, not a later stage step (from_tag = to_tag = "applied").
            select(func.max(TagHistory.at)).where(
                TagHistory.to_tag == "applied",
                or_(TagHistory.from_tag.is_(None), TagHistory.from_tag != "applied"),
            )
        ),
    )


NIGHTS = 14  # how many nights each source's chart covers
RUNS = 20  # how many runs a source's history shows
# Failing first, then partial runs and count-drop warnings, then OK; never run last.
_RANK = {"failing": 0, "partial": 1, "warning": 1, "ok": 2, "never_run": 3}


def _status(src: Source, last: ScrapeRun | None) -> str:
    if src.consecutive_failures:
        return "failing"
    if not src.last_success_at:
        return "never_run"
    if last and last.status == "partial":
        return "partial"
    return "warning" if src.warning_active else "ok"


def _duration(run: ScrapeRun) -> int | None:
    return int((run.finished_at - run.started_at).total_seconds()) if run.finished_at else None


def _last_run(run: ScrapeRun | None) -> LastRun | None:
    if run is None:
        return None
    return LastRun(
        kind=run.kind, status=run.status, started_at=run.started_at, duration_s=_duration(run)
    )


def _nights(s: Session, at: datetime) -> tuple[list[str], dict[tuple[int, str], Night]]:
    """The last NIGHTS IST dates, and each source's full sweep on each (the latest that day)."""
    tz = ZoneInfo(TZ)
    today = at.astimezone(tz).date()
    days = [today - timedelta(days=d) for d in range(NIGHTS - 1, -1, -1)]
    start = datetime.combine(days[0], time(), tz)
    rows = s.execute(
        select(ScrapeRun.source_id, ScrapeRun.started_at, ScrapeRun.jobs_found, ScrapeRun.status)
        .where(ScrapeRun.kind == "full", ScrapeRun.started_at >= start)
        .order_by(ScrapeRun.started_at)
    )
    found: dict[tuple[int, str], Night] = {}
    for source_id, started, count, status in rows:
        day = started.astimezone(tz).date().isoformat()
        found[(source_id, day)] = Night(day=day, count=count, status=status)
    return [d.isoformat() for d in days], found


@router.get("/sources")
def sources(s: Sess, at: Now) -> list[SourceHealth]:
    # Each source's newest run: one index seek per source on (source_id, started_at).
    newest = (
        select(ScrapeRun.id)
        .where(ScrapeRun.source_id == Source.id)
        .order_by(ScrapeRun.started_at.desc(), ScrapeRun.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    ids = select(newest).select_from(Source)
    last = {r.source_id: r for r in s.scalars(select(ScrapeRun).where(ScrapeRun.id.in_(ids)))}
    days, nights = _nights(s, at)
    rows = []
    for src, name in s.execute(select(Source, Company.name).join(Company)):
        run = last.get(src.id)
        rows.append(
            SourceHealth(
                key=src.key,
                company=name,
                adapter=src.adapter,
                origin=src.origin,
                enabled=src.enabled,
                status=_status(src, run),
                last_success_at=src.last_success_at,
                last_job_count=src.last_job_count,
                last_error=src.last_error,
                consecutive_failures=src.consecutive_failures,
                last_run=_last_run(run),
                nights=[
                    nights.get((src.id, d), Night(day=d, count=None, status=None)) for d in days
                ],
            )
        )
    return sorted(
        rows,
        key=lambda r: (
            not r.enabled,
            _RANK[r.status],
            -r.consecutive_failures,
            r.company.lower(),
            r.key,
        ),
    )


@router.get("/sources/{key}/runs")
def source_runs(key: str, s: Sess) -> list[RunOut]:
    src = s.scalar(select(Source).where(Source.key == key))
    if src is None:
        raise HTTPException(404, "No such source.")
    runs = s.scalars(
        select(ScrapeRun)
        .where(ScrapeRun.source_id == src.id)
        .order_by(ScrapeRun.started_at.desc(), ScrapeRun.id.desc())
        .limit(RUNS)
    )
    return [
        RunOut(
            kind=r.kind,
            status=r.status,
            started_at=r.started_at,
            duration_s=_duration(r),
            jobs_found=r.jobs_found,
            reported_total=r.reported_total,
            new_count=r.new_count,
            updated_count=r.updated_count,
            closed_count=r.closed_count,
            error=r.error,
        )
        for r in runs
    ]


def _schedule_out(cfg: ScheduleConfig, at: datetime) -> Schedule:
    return Schedule(
        incremental_minutes=cfg.incremental_minutes,
        full_at=cfg.full_at.strftime("%H:%M"),
        tracked_at=cfg.tracked_at.strftime("%H:%M"),
        next_full_at=next_daily(at, cfg.full_at).astimezone(UTC),
        next_tracked_at=next_daily(at, cfg.tracked_at).astimezone(UTC),
    )


@router.get("/schedule")
def schedule(s: Sess, at: Now) -> Schedule:
    return _schedule_out(load_schedule(s), at)


@router.put("/schedule")
def change_schedule(body: ScheduleBody, s: Sess, at: Now) -> Schedule:
    """Saved here; the worker picks it up within a minute (app.worker.scheduler)."""
    cfg = ScheduleConfig(
        body.incremental_minutes,
        time.fromisoformat(body.full_at),
        time.fromisoformat(body.tracked_at),
    )
    try:
        save_schedule(s, cfg)
    except ScheduleError as e:
        raise HTTPException(422, str(e)) from None
    s.commit()
    return _schedule_out(cfg, at)


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
