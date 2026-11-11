"""Spire2Grow career portals (Myntra): a Flutter app over a public JSON API.

The app first asks which workspace its domain belongs to, then sends that id as a
`WorkspaceId` header on every call. Search answers carry the full description.
"""

import time

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.adapters.text import from_ms
from app.http.client import PoliteClient

API = "https://io.spire2grow.com/ies/v1/p"
PAGE_SIZE = 100
MAX_PAGES = 50
_REMOTE = {"HYBRID": "hybrid", "REMOTE": "remote"}


@register
class Spire2GrowAdapter:
    name = "spire2grow"
    listing_has_details = True

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        headers = await _headers(client, cfg)
        jobs: dict[str, RawJob] = {}
        total = None
        for page in range(1, MAX_PAGES + 1):
            # The site builds this URL by hand, trailing "&" included.
            resp = await client.get(
                f"{API}/requisition/_search?page={page}&size={PAGE_SIZE}&", headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict) or not isinstance(data.get("entities"), list):
                raise ParseError("spire2grow: search answer without entities")
            total = data.get("total")
            for entity in data["entities"]:
                job = _job(cfg, entity)
                jobs.setdefault(job.external_id, job)
            if not data["entities"] or total is None or len(jobs) >= total:
                break
        complete = mode == "full" and total is not None and len(jobs) >= total
        return ListingResult(jobs=list(jobs.values()), reported_total=total, complete=complete)

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        headers = await _headers(client, cfg)
        resp = await client.get(f"{API}/requisition/displayId/{job.external_id}", headers=headers)
        if resp.status_code == 404:
            return GONE  # {"errorMessages":["Requisition not found in elasticsearch index…"]}
        resp.raise_for_status()
        return _job(cfg, resp.json())


async def _headers(client: PoliteClient, cfg: dict) -> dict[str, str]:
    resp = await client.get(f"{API}/workspaceId", params={"domain": cfg["domain"]})
    resp.raise_for_status()
    workspace = resp.text.strip().strip('"')
    if not workspace:
        raise ParseError(f"spire2grow: no workspace for {cfg['domain']}")
    return {
        "WorkspaceId": workspace,
        "language": "en",
        "workflowId": f"WFU_{int(time.time() * 1000)}",
        "Accept": "application/json",
    }


def _job(cfg: dict, e: dict) -> RawJob:
    if not isinstance(e, dict) or not e.get("displayId") or not e.get("jobTitle"):
        raise ParseError("spire2grow: requisition without displayId/jobTitle")
    places = [loc for loc in e.get("jobLocation") or [] if isinstance(loc, dict)]
    locations = [p["fqLocationName"] for p in places if p.get("fqLocationName")]
    countries = country_codes([p["country"] for p in places if p.get("country")])
    kind = (e.get("employmentType") or "").upper()
    flags = {"intern": True} if "INTERN" in kind or "APPRENTICE" in kind else {}
    return RawJob(
        external_id=str(e["displayId"]),
        title=e["jobTitle"].strip(),
        url=f"https://{cfg['domain']}/jobs/{e['displayId']}",
        locations=locations,
        country_codes=countries,
        remote_type=_REMOTE.get((e.get("jobType") or "").upper()),
        employment_type=kind.lower() or None,
        posted_at=from_ms((e.get("jobPosting") or {}).get("startDate")),
        description_html=e.get("jobDescription") or None,
        platform_flags=flags,
    )
