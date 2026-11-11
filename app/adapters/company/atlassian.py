"""Atlassian: one JSON endpoint lists every job with its full text. robots.txt doesn't
disallow /endpoint for `*`. Links point at the iCIMS job page the listing gives."""

from app.adapters.base import Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.adapters.text import join_sections
from app.http.client import PoliteClient

URL = "https://www.atlassian.com/endpoint/careers/listings"


@register
class AtlassianAdapter:
    name = "atlassian"
    listing_has_details = True

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        resp = await client.get(URL)
        resp.raise_for_status()
        try:
            rows = resp.json()
        except ValueError as e:
            raise ParseError("atlassian: not JSON") from e
        if not isinstance(rows, list):
            raise ParseError("atlassian: expected a list of jobs")
        jobs = {j.external_id: j for j in map(_to_raw, rows)}
        return ListingResult(jobs=list(jobs.values()), reported_total=None, complete=mode == "full")

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        return job  # the listing carries the whole posting; closing uses the 2-sweep rule


def _to_raw(p: dict) -> RawJob:
    portal = (p.get("portalJobPost") or {}).get("portalUrl")
    if not p.get("id") or not p.get("title") or not (portal or p.get("applyUrl")):
        raise ParseError("atlassian: job without id/title/link")
    locations = [loc for loc in p.get("locations") or [] if isinstance(loc, str) and loc]
    remote = bool(locations) and all(loc.startswith("Remote") for loc in locations)
    return RawJob(
        external_id=str(p["id"]),
        title=p["title"],
        url=portal or p["applyUrl"],
        apply_url=p.get("applyUrl"),
        locations=locations,
        country_codes=country_codes(locations),
        remote_type="remote" if remote else None,
        description_html=join_sections(
            [
                (None, p.get("overview")),
                ("Responsibilities", p.get("responsibilities")),
                ("Qualifications", p.get("qualifications")),
            ]
        ),
    )
