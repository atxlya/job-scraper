"""RippleHire career sites (LTIMindtree): a form-POST search that answers JSON.

The tenant's public career-site token comes from the company's own careers links. The
list is newest first and has no description or date; the job detail call has both. A
missing job answers 500, which is an error here, never "gone" (an outage looks the same).
"""

import json
from datetime import UTC, datetime

from app.adapters.base import Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.adapters.text import join_sections
from app.http.client import PoliteClient

PAGE_SIZE = 100
MAX_PAGES = 100


@register
class RippleHireAdapter:
    name = "ripplehire"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        jobs: dict[str, RawJob] = {}
        total = None
        for page in range(MAX_PAGES):
            data = await _search(client, cfg, page)
            total = data["totalJobCount"]
            rows = data["jobVoList"] or []
            for row in rows:
                job = _row(cfg, row)
                jobs.setdefault(job.external_id, job)
            if mode != "full" or not rows or len(jobs) >= total:
                break
        complete = mode == "full" and total is not None and len(jobs) >= total
        return ListingResult(jobs=list(jobs.values()), reported_total=total, complete=complete)

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        resp = await client.get(
            f"https://{cfg['host']}/candidate/candidatejobdetail",
            params={
                "token": cfg["token"],
                "jobSeq": job.external_id,
                "source": "CAREERSITE",
                "lang": "en",
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()  # a missing job answers 500: an error, not GONE
        vo = _json(resp).get("jobVO")
        if not isinstance(vo, dict):
            raise ParseError("ripplehire: job detail without jobVO")
        posted = None
        if vo.get("jobPostingDate"):
            try:
                posted = datetime.strptime(vo["jobPostingDate"], "%d-%b-%Y").replace(tzinfo=UTC)
            except ValueError as e:
                raise ParseError(f"ripplehire: unreadable date {vo['jobPostingDate']!r}") from e
        return job.model_copy(
            update={
                "description_html": join_sections(
                    [(None, vo.get("jobDesc")), ("Skills", vo.get("jobSkills"))]
                ),
                "posted_at": posted or job.posted_at,
                "employment_type": vo.get("jobTypeCustom3") or job.employment_type,
            }
        )


async def _search(client: PoliteClient, cfg: dict, page: int) -> dict:
    params = {
        "page": page,
        "search": "*:*",
        "token": cfg["token"],
        "source": "CAREERSITE",
        "pagesize": PAGE_SIZE,
    }
    if cfg.get("geo"):
        params["geo"] = cfg["geo"]
    resp = await client.post_form(
        f"https://{cfg['host']}/candidate/candidatejobsearch",
        {"careerSiteUrlParams": json.dumps(params), "lang": "en"},
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    data = _json(resp)
    if "jobVoList" not in data or not isinstance(data.get("totalJobCount"), int):
        raise ParseError("ripplehire: search answer without jobVoList/totalJobCount")
    return data


def _json(resp) -> dict:
    try:
        data = resp.json()
    except ValueError as e:
        raise ParseError("ripplehire: answer is not JSON") from e
    if not isinstance(data, dict):
        raise ParseError("ripplehire: answer is not a JSON object")
    return data


def _row(cfg: dict, row: dict) -> RawJob:
    seq = str(row.get("jobSeq") or "")
    if not seq or not row.get("jobTitle"):
        raise ParseError("ripplehire: job row without jobSeq/jobTitle")
    locations = [p.strip() for p in (row.get("locations") or "").split(",") if p.strip()]
    countries = ["IN"] if cfg.get("geo") == "India" else country_codes(locations)
    return RawJob(
        external_id=seq,
        title=row["jobTitle"].strip(),
        url=(
            f"https://{cfg['host']}/candidate/?token={cfg['token']}"
            f"&lang=en&source=CAREERSITE#detail/job/{seq}"
        ),
        locations=locations,
        country_codes=countries,
    )
