"""Lever job boards (public postings API): Paytm, Meesho, CRED.

One GET returns every posting with its full description, so there is no paging and
incremental and full runs make the same request (plan D9).
"""

import re

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.adapters.text import from_ms, join_sections
from app.http.client import PoliteClient

API = "https://api.lever.co/v0/postings"
_INTERN = re.compile(r"(?i)\bintern")
_REMOTE = {"onsite", "hybrid", "remote"}


@register
class LeverAdapter:
    name = "lever"
    listing_has_details = True

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        resp = await client.get(f"{API}/{cfg['site']}", params={"mode": "json"})
        resp.raise_for_status()
        try:
            postings = resp.json()
        except ValueError as e:
            raise ParseError(f"lever {cfg['site']}: not JSON") from e
        if not isinstance(postings, list):
            raise ParseError(f"lever {cfg['site']}: expected a list of postings")
        jobs = {j.external_id: j for j in (_to_raw(cfg, p) for p in postings)}
        return ListingResult(jobs=list(jobs.values()), reported_total=None, complete=mode == "full")

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        resp = await client.get(f"{API}/{cfg['site']}/{job.external_id}", params={"mode": "json"})
        if resp.status_code == 404:
            return GONE
        resp.raise_for_status()
        try:
            return _to_raw(cfg, resp.json())
        except ValueError as e:
            raise ParseError(f"lever {cfg['site']}: detail not JSON") from e


def _to_raw(cfg: dict, p: dict) -> RawJob:
    if not isinstance(p, dict) or not p.get("id") or not p.get("text") or not p.get("hostedUrl"):
        raise ParseError(f"lever {cfg['site']}: posting without id/text/hostedUrl")
    cats = p.get("categories") or {}
    locations = cats.get("allLocations") or ([cats["location"]] if cats.get("location") else [])
    codes = set(country_codes(locations))
    if p.get("country"):
        codes.add(p["country"])
    commitment = cats.get("commitment")
    lists = [(li.get("text"), f"<ul>{li.get('content', '')}</ul>") for li in p.get("lists") or []]
    workplace = p.get("workplaceType")
    return RawJob(
        external_id=p["id"],
        title=p["text"],
        url=p["hostedUrl"],
        apply_url=p.get("applyUrl"),
        locations=locations,
        country_codes=sorted(codes),
        remote_type=workplace if workplace in _REMOTE else None,
        employment_type=commitment,
        posted_at=from_ms(p.get("createdAt")),
        description_html=join_sections(
            [(None, p.get("description")), *lists, (None, p.get("additional"))]
        ),
        platform_flags={"intern": True} if commitment and _INTERN.search(commitment) else {},
    )
