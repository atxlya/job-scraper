"""IBM (the search API behind ibm.com/careers/search), internships only.

careers.ibm.com sits behind an AWS WAF challenge, so it is never fetched (plan D6): the
description is the search snippet, and fetch_detail makes no request.
"""

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pycountry

from app.adapters.base import Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.adapters.text import text_to_html
from app.http.client import PoliteClient

SEARCH = "https://www-api.ibm.com/search/api/v2"
SIZE = 100
_REMOTE = {"hybrid": "hybrid", "remote": "remote", "on-site": "onsite", "onsite": "onsite"}
_FIELDS = ["_id", "title", "url", "description", "dcdate"] + [
    f"field_keyword_{n}" for n in ("08", "17", "18", "19")
]


def _body(start: int) -> dict:
    return {
        "appId": "careers",
        "scopes": ["careers2"],
        "query": {"bool": {"must": []}},
        "post_filter": {"bool": {"must": [{"term": {"field_keyword_18": "Internship"}}]}},
        "size": SIZE,
        "from": start,
        "sort": [{"dcdate": "desc"}],
        "lang": "zz",
        "localeSelector": {},
        "sm": {"query": "", "lang": "zz"},
        "_source": _FIELDS,
    }


@register
class IbmAdapter:
    name = "ibm"
    listing_has_details = True

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        jobs: dict[str, RawJob] = {}
        start, total, short = 0, None, False
        while True:
            hits, count = await self._page(client, start)
            total = count if total is None else total
            for h in hits:
                job = _to_raw(h.get("_source") or {})
                jobs.setdefault(job.external_id, job)
            if not hits:
                short = start < total  # the site stopped before its own total
                break
            start += SIZE
            if mode == "incremental" or start >= total:
                break
        complete = mode == "full" and start >= total and not short
        return ListingResult(jobs=list(jobs.values()), reported_total=total, complete=complete)

    async def _page(self, client: PoliteClient, start: int) -> tuple[list[dict], int]:
        resp = await client.post_json(SEARCH, _body(start), headers={"Accept": "application/json"})
        resp.raise_for_status()
        try:
            hits = resp.json()["hits"]
            return hits["hits"], int(hits["total"]["value"])
        except (ValueError, KeyError, TypeError) as e:
            raise ParseError("ibm: unexpected shape") from e

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        return job  # never touch careers.ibm.com (WAF challenge)


def _to_raw(s: dict) -> RawJob:
    url = s.get("url") or ""
    job_id = parse_qs(urlsplit(url).query).get("jobId", [None])[0]
    if not job_id or not s.get("title"):
        raise ParseError("ibm: hit without jobId/title")
    place = s.get("field_keyword_19") or ""
    locations = [place] if place else []
    codes = set(country_codes(locations))
    suffix = place.rsplit(", ", 1)[-1] if ", " in place else ""
    if len(suffix) == 2 and pycountry.countries.get(alpha_2=suffix):
        codes.add(suffix)
    posted = None
    if s.get("dcdate"):
        try:
            posted = datetime.fromisoformat(s["dcdate"][:10]).replace(tzinfo=UTC)
        except ValueError:
            posted = None
    return RawJob(
        external_id=job_id,
        title=s["title"],
        url=url,
        locations=locations,
        country_codes=sorted(codes),
        remote_type=_REMOTE.get((s.get("field_keyword_17") or "").lower()),
        posted_at=posted,
        description_html=text_to_html(s.get("description")),
        # The search is filtered to Internship. "snippet": the description is the search
        # summary (boilerplate), so Gemini is never asked about it.
        platform_flags={"intern": True, "snippet": True},
    )
