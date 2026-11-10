"""Job list, filters and (Task 5+) job detail and tagging."""

from collections import Counter
from datetime import datetime, timedelta
from typing import Annotated

import pycountry
from fastapi import APIRouter, Depends, Query
from sqlalchemy import (
    Integer,
    Select,
    String,
    and_,
    column,
    false,
    func,
    or_,
    select,
    text,
    type_coerce,
)
from sqlalchemy.orm import Session

from app.api.deps import get_session, now, require_user
from app.api.schemas import FilterOptions, JobCard, JobFilters, JobPage, Option
from app.core.eligibility import eligibility
from app.core.models import Company, Job, JobAnalysis, JobUserState, UTCDateTime
from app.pipeline.derived import fts_query

router = APIRouter(prefix="/api", dependencies=[Depends(require_user)])

POSTED = {"1d": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30)}
Sess = Annotated[Session, Depends(get_session)]
Now = Annotated[datetime, Depends(now)]


def _newest():
    return func.coalesce(Job.posted_at, Job.first_seen_at, type_=UTCDateTime)


def _has_quote():
    return and_(
        JobAnalysis.eligibility == "warn",
        JobAnalysis.eligibility_quote.is_not(None),
        JobAnalysis.eligibility_quote != "",
    )


def _has_country(code: str):
    # country_codes is stored as JSON text like ["IN", "US"]; code is validated [A-Z]{2}.
    return type_coerce(Job.country_codes, String).like(f'%"{code}"%')


def _elig_condition(status: str):
    """SQL twin of app.core.eligibility.eligibility(), using the stored degree flag."""
    if status == "warn":
        return or_(Job.degree_only.is_not(None), _has_quote())
    if status == "ok":
        return and_(JobAnalysis.eligibility == "ok", Job.degree_only.is_(None))
    return and_(
        Job.degree_only.is_(None),
        or_(
            JobAnalysis.id.is_(None),
            JobAnalysis.eligibility.not_in(["ok", "warn"]),
            and_(JobAnalysis.eligibility == "warn", ~_has_quote()),
        ),
    )


def _base(view: str, dismissed: bool) -> Select:
    """Jobs in a view, with closed and dismissed jobs hidden per plan D6."""
    stmt = (
        select(Job, Company, JobAnalysis, JobUserState)
        .join(Company, Company.id == Job.company_id)
        .outerjoin(JobAnalysis, JobAnalysis.job_id == Job.id)
        .outerjoin(JobUserState, JobUserState.job_id == Job.id)
        .where(or_(Job.state == "open", JobUserState.tag.in_(["liked", "applied"])))
    )
    if view == "tech":
        stmt = stmt.where(Job.is_tech.is_(True), Job.is_internship.is_(True))
    if not dismissed:
        stmt = stmt.where(or_(JobUserState.tag.is_(None), JobUserState.tag != "dismissed"))
    return stmt


def _filtered(f: JobFilters, at: datetime) -> Select:
    stmt = _base(f.view, f.dismissed)
    if f.company:
        stmt = stmt.where(Company.slug.in_(f.company))
    if f.loc == "india":
        stmt = stmt.where(or_(_has_country("IN"), Job.remote_type == "remote"))
    elif f.loc != "anywhere":
        stmt = stmt.where(_has_country(f.loc))
    if f.elig:
        stmt = stmt.where(or_(*(_elig_condition(e) for e in f.elig)))
    if f.posted != "any":
        stmt = stmt.where(_newest() >= at - POSTED[f.posted])
    if f.tag:
        conds = [JobUserState.tag == t for t in f.tag if t != "untagged"]
        if "untagged" in f.tag:
            conds.append(JobUserState.tag.is_(None))
        stmt = stmt.where(or_(*conds))
    if f.q:
        match = fts_query(f.q)
        if match is None:
            stmt = stmt.where(false())
        else:
            hits = (
                text("SELECT rowid FROM jobs_fts WHERE jobs_fts MATCH :fq")
                .bindparams(fq=match)
                .columns(column("rowid", Integer))
            )
            stmt = stmt.where(Job.id.in_(hits))
    return stmt


def _location(locations: list[str]) -> str:
    shown = " · ".join(locations[:2])
    return shown + (f" +{len(locations) - 2}" if len(locations) > 2 else "")


def card(job: Job, company: Company, analysis: JobAnalysis | None, us: JobUserState | None):
    return JobCard(
        id=job.id,
        company=company.name,
        company_slug=company.slug,
        title=job.title,
        location=_location(job.locations or []),
        posted_at=job.posted_at,
        first_seen_at=job.first_seen_at,
        is_new=us is None or us.seen_at is None,
        eligibility=eligibility(job, analysis).status,
        tag=us.tag if us else None,
        closed=job.state == "closed",
    )


@router.get("/jobs")
def list_jobs(
    f: Annotated[JobFilters, Query()],
    s: Sess,
    at: Now,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> JobPage:
    stmt = _filtered(f, at)
    total = s.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = s.execute(stmt.order_by(_newest().desc(), Job.id.desc()).offset(offset).limit(limit))
    return JobPage(total=total or 0, items=[card(*r) for r in rows], loaded_at=at)


def _country_name(code: str) -> str:
    c = pycountry.countries.get(alpha_2=code)
    return getattr(c, "common_name", None) or (c.name if c else code)


@router.get("/filters")
def filter_options(s: Sess, view: Annotated[str, Query(pattern="^(tech|all)$")] = "tech"):
    base = _base(view, dismissed=False).with_only_columns(
        Company.slug, Company.name, Job.country_codes
    )
    companies: Counter[tuple[str, str]] = Counter()
    countries: Counter[str] = Counter()
    for slug, name, codes in s.execute(base):
        companies[(slug, name)] += 1
        countries.update(set(codes or []))
    return FilterOptions(
        companies=[
            Option(value=slug, label=name, count=n)
            for (slug, name), n in sorted(companies.items(), key=lambda x: (-x[1], x[0][1]))
        ],
        countries=[
            Option(value=code, label=_country_name(code), count=n)
            for code, n in sorted(countries.items(), key=lambda x: (-x[1], x[0]))
        ],
    )
