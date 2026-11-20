"""Job list, filters, job detail, tags, notes and "seen"."""

import asyncio
import csv
import io
import logging
import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Annotated
from urllib.parse import urljoin, urlparse

import httpx
import nh3
import pycountry
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from selectolax.lexbor import LexborHTMLParser
from sqlalchemy import (
    Integer,
    Select,
    String,
    and_,
    column,
    false,
    func,
    literal,
    or_,
    select,
    text,
    true,
    type_coerce,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

import app.adapters  # noqa: F401  (registers adapters)
from app.adapters.base import ADAPTERS, GONE
from app.api.deps import IST, get_session, ist_midnight, now, require_user
from app.api.place import place
from app.api.schemas import (
    Application,
    Change,
    FilterOptions,
    JobCard,
    JobDetail,
    JobFilters,
    JobPage,
    MarkSeenBody,
    NoteBody,
    Option,
    StageBody,
    Step,
    TagBody,
    TagEvent,
)
from app.core import tags
from app.core.categories import LABEL as CATEGORY_LABEL
from app.core.eligibility import eligibility
from app.core.models import (
    Company,
    Job,
    JobAnalysis,
    JobChange,
    JobUserState,
    Source,
    TagHistory,
    UTCDateTime,
)
from app.http.client import RobotsDisallowed, RobotsUnavailable
from app.pipeline.derived import fts_query
from app.pipeline.ingest import apply_detail, mark_gone, raw_from_job

# The dashboard waits on this fetch: a site retrying 5xx with back-off could hold it
# for minutes (20 s timeout x 5 tries), so give up after this long.
DETAIL_BUDGET_S = 30.0

router = APIRouter(prefix="/api", dependencies=[Depends(require_user)])
log = logging.getLogger(__name__)

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
    """Jobs in a view, with closed and dismissed jobs hidden per plan D6, and applications
    that ended in a rejection: those live on the Applications page, as a history."""
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
    return stmt.where(or_(JobUserState.stage.is_(None), JobUserState.stage != "rejected"))


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
    if f.new == "today":
        stmt = stmt.where(Job.first_seen_at >= ist_midnight(at))
    if f.tag:
        conds = [JobUserState.tag == t for t in f.tag if t != "untagged"]
        if "untagged" in f.tag:
            conds.append(JobUserState.tag.is_(None))
        stmt = stmt.where(or_(*conds))
    if f.category:
        stmt = stmt.where(Job.category.in_(f.category))
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
    where = place(job.locations or [], job.country_codes or [], job.remote_type)
    return JobCard(
        id=job.id,
        company=company.name,
        company_slug=company.slug,
        title=job.title,
        location=_location(job.locations or []),
        place=where.text,
        country=where.country,
        more_places=where.more,
        india=where.india,
        remote=where.remote,
        posted_at=job.posted_at,
        first_seen_at=job.first_seen_at,
        is_new=us is None or us.seen_at is None,
        eligibility=eligibility(job, analysis).status,
        tag=us.tag if us else None,
        stage=us.stage if us and us.tag == "applied" else None,
        closed=job.state == "closed",
        category=job.category if job.category in CATEGORY_LABEL else None,
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
    max_id = s.scalar(select(func.max(Job.id))) or 0
    return JobPage(total=total or 0, items=[card(*r) for r in rows], loaded_at=at, max_id=max_id)


# --- CSV export ---------------------------------------------------------------------------

EXPORT_BATCH = 500  # rows read from SQLite, and written out, at a time
# Made to be read by an AI when sorting jobs and writing resumes: what the job is, and
# links back to it. Tags, dates and eligibility are filters in the dashboard instead.
EXPORT_HEADER = [
    "Company",
    "Title",
    "Category",
    "Locations",
    "Apply URL",
    "Dashboard URL",
    "About",
    "Responsibilities",
    "Requirements",
    "Preferred",
    "Description",
]
SECTION_KEYS = ("responsibilities", "requirements", "preferred")
CELL_MAX = 32_000  # Excel and Google Sheets cut a cell at 32,767 characters
# A spreadsheet runs a cell starting with one of these as a formula (OWASP's list). Titles
# and locations come from other people's sites, so every text cell is guarded.
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: str | None) -> str:
    v = value or ""
    return f"'{v}" if v.startswith(FORMULA_START) else v


BLOCK_END = re.compile(r"(?i)<br\s*/?>|</(?:p|div|li|h[1-6]|tr|ul|ol|table|section)\s*>")
LIST_ITEM = re.compile(r"(?i)<li\b[^>]*>")


def _plain(html: str | None) -> str:
    """A description as readable text: a line per paragraph, heading or bullet, with
    bold and links kept inline (html_to_text puts every tag on its own line)."""
    if not html:
        return ""
    html = LIST_ITEM.sub("\\g<0>• ", BLOCK_END.sub("\\g<0>\n", html))
    text = LexborHTMLParser(html).text(separator="")
    lines = (re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _long(text: str) -> str:
    text = text.strip()
    return _cell(text if len(text) <= CELL_MAX else text[: CELL_MAX - 1] + "…")


def _sections(analysis: JobAnalysis | None) -> list[str]:
    """Gemini's summary, when the job has been read: about, then three bullet lists."""
    sec = (analysis.sections if analysis else None) or {}
    about = sec.get("about") if isinstance(sec.get("about"), str) else ""
    lists = [sec.get(k) if isinstance(sec.get(k), list) else [] for k in SECTION_KEYS]
    bullets = ["\n".join(f"• {x}" for x in items if isinstance(x, str)) for items in lists]
    return [_long(about), *(_long(b) for b in bullets)]


def _description(job: Job, summary: list[str]) -> str:
    """The full posting only when Gemini hasn't summarised the job: the summary holds what
    matters, and the rest (company blurb, benefits, legal text) is most of the file."""
    return "" if any(summary) else _long(_plain(job.description_html))


def _csv_rows(sf, stmt: Select, dashboard: str) -> Iterator[bytes]:
    """Yields the file in pieces, one batch of rows each. Opens its own session: the
    request's is closed before a streamed body is sent. The session holds rows weakly, so
    a batch is freed once written."""
    out = io.StringIO()
    writer = csv.writer(out)
    out.write("\ufeff")  # BOM: Excel otherwise reads UTF-8 as Latin-1
    writer.writerow(EXPORT_HEADER)
    with sf() as s:
        result = s.execute(stmt.execution_options(yield_per=EXPORT_BATCH))
        for batch in result.partitions():
            for job, company, analysis, _us in batch:
                summary = _sections(analysis)
                writer.writerow(
                    [
                        _cell(company.name),
                        _cell(job.title),
                        CATEGORY_LABEL.get(job.category or "", ""),
                        _cell("; ".join(job.locations or [])),
                        _cell(job.apply_url or job.url),
                        f"{dashboard}/jobs/{job.id}",
                        *summary,
                        _description(job, summary),
                    ]
                )
            yield out.getvalue().encode("utf-8")
            out.seek(0)
            out.truncate()
    if out.tell():
        yield out.getvalue().encode("utf-8")


@router.get("/jobs.csv")
def export_jobs(f: Annotated[JobFilters, Query()], request: Request, at: Now) -> StreamingResponse:
    """The jobs the list shows for these filters, in the list's order, as a CSV file."""
    stmt = _filtered(f, at).order_by(_newest().desc(), Job.id.desc())
    base = (request.app.state.settings.dashboard_url or str(request.base_url)).rstrip("/")
    name = f"jobs-{at.astimezone(IST).date().isoformat()}.csv"
    return StreamingResponse(
        _csv_rows(request.app.state.session_factory, stmt, base),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


def _country_name(code: str) -> str:
    c = pycountry.countries.get(alpha_2=code)
    return getattr(c, "common_name", None) or (c.name if c else code)


@router.get("/filters")
def filter_options(s: Sess, view: Annotated[str, Query(pattern="^(tech|all)$")] = "tech"):
    # Counted in SQL: at ~40k jobs, reading every row into Python is the slow part.
    ids = _base(view, dismissed=False).with_only_columns(Job.id).scalar_subquery()
    company_rows = s.execute(
        select(Company.slug, Company.name, func.count(Job.id))
        .join(Job, Job.company_id == Company.id)
        .where(Job.id.in_(ids))
        .group_by(Company.id)
    )
    code = func.json_each(Job.country_codes).table_valued("value")
    category_rows = s.execute(
        select(Job.category, func.count(Job.id))
        .where(Job.id.in_(ids), Job.category.is_not(None))
        .group_by(Job.category)
    )
    country_rows = s.execute(
        select(code.c.value, func.count(func.distinct(Job.id)))
        .select_from(Job)
        .join(code, true())
        .where(Job.id.in_(ids))
        .group_by(code.c.value)
    )
    return FilterOptions(
        companies=[
            Option(value=slug, label=name, count=n)
            for slug, name, n in sorted(company_rows, key=lambda r: (-r[2], r[1]))
        ],
        countries=[
            Option(value=c, label=_country_name(c), count=n)
            for c, n in sorted(country_rows, key=lambda r: (-r[1], r[0]))
        ],
        categories=[
            Option(value=c, label=CATEGORY_LABEL[c], count=n)
            for c, n in sorted(category_rows, key=lambda r: (-r[1], r[0]))
            if c in CATEGORY_LABEL
        ],
    )


# --- detail -----------------------------------------------------------------------------

ALLOWED_TAGS = {
    "p", "br", "ul", "ol", "li", "b", "strong", "i", "em", "h2", "h3", "h4", "a",
    "table", "tr", "td", "th", "thead", "tbody",
}  # fmt: skip


def sanitise(html: str, base_url: str | None = None) -> str:
    """Posting HTML is third-party: keep structure, drop scripts, handlers and odd links.
    Links open in a new tab, and relative ones point at the posting's site, not ours."""

    def absolute(tag: str, attr: str, value: str) -> str:
        if tag == "a" and attr == "href" and base_url:
            return urljoin(base_url, value)
        return value

    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes={"a": {"href"}},
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer nofollow",
        attribute_filter=absolute,
        set_tag_attribute_values={"a": {"target": "_blank"}},
    )


def _load(s: Session, job_id: int):
    row = s.execute(
        select(Job, Company, JobAnalysis, JobUserState)
        .join(Company, Company.id == Job.company_id)
        .outerjoin(JobAnalysis, JobAnalysis.job_id == Job.id)
        .outerjoin(JobUserState, JobUserState.job_id == Job.id)
        .where(Job.id == job_id)
    ).first()
    if row is None:
        raise HTTPException(404, "Job not found")
    return row


def job_detail(s: Session, job_id: int) -> JobDetail:
    job, company, analysis, us = _load(s, job_id)
    e = eligibility(job, analysis)
    sections = analysis.sections if analysis and any(analysis.sections.values()) else None
    changes = s.scalars(
        select(JobChange).where(JobChange.job_id == job_id).order_by(JobChange.changed_at)
    )
    history = list(
        s.scalars(select(TagHistory).where(TagHistory.job_id == job_id).order_by(TagHistory.id))
    )
    return JobDetail(
        **card(job, company, analysis, us).model_dump(),
        external_id=job.external_id,
        locations=job.locations or [],
        employment_type=job.employment_type,
        remote_type=job.remote_type,
        url=job.url,
        apply_url=job.apply_url,
        degree=e.degree,
        quote=e.quote,
        checking=e.checking,
        unclear=e.unclear,
        unchecked=e.unchecked,
        tech_internship=job.is_tech is True and job.is_internship is True,
        sections=sections,
        description_html=sanitise(job.description_html, job.url)
        if sections is None and job.description_html
        else None,
        has_description=bool(job.description_html),
        note=us.note if us else None,
        changes=[Change(at=c.changed_at, fields=c.fields) for c in changes],
        tag_history=[
            TagEvent(
                at=h.at,
                from_tag=h.from_tag,
                to_tag=h.to_tag,
                from_stage=h.from_stage,
                to_stage=h.to_stage,
                event_date=h.event_date,
                note=h.note,
            )
            for h in history
        ],
        steps=_steps(history),
    )


def _steps(history: list[TagHistory]) -> list[Step]:
    return [Step(**vars(st)) for st in tags.application_steps(history)]


def _user_state(s: Session, job_id: int) -> JobUserState:
    _load(s, job_id)  # 404 for unknown jobs
    return tags.user_state(s, job_id)


@router.post("/jobs/mark-seen")
def mark_all_seen(body: MarkSeenBody, s: Sess, at: Now) -> dict:
    """Marks every job up to the list's max_id as seen, sparing ones that came later (D7)."""
    stmt = sqlite_insert(JobUserState).from_select(
        ["job_id", "seen_at"],
        select(Job.id, literal(at, UTCDateTime)).where(Job.id <= body.up_to_id),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["job_id"],
        set_={"seen_at": stmt.excluded.seen_at},
        where=JobUserState.seen_at.is_(None),
    )
    marked = s.execute(stmt).rowcount
    s.commit()
    return {"marked": marked}


@router.get("/jobs/{job_id}")
def get_job(job_id: int, s: Sess) -> JobDetail:
    return job_detail(s, job_id)


@router.post("/jobs/{job_id}/seen", status_code=204)
def mark_seen(job_id: int, s: Sess, at: Now) -> Response:
    us = _user_state(s, job_id)
    us.seen_at = us.seen_at or at
    s.commit()
    return Response(status_code=204)


@router.put("/jobs/{job_id}/tag")
def set_tag(job_id: int, body: TagBody, s: Sess, at: Now) -> JobDetail:
    _load(s, job_id)  # 404 for unknown jobs
    tags.set_tag(s, job_id, body.tag, at, event_date=body.event_date, note=body.note)
    s.commit()
    return job_detail(s, job_id)


@router.put("/jobs/{job_id}/stage")
def set_stage(job_id: int, body: StageBody, s: Sess, at: Now) -> JobDetail:
    _load(s, job_id)  # 404 for unknown jobs
    try:
        tags.set_stage(s, job_id, body.stage, at, event_date=body.event_date, note=body.note)
    except tags.NotApplied as e:
        s.rollback()
        raise HTTPException(409, "Mark it Applied first.") from e
    s.commit()
    return job_detail(s, job_id)


@router.get("/applications")
def applications(s: Sess) -> list[Application]:
    """Every applied job, whatever its stage or state (closed ones too), newest step first."""
    rows = s.execute(
        select(Job, Company, JobUserState)
        .join(Company, Company.id == Job.company_id)
        .join(JobUserState, JobUserState.job_id == Job.id)
        .where(JobUserState.tag == "applied")
    ).all()
    by_job: dict[int, list[TagHistory]] = {}
    for h in s.scalars(
        select(TagHistory)
        .where(TagHistory.job_id.in_([job.id for job, _, _ in rows]))
        .order_by(TagHistory.id)
    ):
        by_job.setdefault(h.job_id, []).append(h)
    out = []
    for job, company, us in rows:
        steps = _steps(by_job.get(job.id, []))
        out.append(
            Application(
                id=job.id,
                company=company.name,
                company_slug=company.slug,
                title=job.title,
                closed=job.state == "closed",
                stage=us.stage,
                steps=steps,
                # An applied job with no history (tagged before history existed): first seen.
                last_on=steps[-1].on if steps else job.first_seen_at.astimezone(tags.IST).date(),
            )
        )
    return sorted(out, key=lambda a: (a.last_on, a.id), reverse=True)


@router.put("/jobs/{job_id}/note", status_code=204)
def set_note(job_id: int, body: NoteBody, s: Sess) -> Response:
    us = _user_state(s, job_id)
    us.note = body.note or None
    s.commit()
    return Response(status_code=204)


@router.post("/jobs/{job_id}/description")
async def fetch_description(job_id: int, request: Request, at: Now) -> JobDetail:
    """Fetch a missing description now (plan D8). Never holds a DB write across the fetch."""
    sf = request.app.state.session_factory
    with sf() as s:
        job = _load(s, job_id)[0]
        if job.description_html:
            return job_detail(s, job_id)
        src = s.scalars(
            select(Source).where(Source.id.in_(job.source_ids or []), Source.enabled.is_(True))
        ).first()
        if src is None or src.adapter not in ADAPTERS:
            raise HTTPException(409, "This job's source is turned off, so it can't be fetched.")
        adapter, cfg, raw = ADAPTERS[src.adapter](), dict(src.config), raw_from_job(job)
        host = urlparse(job.url).hostname or "the site"
    try:
        detail = await asyncio.wait_for(
            adapter.fetch_detail(request.app.state.client, cfg, raw), DETAIL_BUDGET_S
        )
    except TimeoutError as e:
        raise HTTPException(504, f"{host} took too long to answer. Try again later.") from e
    except (RobotsUnavailable, httpx.HTTPError) as e:
        raise HTTPException(502, f"Couldn't reach {host}. Try again later.") from e
    except RobotsDisallowed as e:
        raise HTTPException(409, "This site's robots.txt doesn't allow fetching the page.") from e
    except Exception as e:  # ParseError, or an adapter tripping on an unexpected page
        log.warning("on-demand fetch for job %s failed: %r", job_id, e)
        raise HTTPException(502, f"Couldn't read the page from {host}. Try again later.") from e
    with sf() as s:
        job = s.get(Job, job_id)
        if detail is GONE:
            mark_gone(s, job, at)
        else:
            apply_detail(s, job, detail, at)
        s.commit()
        return job_detail(s, job_id)
