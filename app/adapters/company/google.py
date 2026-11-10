"""Google Careers. The job data is JSON inside the page (AF_initDataCallback 'ds:1').

robots.txt disallows `page=` URLs, so only page 1 of each query is ever read. Queries
are kept narrow (intern level × country) so each fits on page 1. Positional array
fields are undocumented and may change: any surprise raises ParseError.
"""

import json
import re
from datetime import UTC, datetime

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register
from app.http.client import PoliteClient

RESULTS = "https://www.google.com/about/careers/applications/jobs/results/"
_DS = {
    key: re.compile(rf"key: '{key}'.*?data:(\[.*?\]), sideChannel", re.S)
    for key in ("ds:0", "ds:1")
}


def _block(html: str, key: str):
    m = _DS[key].search(html)
    if not m:
        raise ParseError(f"google: no {key} block")
    try:
        return json.loads(m.group(1))
    except ValueError as e:
        raise ParseError(f"google: {key} is not JSON") from e


def _text(field) -> str | None:
    return field[1] if isinstance(field, list) and len(field) > 1 else None


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def _to_raw(j: list) -> RawJob:
    try:
        job_id, title = str(j[0]), j[1]
        locs = j[9] or []
        posted = datetime.fromtimestamp(j[12][0], tz=UTC) if j[12] else None
    except (IndexError, TypeError) as e:
        raise ParseError("google: job array shape changed") from e
    if not job_id or not title:
        raise ParseError("google: job without id/title")
    parts = [_text(j[10]), _text(j[3]), _text(j[4])]
    return RawJob(
        external_id=job_id,
        title=title,
        url=f"{RESULTS}{job_id}-{_slug(title)}",
        apply_url=j[2] if isinstance(j[2], str) else None,
        locations=[loc[0] for loc in locs if loc and loc[0]],
        country_codes=sorted({loc[5] for loc in locs if len(loc) > 5 and loc[5]}),
        posted_at=posted,
        description_html="\n".join(p for p in parts if p) or None,
        platform_flags={"intern": True},
    )


@register
class GoogleAdapter:
    name = "google"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        jobs: dict[str, RawJob] = {}
        total, fits = 0, True
        queries = cfg["queries"]
        if mode == "incremental" and cfg.get("incremental_queries"):
            queries = cfg["incremental_queries"]  # each page is ~1.2 MB; poll less often
        for q in queries:
            catch_all = bool(q.get("catch_all"))  # newest jobs anywhere; not a coverage query
            q = {k: v for k, v in q.items() if k != "catch_all"}
            params = {"q": "", **q, "sort_by": "date"}
            resp = await client.get(RESULTS, params=params)
            resp.raise_for_status()
            data = _block(resp.text, "ds:1")
            try:
                rows, count, page_size = data[0] or [], int(data[2] or 0), int(data[3] or 20)
            except (IndexError, TypeError, ValueError) as e:
                raise ParseError("google: ds:1 header changed") from e
            for row in rows:
                job = _to_raw(row)
                jobs.setdefault(job.external_id, job)
            if not catch_all:
                total += count
                fits = fits and count <= page_size
        complete = mode == "full" and fits
        return ListingResult(jobs=list(jobs.values()), reported_total=total, complete=complete)

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        resp = await client.get(job.url)
        if resp.status_code == 404:
            return GONE
        resp.raise_for_status()
        data = _block(resp.text, "ds:0")
        if not data:
            return GONE
        fresh = _to_raw(data[0])
        return job.model_copy(
            update={
                "description_html": fresh.description_html,
                "locations": fresh.locations or job.locations,
                "country_codes": fresh.country_codes or job.country_codes,
            }
        )
