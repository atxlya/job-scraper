"""PhonePe: one JSON file lists every requisition. Only PUBLIC rows are real openings;
each links to a SmartRecruiters job page, which carries the description."""

from app.adapters.base import Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.adapters.smartrecruiters_page import SR_ID, apply_posting, fetch_posting
from app.http.client import PoliteClient

URL = "https://www.phonepe.com/apollo/job-postings/latest.json"


@register
class PhonePeAdapter:
    name = "phonepe"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        resp = await client.get(URL)
        resp.raise_for_status()
        try:
            data = resp.json()
            rows, total = data["results"], data.get("totalCount")
        except (ValueError, KeyError, TypeError) as e:
            raise ParseError("phonepe: unexpected shape") from e
        jobs: dict[str, RawJob] = {}
        for r in rows:
            m = SR_ID.search(r.get("applyUrl") or "")
            if r.get("status") != "PUBLIC" or not m or not r.get("title"):
                continue
            locations = [r["location"]] if r.get("location") else []
            jobs.setdefault(
                m.group(1),
                RawJob(
                    external_id=m.group(1),
                    title=r["title"],
                    url=r["applyUrl"],
                    locations=locations,
                    country_codes=country_codes(locations) or ["IN"],
                    employment_type=r.get("type"),
                    platform_flags={"intern": True} if r.get("type") == "Intern" else {},
                ),
            )
        complete = mode == "full" and len(rows) == total
        return ListingResult(jobs=list(jobs.values()), reported_total=None, complete=complete)

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        posting = await fetch_posting(client, job.url)
        return posting if isinstance(posting, Gone) else apply_posting(job, posting)
