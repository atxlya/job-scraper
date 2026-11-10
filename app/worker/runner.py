"""Runs one source end to end: fetch → store → classify → alert → health.

Database rule: a write is never left open while waiting on the network. Each run
fetches everything first, then writes and commits in one step, then sends alerts.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import ADAPTERS, GONE, ParseError, RawJob
from app.core.models import Company, Job, JobUserState, ScrapeRun, Source
from app.http.client import PoliteClient, RobotsDisallowed
from app.llm.queue import run_analysis_batch
from app.notify.alerts import process_new, refresh_after_analysis
from app.notify.health import notify_round, record_run
from app.pipeline.classify import Keywords, classify
from app.pipeline.ingest import ingest, job_key, mark_gone

log = logging.getLogger(__name__)
RunKind = Literal["incremental", "full", "tracked"]
CONCURRENCY = 4
COUNT_TOLERANCE = 0.02


@dataclass
class Ctx:
    settings: Any
    session_factory: sessionmaker[Session]
    client: PoliteClient
    provider: Any
    pacer: Any
    channel: Any
    keywords: Keywords
    source_locks: dict[int, asyncio.Lock] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(UTC)


def _raw_from_job(job: Job) -> RawJob:
    return RawJob(
        external_id=job.external_id,
        title=job.title,
        url=job.url,
        apply_url=job.apply_url,
        locations=job.locations or [],
        platform_flags=job.platform_flags or {},
    )


def _mismatch(found: int, total: int | None) -> bool:
    return total is not None and abs(found - total) > max(2, COUNT_TOLERANCE * total)


async def run_source(ctx: Ctx, source_id: int, mode: RunKind) -> ScrapeRun:
    lock = ctx.source_locks.setdefault(source_id, asyncio.Lock())
    async with lock:  # the 30-min and nightly runs must not scrape one source at once
        return await _run_source(ctx, source_id, mode)


async def _run_source(ctx: Ctx, source_id: int, mode: RunKind) -> ScrapeRun:
    started = _now()
    with ctx.session_factory() as s:
        src = s.get(Source, source_id)
        adapter = ADAPTERS[src.adapter]()
        cfg = dict(src.config)
        known = set(s.scalars(select(Job.external_id).where(Job.company_id == src.company_id)))
        targets: list[tuple[int, RawJob]] = []
        if mode == "tracked":
            tagged = set(
                s.scalars(
                    select(JobUserState.job_id).where(JobUserState.tag.in_(["liked", "applied"]))
                )
            )
            for job in s.scalars(
                select(Job).where(Job.company_id == src.company_id, Job.state == "open")
            ):
                if source_id in job.source_ids and (job.id in tagged or src.adapter == "google"):
                    targets.append((job.id, _raw_from_job(job)))

    status, error, result, gone_ids = "ok", None, None, []
    try:
        if mode == "tracked":
            for job_id, raw in targets:
                if await adapter.fetch_detail(ctx.client, cfg, raw) is GONE:
                    gone_ids.append(job_id)
        else:
            result = await adapter.list_jobs(ctx.client, cfg, mode)
            if mode == "full" and _mismatch(len(result.jobs), result.reported_total):
                status = "partial"
                result = result.model_copy(update={"complete": False})
            fresh: list[RawJob] = []
            for raw in result.jobs:
                if job_key(raw) in known:
                    fresh.append(raw)
                    continue
                try:
                    detail = await adapter.fetch_detail(ctx.client, cfg, raw)
                except (httpx.HTTPError, ParseError, RobotsDisallowed) as e:
                    log.warning("%s: detail failed for %s: %s", src.key, raw.external_id, e)
                    fresh.append(raw)
                    continue
                if detail is not GONE:
                    fresh.append(detail)
            result = result.model_copy(update={"jobs": fresh})
    except Exception as e:  # noqa: BLE001 - one source failing must never stop the others
        log.warning("%s %s run failed: %s", src.key, mode, e)
        status, error = "failed", f"{type(e).__name__}: {e}"[:2000]

    new_ids: list[int] = []
    with ctx.session_factory() as s:
        src = s.get(Source, source_id)
        run = ScrapeRun(
            source_id=source_id, kind=mode, status=status, started_at=started, error=error
        )
        try:
            if status != "failed":
                now = _now()
                if mode == "tracked":
                    for job_id in gone_ids:
                        mark_gone(s, s.get(Job, job_id), now)
                    run.jobs_found, run.closed_count = len(targets), len(gone_ids)
                else:
                    stats = ingest(s, src, result, mode, now)
                    _classify_new(s, ctx.keywords, stats.new_ids)
                    new_ids = stats.new_ids
                    run.jobs_found = stats.seen
                    run.reported_total = result.reported_total
                    run.new_count, run.updated_count = len(stats.new_ids), len(stats.updated_ids)
                    run.closed_count = len(stats.closed_ids)
            run.finished_at = _now()
            s.add(run)
            s.flush()
            record_run(s, src, run, run.finished_at)
            s.commit()
        except Exception as e:  # noqa: BLE001
            log.exception("%s: storing results failed", source_id)
            s.rollback()
            src = s.get(Source, source_id)
            run = ScrapeRun(
                source_id=source_id,
                kind=mode,
                status="failed",
                started_at=started,
                finished_at=_now(),
                error=f"store: {type(e).__name__}: {e}"[:2000],
            )
            s.add(run)
            s.flush()
            record_run(s, src, run, run.finished_at)
            s.commit()
            new_ids = []

    if run.status != "failed" and mode != "tracked":
        with ctx.session_factory() as s:
            await process_new(s, ctx.channel, s.get(Source, source_id), new_ids, _now())
            s.commit()
    return run


def _classify_new(s: Session, kw: Keywords, job_ids: list[int]) -> None:
    for job_id in job_ids:
        job = s.get(Job, job_id)
        c = classify(_raw_from_job(job), kw)
        job.is_internship, job.is_tech = c.is_internship, c.is_tech
        if c.is_internship is False or c.is_tech is False:
            job.analysis_state = "skipped"  # not a tech internship: no Gemini call needed
    s.flush()


async def run_all(ctx: Ctx, mode: RunKind, only: str | None = None) -> list[ScrapeRun]:
    with ctx.session_factory() as s:
        q = (
            select(Source.id, Source.key)
            .join(Company, Company.id == Source.company_id)
            .where(Source.enabled.is_(True), Company.supported.is_(True))
        )
        ids = [sid for sid, key in s.execute(q) if only is None or key == only]
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(sid: int) -> ScrapeRun:
        async with sem:
            return await run_source(ctx, sid, mode)

    runs = await asyncio.gather(*(one(sid) for sid in ids))
    with ctx.session_factory() as s:
        attached = [s.get(ScrapeRun, r.id) for r in runs]
        await notify_round(s, ctx.channel, attached, _now())
        s.commit()
    return list(runs)


async def analysis_tick(ctx: Ctx) -> list[int]:
    if ctx.provider is None or ctx.pacer is None:
        return []
    now = _now()
    ids = await run_analysis_batch(
        ctx.session_factory,
        ctx.provider,
        ctx.pacer,
        model=ctx.settings.gemini_model,
        now=now,
        fresh_since=now - timedelta(minutes=35),
    )
    for job_id in ids:
        with ctx.session_factory() as s:
            await refresh_after_analysis(s, ctx.channel, job_id, _now())
            s.commit()
    return ids
