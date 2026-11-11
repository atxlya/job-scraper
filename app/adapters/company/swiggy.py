"""Swiggy: careers.swiggy.in serves every job as one compact JSON file. Each job links to
its SmartRecruiters page, which carries the description.

Keys (from the site's own script, 2026-11-11): t title, l location, c city, b business
unit, e employment type, d epoch ms, u job URL, r 1 = "Remote" tag, h 1 = "Hybrid" tag.
"""

from app.adapters.base import Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.adapters.smartrecruiters_page import apply_posting, fetch_posting, sr_id
from app.adapters.text import from_ms
from app.http.client import PoliteClient

URL = "https://careers.swiggy.in/api/jobs.json"


@register
class SwiggyAdapter:
    name = "swiggy"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        resp = await client.get(URL)
        resp.raise_for_status()
        try:
            data = resp.json()
            rows, total = data["jobs"], data.get("total")
        except (ValueError, KeyError, TypeError) as e:
            raise ParseError("swiggy: unexpected shape") from e
        jobs: dict[str, RawJob] = {}
        for r in rows:
            job_id = sr_id(r.get("u") or "")
            if not job_id or not r.get("t"):
                continue  # e.g. a role posted on another site; it has no page we can read
            locations = [r["l"]] if r.get("l") else []
            remote = "remote" if r.get("r") == 1 else "hybrid" if r.get("h") == 1 else None
            jobs.setdefault(
                job_id,
                RawJob(
                    external_id=job_id,
                    title=r["t"],
                    url=r["u"],
                    locations=locations,
                    country_codes=country_codes(locations),
                    remote_type=remote,
                    employment_type=r.get("e") or None,
                    posted_at=from_ms(r.get("d")),
                ),
            )
        if rows and not jobs:
            raise ParseError("swiggy: no job has a title and SmartRecruiters link")
        return ListingResult(
            jobs=list(jobs.values()), reported_total=total, complete=mode == "full"
        )

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        posting = await fetch_posting(client, job.url)
        return posting if isinstance(posting, Gone) else apply_posting(job, posting)
