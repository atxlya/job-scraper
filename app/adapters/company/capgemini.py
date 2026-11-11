"""Capgemini (jobstream search API behind capgemini.com/careers). Pages start at 1, and
rows aren't newest-first (checked 2026-11-11), so every run reads every page (plan D10)."""

import re

from app.adapters.base import Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.http.client import PoliteClient

URL = "https://cg-jobstream-api.azurewebsites.net/api/job-search"
PAGE = 100
_INTERN = re.compile(r"(?i)\bintern(ship)?s?\b|\bstudents?\b")


@register
class CapgeminiAdapter:
    name = "capgemini"
    listing_has_details = True

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        country = cfg["country_code"].split("-")[-1].upper()
        jobs: dict[str, RawJob] = {}
        page, total, short = 1, None, False
        while True:
            data = await self._get(client, cfg, page)
            total = int(data["total"]) if total is None else total
            for row in data["data"]:
                job = _to_raw(row, country)
                jobs.setdefault(job.external_id, job)
            if not data["data"]:
                short = (page - 1) * PAGE < total  # the site stopped before its own total
                break
            if page * PAGE >= total:
                break
            page += 1
        complete = mode == "full" and page * PAGE >= total and not short
        return ListingResult(jobs=list(jobs.values()), reported_total=total, complete=complete)

    async def _get(self, client: PoliteClient, cfg: dict, page: int) -> dict:
        params = {"country_code": cfg["country_code"], "page": page, "size": PAGE}
        resp = await client.get(URL, params=params)
        resp.raise_for_status()
        try:
            data = resp.json()
            if isinstance(data["data"], list) and data["total"] is not None:
                return data
        except (ValueError, KeyError, TypeError) as e:
            raise ParseError("capgemini: unexpected shape") from e
        raise ParseError("capgemini: data/total missing")

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        return job  # the listing carries the whole posting; closing uses the 2-sweep rule


def _to_raw(p: dict, country: str) -> RawJob:
    if not p.get("id") or not p.get("title") or not p.get("apply_job_url"):
        raise ParseError("capgemini: job without id/title/link")
    locations = [s.strip() for s in (p.get("location") or "").split(",") if s.strip()]
    level = f"{p.get('experience_level') or ''} {p.get('contract_type') or ''}"
    return RawJob(
        external_id=str(p["id"]),
        title=p["title"],
        url=p["apply_job_url"],
        locations=locations,
        country_codes=sorted({country, *country_codes(locations)}),
        employment_type=p.get("contract_type") or None,
        description_html=p.get("description") or None,
        platform_flags={"intern": True} if _INTERN.search(level) else {},
    )
