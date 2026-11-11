"""Greenhouse job boards (public boards API): Razorpay, Groww, InMobi.

The full sweep asks for `content=true` (every description, HTML-escaped). The
30-minute run leaves it out to stay small; new candidates then get their description
from the per-job endpoint (plan D9).
"""

import html
from datetime import datetime

from app.adapters.base import (
    GONE,
    Gone,
    ListingResult,
    Mode,
    ParseError,
    RawJob,
    register,
    utc,
)
from app.adapters.geo import country_codes
from app.http.client import PoliteClient

API = "https://boards-api.greenhouse.io/v1/boards"


@register
class GreenhouseAdapter:
    name = "greenhouse"
    listing_has_details = True

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        params = {"content": "true"} if mode == "full" else None
        resp = await client.get(f"{API}/{cfg['board']}/jobs", params=params)
        resp.raise_for_status()
        try:
            data = resp.json()
            postings, total = data["jobs"], data.get("meta", {}).get("total")
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise ParseError(f"greenhouse {cfg['board']}: unexpected shape") from e
        if not isinstance(postings, list):
            raise ParseError(f"greenhouse {cfg['board']}: jobs is not a list")
        jobs = {j.external_id: j for j in (_to_raw(cfg, p) for p in postings)}
        return ListingResult(
            jobs=list(jobs.values()), reported_total=total, complete=mode == "full"
        )

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        resp = await client.get(f"{API}/{cfg['board']}/jobs/{job.external_id}")
        if resp.status_code == 404:
            return GONE
        resp.raise_for_status()
        try:
            return _to_raw(cfg, resp.json())
        except ValueError as e:
            raise ParseError(f"greenhouse {cfg['board']}: detail not JSON") from e


def _to_raw(cfg: dict, p: dict) -> RawJob:
    if not isinstance(p, dict) or not p.get("id") or not p.get("title"):
        raise ParseError(f"greenhouse {cfg['board']}: job without id/title")
    locations = [p["location"]["name"]] if (p.get("location") or {}).get("name") else []
    for office in p.get("offices") or []:
        name = office.get("name")
        if name and not any(name in loc for loc in locations):
            locations.append(name)
    posted = None
    if p.get("first_published"):
        posted = utc(datetime.fromisoformat(p["first_published"]))
    return RawJob(
        external_id=str(p["id"]),
        title=p["title"],
        url=p.get("absolute_url")
        or f"https://job-boards.greenhouse.io/{cfg['board']}/jobs/{p['id']}",
        locations=locations,
        country_codes=country_codes(locations),
        posted_at=posted,
        employment_type=_metadata(p, "Employment Type"),
        description_html=html.unescape(p["content"]) if p.get("content") else None,
    )


def _metadata(p: dict, name: str) -> str | None:
    for m in p.get("metadata") or []:
        if m.get("name") == name and m.get("value"):
            v = m["value"]
            return v[0] if isinstance(v, list) else str(v)
    return None
