"""Zerodha (careers.zerodha.com). The site's own script fetches /api/jobs.

On 2026-11-11 the API answered `{"count":0,"data":[],"success":true}`, so the source is
configured with `allow_empty` (plan D3). Field names come from the site's job card
(assets/index-*.js): `name` (the card's unique key), `job_title`, `location`,
`location_type`, `description`. No real non-empty answer has been recorded yet.
"""

import re

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.http.client import PoliteClient

URL = "https://careers.zerodha.com/api/jobs"
PAGE_URL = "https://careers.zerodha.com/#job-openings"  # there are no per-job pages
_REMOTE = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite", "on-site": "onsite"}


@register
class ZerodhaAdapter:
    name = "zerodha"
    listing_has_details = True

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        rows, count = await self._rows(client)
        jobs = {j.external_id: j for j in map(_to_raw, rows)}
        return ListingResult(
            jobs=list(jobs.values()), reported_total=count, complete=mode == "full"
        )

    async def _rows(self, client: PoliteClient) -> tuple[list[dict], int | None]:
        resp = await client.get(URL)
        resp.raise_for_status()
        try:
            data = resp.json()
            ok, rows = data["success"], data["data"]
        except (ValueError, KeyError, TypeError) as e:
            raise ParseError("zerodha: unexpected shape") from e
        if ok is not True or not isinstance(rows, list):
            raise ParseError("zerodha: unsuccessful answer")
        return rows, data.get("count")

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        rows, _ = await self._rows(client)
        for job_now in map(_to_raw, rows):
            if job_now.external_id == job.external_id:
                return job_now
        return GONE


def _to_raw(p: dict) -> RawJob:
    title = (p.get("job_title") or p.get("title")) if isinstance(p, dict) else None
    if not title:
        raise ParseError("zerodha: job without job_title")
    key = p.get("name") or re.sub(r"\s+", "-", title.strip().lower())
    locations = [p["location"]] if p.get("location") else []
    return RawJob(
        external_id=str(key),
        title=title,
        url=PAGE_URL,
        locations=locations,
        country_codes=country_codes(locations) or ["IN"],
        remote_type=_REMOTE.get(str(p.get("location_type") or "").lower()),
        description_html=p.get("description") or None,
    )
