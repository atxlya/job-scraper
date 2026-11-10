"""Workday career sites (public CXS JSON API). Config: see docs/companies.md."""

from datetime import UTC, datetime
from typing import Any

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.http.client import PoliteClient

PAGE = 20
CAP = 2000  # Workday stops counting here; larger listings must be split by facet
INCREMENTAL_PAGES = 3
HEADERS = {"Accept": "application/json"}


@register
class WorkdayAdapter:
    name = "workday"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        if mode == "incremental":
            applied = dict(cfg.get("intern_facets") or {})
            search = "" if applied else cfg.get("intern_search", "")
            jobs, total, _ = await self._pages(client, cfg, applied, search, INCREMENTAL_PAGES)
            return ListingResult(jobs=jobs, reported_total=total, complete=False)

        seen: dict[str, RawJob] = {}
        total, complete = await self._crawl(
            client, cfg, {}, list(cfg.get("split_facets", [])), seen
        )
        return ListingResult(jobs=list(seen.values()), reported_total=total, complete=complete)

    async def _crawl(self, client, cfg, applied: dict, splits: list[str], seen: dict):
        first = await self._post(client, cfg, applied, "", 0)
        total = int(first["total"])
        if total >= CAP and splits:
            param, rest = splits[0], splits[1:]
            values = _facet_values(first.get("facets", []), param)
            if values:
                for value_id in values:
                    await self._crawl(client, cfg, {**applied, param: [value_id]}, rest, seen)
                return None, True
        jobs, _, complete = await self._pages(client, cfg, applied, "", None, first=first)
        for j in jobs:
            seen.setdefault(j.external_id, j)
        return total, complete and total < CAP

    async def _pages(self, client, cfg, applied, search, max_pages, first=None):
        data = first or await self._post(client, cfg, applied, search, 0)
        total = int(data["total"])  # only page 1 carries the real total
        jobs = self._postings(cfg, data)
        offset, pages = PAGE, 1
        while offset < total and (max_pages is None or pages < max_pages):
            data = await self._post(client, cfg, applied, search, offset)
            if not data["jobPostings"]:
                break
            jobs.extend(self._postings(cfg, data))
            offset += PAGE
            pages += 1
        unique = list({j.external_id: j for j in jobs}.values())  # listings shift between pages
        return unique, total, offset >= total

    async def _post(self, client, cfg, applied, search, offset) -> dict[str, Any]:
        url = f"https://{cfg['host']}/wday/cxs/{cfg['tenant']}/{cfg['site']}/jobs"
        body = {"appliedFacets": applied, "limit": PAGE, "offset": offset, "searchText": search}
        resp = await client.post_json(url, body, headers=HEADERS)
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as e:
            raise ParseError(f"workday {cfg['tenant']}: not JSON") from e
        if not isinstance(data, dict) or "jobPostings" not in data or "total" not in data:
            raise ParseError(f"workday {cfg['tenant']}: unexpected shape")
        return data

    def _postings(self, cfg: dict, data: dict) -> list[RawJob]:
        """Workday sometimes lists postings with only bulletFields (no title or link).
        Those are skipped; a page where every posting is like that is a format change."""
        postings = data["jobPostings"]
        usable = [p for p in postings if p.get("externalPath") and p.get("title")]
        if postings and not usable:
            raise ParseError(f"workday {cfg['tenant']}: no posting has a path/title")
        return [self._to_raw(cfg, p) for p in usable]

    def _to_raw(self, cfg: dict, p: dict) -> RawJob:
        path = p["externalPath"]
        bullets = p.get("bulletFields") or []
        locations = [p["locationsText"]] if p.get("locationsText") else []
        return RawJob(
            external_id=bullets[0] if bullets else path,
            title=p["title"],
            url=f"https://{cfg['host']}/{cfg['site']}{path}",
            locations=locations,
            country_codes=country_codes(locations),
            employment_type=None,
        )

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        path = job.url.split(f"/{cfg['site']}", 1)[1]
        url = f"https://{cfg['host']}/wday/cxs/{cfg['tenant']}/{cfg['site']}{path}"
        resp = await client.get(url, headers=HEADERS)
        if resp.status_code == 404:
            return GONE
        resp.raise_for_status()
        info = resp.json().get("jobPostingInfo")
        if not info:
            raise ParseError(f"workday {cfg['tenant']}: detail without jobPostingInfo")
        locations = [info["location"]] if info.get("location") else list(job.locations)
        locations += [loc for loc in info.get("additionalLocations") or [] if loc not in locations]
        country = (info.get("country") or {}).get("descriptor")
        posted = None
        if info.get("startDate"):
            posted = datetime.fromisoformat(info["startDate"]).replace(tzinfo=UTC)
        return job.model_copy(
            update={
                "description_html": info.get("jobDescription"),
                "employment_type": info.get("timeType"),
                "posted_at": posted,
                "apply_url": info.get("externalUrl") or job.url,
                "locations": locations,
                "country_codes": country_codes(locations + ([country] if country else [])),
            }
        )


def _facet_values(facets: list[dict], param: str) -> list[str]:
    """Facet value IDs for `param`, looking inside nested groups like locationMainGroup."""
    for f in facets:
        if f.get("facetParameter") == param:
            return [v["id"] for v in f.get("values", []) if v.get("id")]
        for v in f.get("values", []):
            if v.get("facetParameter") == param:
                return [x["id"] for x in v.get("values", []) if x.get("id")]
    return []
