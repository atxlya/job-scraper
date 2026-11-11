"""Amazon (amazon.jobs search JSON). Amazon has no working internship filter: it ignores
job_type[], business_category[] and team[], and `is_intern` is always null (2026-11-11).
So two overlapping queries cover it: "intern" worldwide, and every India job (plan D7).
"""

import json
from datetime import UTC, datetime

from app.adapters.base import Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.adapters.text import join_sections
from app.http.client import PoliteClient

SEARCH = "https://www.amazon.jobs/en/search.json"
BASE = "https://www.amazon.jobs"
PAGE = 100
HITS_CAP = 10000  # amazon.jobs stops counting here


@register
class AmazonAdapter:
    name = "amazon"
    listing_has_details = True

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        jobs: dict[str, RawJob] = {}
        total, complete = 0, mode == "full"
        for query in cfg["queries"]:
            seen_before = set(jobs)
            mine: set[str] = set()
            offset, hits, short = 0, None, False
            while True:
                data = await self._page(client, query, offset)
                hits = int(data["hits"]) if hits is None else hits
                for row in data["jobs"]:
                    job = _to_raw(row)
                    mine.add(job.external_id)
                    jobs.setdefault(job.external_id, job)
                if not data["jobs"]:
                    short = offset < hits  # the site stopped before its own total
                    break
                offset += PAGE
                if mode == "incremental" or hits >= HITS_CAP:
                    break
                if offset >= hits:
                    break
            # A job an earlier query already returned is counted once, so the run's
            # found/total check stays exact while the queries overlap.
            total += hits - len(mine & seen_before)
            complete = complete and hits < HITS_CAP and offset >= hits and not short
        return ListingResult(jobs=list(jobs.values()), reported_total=total, complete=complete)

    async def _page(self, client: PoliteClient, query: dict, offset: int) -> dict:
        params = {**query, "offset": offset, "result_limit": PAGE, "sort": "recent"}
        resp = await client.get(SEARCH, params=params)
        resp.raise_for_status()
        try:
            data = resp.json()
            ok = isinstance(data["jobs"], list) and data["hits"] is not None
        except (ValueError, KeyError, TypeError) as e:
            raise ParseError("amazon: unexpected shape") from e
        if data.get("error") or not ok:
            raise ParseError(f"amazon: search error {data.get('error')!r}")
        return data

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        return job  # the listing carries the whole posting; closing uses the 2-sweep rule


def _to_raw(p: dict) -> RawJob:
    if not p.get("id_icims") or not p.get("title") or not p.get("job_path"):
        raise ParseError("amazon: job without id/title/path")
    places = []
    for raw in p.get("locations") or []:
        try:
            places.append(json.loads(raw) if isinstance(raw, str) else raw)
        except ValueError:
            continue
    locations = [x["normalizedLocation"] for x in places if x.get("normalizedLocation")]
    codes = {x["countryIso2a"] for x in places if x.get("countryIso2a")}
    if not locations and p.get("normalized_location"):
        locations = [p["normalized_location"]]
    if not codes:
        codes = set(country_codes(locations))
    posted = None
    if p.get("posted_date"):
        try:
            posted = datetime.strptime(p["posted_date"], "%B %d, %Y").replace(tzinfo=UTC)
        except ValueError:
            posted = None
    flags = {}
    if p.get("is_intern"):
        flags["intern"] = True
    if p.get("university_job"):
        flags["university"] = True
    return RawJob(
        external_id=str(p["id_icims"]),
        title=p["title"].strip(),
        url=BASE + p["job_path"],
        apply_url=p.get("url_next_step"),
        locations=locations,
        country_codes=sorted(codes),
        employment_type=p.get("job_schedule_type"),
        posted_at=posted,
        description_html=join_sections(
            [
                (None, p.get("description")),
                ("Basic qualifications", p.get("basic_qualifications")),
                ("Preferred qualifications", p.get("preferred_qualifications")),
            ]
        ),
        platform_flags=flags,
    )
