"""Columns and the search index that are computed from a job's own fields.

Kept in Python (not SQL triggers) because the search body is the description's
plain text, and the degree flag comes from the title rules in classify.py.
"""

import re
from collections.abc import Iterable

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.core.models import Company, Job
from app.llm.queue import html_to_text
from app.pipeline.classify import degree_only

FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5("
    "title, company, body, tokenize='unicode61 remove_diacritics 2')"
)
_WORD_KEEP = re.compile(r"[^\w+#.]", re.UNICODE)


def create_fts(engine: Engine) -> None:
    """For databases made with metadata.create_all (tests, fresh dev DBs)."""
    with engine.begin() as conn:
        conn.execute(text(FTS_DDL))


def refresh_derived(session: Session, job_ids: Iterable[int]) -> None:
    ids = list(job_ids)
    if not ids:
        return
    names = dict(session.execute(select(Company.id, Company.name)).all())
    for job in session.scalars(select(Job).where(Job.id.in_(ids))):
        job.degree_only = degree_only(job.title)
        session.execute(text("DELETE FROM jobs_fts WHERE rowid = :id"), {"id": job.id})
        session.execute(
            text("INSERT INTO jobs_fts(rowid, title, company, body) VALUES (:id, :t, :c, :b)"),
            {
                "id": job.id,
                "t": job.title,
                "c": names.get(job.company_id, ""),
                "b": html_to_text(job.description_html),
            },
        )
    session.flush()


def fts_query(q: str) -> str | None:
    """User text -> an FTS5 query of quoted prefix terms. Never passes FTS syntax through."""
    words = [_WORD_KEEP.sub("", w) for w in q.split()]
    words = [w for w in words if w]
    if not words:
        return None
    return " ".join(f'"{w}"*' for w in words)
