"""Which jobs Gemini looks at next, and the batch loop that does it."""

import logging
from datetime import datetime

from selectolax.lexbor import LexborHTMLParser
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.models import Job, JobAnalysis
from app.llm.pacer import Pacer
from app.llm.provider import LlmProvider, RateLimited, validate_quotes

log = logging.getLogger(__name__)
PROMPT_VERSION = "1"


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    return LexborHTMLParser(html).text(separator="\n").strip()


def next_jobs(session: Session, limit: int, fresh_since: datetime) -> list[Job]:
    """Pending jobs that may be tech internships. New ones first, then India, then the rest."""
    candidates = session.scalars(
        select(Job).where(
            Job.analysis_state == "pending",
            Job.state == "open",
            or_(Job.is_internship.is_(None), Job.is_internship.is_(True)),
            or_(Job.is_tech.is_(None), Job.is_tech.is_(True)),
        )
    ).all()

    def rank(j: Job):
        fresh = j.first_seen_at >= fresh_since
        india = "IN" in (j.country_codes or [])
        return (0 if fresh else 1, 0 if india else 1, -j.first_seen_at.timestamp())

    return sorted(candidates, key=rank)[:limit]


async def run_analysis_batch(
    session_factory: sessionmaker[Session],
    provider: LlmProvider,
    pacer: Pacer,
    model: str,
    now: datetime,
    limit: int = 5,
    fresh_since: datetime | None = None,
) -> list[int]:
    done: list[int] = []
    with session_factory() as s:
        jobs = next_jobs(s, limit, fresh_since or now)
        for job in jobs:
            text = html_to_text(job.description_html)
            if not text:
                job.analysis_state = "skipped"
                s.commit()
                continue
            if not await pacer.acquire():
                break
            try:
                result = await provider.analyze(job.title, text)
            except RateLimited:
                pacer.on_rate_limited()
                break
            except Exception:  # noqa: BLE001 - one bad job must not stop the queue
                log.exception("analysis failed for job %s", job.id)
                job.analysis_state = "failed"
                s.commit()
                continue
            result = validate_quotes(result, text)
            existing = s.scalars(select(JobAnalysis).where(JobAnalysis.job_id == job.id)).first()
            if existing is not None:
                s.delete(existing)
                s.flush()
            s.add(
                JobAnalysis(
                    job_id=job.id,
                    model=model,
                    prompt_version=PROMPT_VERSION,
                    sections=result.sections.model_dump(),
                    eligibility=result.eligibility,
                    eligibility_quote=result.eligibility_quote,
                    created_at=now,
                )
            )
            if job.is_internship is None:
                job.is_internship = result.is_internship
            if job.is_tech is None:
                job.is_tech = result.is_tech
            job.analysis_state = "done"
            s.commit()
            done.append(job.id)
    return done
