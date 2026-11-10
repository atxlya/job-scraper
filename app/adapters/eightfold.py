"""Eightfold career sites (NVIDIA, Microsoft, Qualcomm, Morgan Stanley, PayPal, HSBC).

Two APIs exist: the current `pcsx` one and the older `apply/v2` (still used by HSBC).
"""

from datetime import UTC, datetime

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.http.client import PoliteClient

PAGE = 10
INCREMENTAL_PAGES = 3
REMOTE = {"onsite": "onsite", "remote": "remote", "hybrid": "hybrid"}


def _ts(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC) if value else None
    except (TypeError, ValueError):
        return None


@register
class EightfoldAdapter:
    name = "eightfold"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        max_pages = INCREMENTAL_PAGES if mode == "incremental" else None
        jobs: dict[str, RawJob] = {}
        start, pages, total = 0, 0, None
        while True:
            positions, count = await self._page(client, cfg, start, mode)
            total = count if total is None else total
            for p in positions:
                job = self._to_raw(cfg, p)
                jobs.setdefault(job.external_id, job)
            pages += 1
            start += PAGE
            if not positions or start >= total or (max_pages and pages >= max_pages):
                break
        complete = mode == "full" and start >= (total or 0)
        return ListingResult(jobs=list(jobs.values()), reported_total=total, complete=complete)

    async def _page(self, client, cfg, start, mode: Mode) -> tuple[list[dict], int]:
        v2 = cfg.get("api") == "apply_v2"
        path = "/api/apply/v2/jobs" if v2 else "/api/pcsx/search"
        params = {"domain": cfg["domain"], "start": start, "sort_by": "timestamp"}
        params |= {"num": PAGE} if v2 else {"query": "", "location": ""}
        params |= cfg.get("filters") or {}
        if mode == "incremental":
            params |= cfg.get("incremental_filters") or {}
        resp = await client.get(f"https://{cfg['host']}{path}", params=params)
        resp.raise_for_status()
        try:
            body = resp.json()
        except ValueError as e:
            raise ParseError(f"eightfold {cfg['domain']}: not JSON") from e
        data = body if v2 else (body.get("data") or {})
        if "positions" not in data or "count" not in data:
            raise ParseError(f"eightfold {cfg['domain']}: unexpected shape")
        return data["positions"], int(data["count"])

    def _to_raw(self, cfg: dict, p: dict) -> RawJob:
        if cfg.get("api") == "apply_v2":
            ext, url, posted = (
                p.get("display_job_id"),
                p.get("canonicalPositionUrl"),
                p.get("t_create"),
            )
            remote = p.get("work_location_option")
        else:
            ext, posted, remote = (
                p.get("displayJobId"),
                p.get("postedTs"),
                p.get("workLocationOption"),
            )
            url = f"https://{cfg['host']}{p['positionUrl']}" if p.get("positionUrl") else None
        if not p.get("name") or not url:
            raise ParseError(f"eightfold {cfg['domain']}: position without name/url")
        locations = list(p.get("locations") or [])
        std = [s.rsplit(",", 1)[-1] for s in p.get("standardizedLocations") or []]
        codes = sorted(set(country_codes(locations)) | {c for c in std if len(c) == 2})
        return RawJob(
            external_id=str(ext or p["id"]),
            title=p["name"],
            url=url,
            locations=locations,
            country_codes=codes,
            remote_type=REMOTE.get(str(remote).lower()),
            posted_at=_ts(posted),
        )

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        position_id = job.url.rstrip("/").rsplit("/", 1)[-1]
        if cfg.get("api") == "apply_v2":
            url = f"https://{cfg['host']}/api/apply/v2/jobs/{position_id}"
            resp = await client.get(url, params={"domain": cfg["domain"]})
            if resp.status_code == 404:
                return GONE
            resp.raise_for_status()
            data = resp.json()
            if not data.get("name"):
                return GONE
            return job.model_copy(update={"description_html": data.get("job_description")})

        resp = await client.get(
            f"https://{cfg['host']}/api/pcsx/position_details",
            params={"position_id": position_id, "domain": cfg["domain"]},
        )
        body = (
            resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        if resp.status_code == 404 or body.get("status") == 404:
            return GONE
        resp.raise_for_status()
        data = body.get("data") or {}
        if not data:
            raise ParseError(f"eightfold {cfg['domain']}: empty detail")
        time_type = data.get("efcustomTextTimeType") or []
        apply = ((data.get("positionUserActions") or {}).get("applyAction") or {}).get("applyUrl")
        return job.model_copy(
            update={
                "description_html": data.get("jobDescription"),
                "employment_type": time_type[0] if time_type else None,
                "apply_url": apply or data.get("publicUrl") or job.url,
            }
        )
