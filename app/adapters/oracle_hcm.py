"""Oracle Recruiting Cloud (HCM) career sites: Amex, JPMorgan, Oracle, Dell, KPMG, Honeywell."""

from datetime import UTC, datetime

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.http.client import PoliteClient

PAGE = 25
INCREMENTAL_PAGES = 3
API = "/hcmRestApi/resources/latest"


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


@register
class OracleHcmAdapter:
    name = "oracle_hcm"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        max_pages = INCREMENTAL_PAGES if mode == "incremental" else None
        jobs: dict[str, RawJob] = {}
        offset, pages, total = 0, 0, None
        while True:
            reqs, count = await self._page(client, cfg, offset)
            total = count if total is None else total
            for r in reqs:
                job = self._to_raw(cfg, r)
                jobs.setdefault(job.external_id, job)
            pages += 1
            offset += PAGE
            if not reqs or offset >= total or (max_pages and pages >= max_pages):
                break
        complete = mode == "full" and offset >= (total or 0)
        return ListingResult(jobs=list(jobs.values()), reported_total=total, complete=complete)

    async def _page(self, client, cfg, offset) -> tuple[list[dict], int]:
        finder = (
            f"findReqs;siteNumber={cfg['site']},limit={PAGE},offset={offset},"
            "sortBy=POSTING_DATES_DESC"
        )
        url = (
            f"https://{cfg['host']}{API}/recruitingCEJobRequisitions?onlyData=true"
            f"&expand=requisitionList.secondaryLocations&finder={finder}"
        )
        resp = await client.get(url)
        resp.raise_for_status()
        try:
            items = resp.json()["items"]
            head = items[0]
            return head["requisitionList"], int(head["TotalJobsCount"])
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ParseError(f"oracle_hcm {cfg['site']}: unexpected shape") from e

    def _to_raw(self, cfg: dict, r: dict) -> RawJob:
        if not r.get("Id") or not r.get("Title"):
            raise ParseError(f"oracle_hcm {cfg['site']}: requisition without Id/Title")
        locations = [r["PrimaryLocation"]] if r.get("PrimaryLocation") else []
        locations += [s.get("Name") for s in r.get("secondaryLocations") or [] if s.get("Name")]
        codes = set(country_codes(locations))
        if r.get("PrimaryLocationCountry"):
            codes.add(r["PrimaryLocationCountry"])
        base = cfg.get("public_host", cfg["host"])
        return RawJob(
            external_id=str(r["Id"]),
            title=r["Title"],
            url=f"https://{base}/hcmUI/CandidateExperience/en/sites/{cfg['site']}/job/{r['Id']}",
            locations=locations,
            country_codes=sorted(codes),
            posted_at=_date(r.get("PostedDate")),
        )

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        url = (
            f"https://{cfg['host']}{API}/recruitingCEJobRequisitionDetails?expand=all"
            f'&onlyData=true&finder=ById;Id="{job.external_id}",siteNumber={cfg["site"]}'
        )
        resp = await client.get(url)
        if resp.status_code == 404:
            return GONE
        resp.raise_for_status()
        items = resp.json().get("items") or []
        if not items:
            return GONE
        d = items[0]
        parts = [
            d.get("ExternalDescriptionStr"),
            d.get("ExternalResponsibilitiesStr"),
            d.get("ExternalQualificationsStr"),
        ]
        return job.model_copy(
            update={
                "description_html": "\n".join(p for p in parts if p) or None,
                "posted_at": _date(d.get("ExternalPostedStartDate")) or job.posted_at,
                "employment_type": d.get("RequisitionType") or job.employment_type,
                "apply_url": job.url,
            }
        )
