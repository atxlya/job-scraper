"""Apple (jobs.apple.com). Search and job pages embed their data as
`window.__staticRouterHydrationData = JSON.parse("…")`: a JSON string holding JSON.

jobs.apple.com has no robots.txt (/robots.txt redirects to apple.com's 404 page), so
every path is allowed. `sort=newest` puts the newest postings first (checked 2026-11-11).
"""

import json
import math
import re
from datetime import datetime

import pycountry

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register, utc
from app.adapters.geo import country_codes
from app.adapters.text import join_sections, text_to_html
from app.http.client import PoliteClient

PER_PAGE = 20
_HYDRATION = re.compile(r'window\.__staticRouterHydrationData\s*=\s*JSON\.parse\((".*?")\);', re.S)


def hydration(page: str) -> dict:
    """The page's `loaderData` (route name → data)."""
    m = _HYDRATION.search(page)
    if not m:
        raise ParseError("apple: page without hydration data")
    try:
        return json.loads(json.loads(m.group(1)))["loaderData"]
    except (ValueError, KeyError, TypeError) as e:
        raise ParseError("apple: hydration data changed") from e


@register
class AppleAdapter:
    name = "apple"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        jobs: dict[str, RawJob] = {}
        page, pages, total = 1, 1, None
        while page <= pages:
            data = await self._search(client, cfg, page, mode)
            if total is None:
                total = int(data["totalRecords"])
                pages = 1 if mode == "incremental" else max(1, math.ceil(total / PER_PAGE))
            for r in data["searchResults"]:
                job = _to_raw(cfg, r)
                jobs.setdefault(job.external_id, job)
            if not data["searchResults"]:
                break
            page += 1
        complete = mode == "full" and page > pages
        return ListingResult(jobs=list(jobs.values()), reported_total=total, complete=complete)

    async def _search(self, client: PoliteClient, cfg: dict, page: int, mode: Mode) -> dict:
        params = {"team": cfg["team"], "page": page}
        if mode == "incremental":
            params["sort"] = "newest"
        resp = await client.get(f"https://jobs.apple.com/{cfg['locale']}/search", params=params)
        resp.raise_for_status()
        data = hydration(resp.text).get("search")
        if not isinstance(data, dict) or "searchResults" not in data or "totalRecords" not in data:
            raise ParseError("apple: search data without results/total")
        return data

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        resp = await client.get(job.url)
        if resp.status_code == 404:
            return GONE
        resp.raise_for_status()
        # A removed job still answers 200, with only the "root" route's data. Any other
        # shape is a site change, not a removal.
        loader = hydration(resp.text)
        if set(loader) == {"root"}:
            return GONE
        d = (loader.get("jobDetails") or {}).get("jobsData")
        if not d:
            raise ParseError(f"apple: job page without jobsData ({sorted(loader)})")
        sections = [
            (None, text_to_html(d.get("jobSummary"))),
            ("Description", text_to_html(d.get("description"))),
            ("Responsibilities", text_to_html(d.get("responsibilities"))),
            ("Minimum qualifications", text_to_html(d.get("minimumQualifications"))),
            ("Preferred qualifications", text_to_html(d.get("preferredQualifications"))),
        ]
        return job.model_copy(
            update={
                "description_html": join_sections(sections),
                "employment_type": d.get("employmentType") or job.employment_type,
                "apply_url": job.url,
            }
        )


def _to_raw(cfg: dict, r: dict) -> RawJob:
    if not r.get("id") or not r.get("postingTitle"):
        raise ParseError("apple: result without id/title")
    locations, codes = [], set()
    for loc in r.get("locations") or []:
        parts = (
            loc.get("city") or loc.get("name"),
            loc.get("stateProvince"),
            loc.get("countryName"),
        )
        text = ", ".join(p for p in parts if p)
        if text:
            locations.append(text)
        iso3 = (loc.get("countryID") or "").removeprefix("iso-country-")
        if c := pycountry.countries.get(alpha_3=iso3) if len(iso3) == 3 else None:
            codes.add(c.alpha_2)
    codes |= set(country_codes(locations))
    posted = r.get("postDateInGMT")
    slug = r.get("transformedPostingTitle", "")
    return RawJob(
        external_id=r["id"],
        title=r["postingTitle"],
        url=f"https://jobs.apple.com/{cfg['locale']}/details/{r['id']}/{slug}",
        locations=locations,
        country_codes=sorted(codes),
        posted_at=utc(datetime.fromisoformat(posted.replace("Z", "+00:00"))) if posted else None,
        platform_flags={"intern": True},  # the team filter is "Students: Internships"
    )
