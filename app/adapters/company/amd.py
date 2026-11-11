"""AMD (iCIMS Jibe API). robots.txt asks for `crawl-delay: 5`, which PoliteClient honours.
The 30-minute run polls only the student/intern category; the full sweep reads every job."""

from datetime import datetime

from app.adapters.base import Gone, ListingResult, Mode, ParseError, RawJob, register, utc
from app.adapters.geo import country_codes
from app.adapters.text import join_sections
from app.http.client import PoliteClient

URL = "https://careers.amd.com/api/jobs"
PAGE = 100


@register
class AmdAdapter:
    name = "amd"
    listing_has_details = True

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        jobs: dict[str, RawJob] = {}
        page, total = 1, None
        while True:
            params: dict = {"page": page, "limit": PAGE}
            if mode == "incremental":
                params["categories"] = cfg["intern_category"]
            data = await self._get(client, params)
            total = int(data["totalCount"]) if total is None else total
            for row in data["jobs"]:
                job = _to_raw(cfg, row.get("data") or {})
                jobs.setdefault(job.external_id, job)
            if mode == "incremental" or not data["jobs"] or page * PAGE >= total:
                break
            page += 1
        complete = mode == "full" and page * PAGE >= total
        return ListingResult(jobs=list(jobs.values()), reported_total=total, complete=complete)

    async def _get(self, client: PoliteClient, params: dict) -> dict:
        resp = await client.get(URL, params=params)
        resp.raise_for_status()
        try:
            data = resp.json()
            if isinstance(data["jobs"], list) and data["totalCount"] is not None:
                return data
        except (ValueError, KeyError, TypeError) as e:
            raise ParseError("amd: unexpected shape") from e
        raise ParseError("amd: jobs/totalCount missing")

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        return job  # the listing carries the whole posting; closing uses the 2-sweep rule


def _to_raw(cfg: dict, d: dict) -> RawJob:
    url = (d.get("meta_data") or {}).get("canonical_url") or d.get("apply_url")
    if not d.get("req_id") or not d.get("title") or not url:
        raise ParseError("amd: job without req_id/title/link")
    locations = [d["full_location"]] if d.get("full_location") else []
    codes = set(country_codes(locations))
    if d.get("country_code"):
        codes.add(d["country_code"])
    posted = None
    if d.get("posted_date"):
        try:
            posted = utc(datetime.strptime(d["posted_date"], "%Y-%m-%dT%H:%M:%S%z"))
        except ValueError:
            posted = None
    names = {c.get("name") for c in d.get("categories") or []}
    return RawJob(
        external_id=str(d["req_id"]),
        title=d["title"],
        url=url,
        apply_url=d.get("apply_url"),
        locations=locations,
        country_codes=sorted(codes),
        employment_type=d.get("employment_type"),
        posted_at=posted,
        description_html=join_sections(
            [
                (None, d.get("description")),
                ("Responsibilities", d.get("responsibilities")),
                ("Qualifications", d.get("qualifications")),
            ]
        ),
        platform_flags={"intern": True} if cfg["intern_category"] in names else {},
    )
