"""MyNextHire career pages (ShareChat): the careers iframe reads its jobs as JSON.

One POST lists every open job with its full text. A job that has closed answers 417
"Requested job is not accepting applications any more." Employee contact fields in the
answer (coordinator, hiring manager) are never read.
"""

import base64
import binascii
import re
from datetime import UTC, datetime

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.adapters.text import text_to_html
from app.http.client import PoliteClient

_GONE_TEXT = "not accepting applications"
# The site's own decodeString(): text that looks like base64 is decoded first.
_BASE64 = re.compile(r"^([0-9a-zA-Z+/]{4})*(([0-9a-zA-Z+/]{2}==)|([0-9a-zA-Z+/]{3}=))?$")


@register
class MyNextHireAdapter:
    name = "mynexthire"
    listing_has_details = True

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        resp = await client.post_json(
            f"https://{cfg['host']}/employer/careers/reqlist/get",
            {"source": "careers", "code": "", "filterByBuId": -1},
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        rows = resp.json().get("reqDetailsBOList") if isinstance(resp.json(), dict) else None
        if not isinstance(rows, list):
            raise ParseError("mynexthire: list answer without reqDetailsBOList")
        jobs: dict[str, RawJob] = {}
        for row in rows:
            job = _job(cfg, row)
            jobs.setdefault(job.external_id, job)
        return ListingResult(jobs=list(jobs.values()), reported_total=None, complete=mode == "full")

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        resp = await client.post_json(
            f"https://{cfg['host']}/employer/careers/req/get",
            {"source": "careers", "id": "", "code": "", "reqId": int(job.external_id)},
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 417:
            if _GONE_TEXT in resp.text.lower():
                return GONE  # "Requested job is not accepting applications any more."
            raise ParseError(f"mynexthire: 417 without the closed-job message: {resp.text[:200]}")
        resp.raise_for_status()
        bo = resp.json().get("reqDetailsBO") if isinstance(resp.json(), dict) else None
        if not isinstance(bo, dict):
            raise ParseError("mynexthire: job answer without reqDetailsBO")
        return _job(cfg, bo)


def _jd(text: str | None) -> str | None:
    if text and _BASE64.match(text):
        try:
            text = base64.b64decode(text).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            pass
    return text_to_html(text)


def _job(cfg: dict, row: dict) -> RawJob:
    if not isinstance(row, dict) or row.get("reqId") is None or not row.get("reqTitle"):
        raise ParseError("mynexthire: job without reqId/reqTitle")
    offices = [o.get("office") for o in row.get("locationList") or [] if isinstance(o, dict)]
    locations = [o.strip() for o in offices if o and o.strip()]
    if not locations and row.get("location"):
        locations = [row["location"].strip()]
    kind = row.get("employmentType") or None
    posted = None
    if row.get("approvedOn"):
        try:
            posted = datetime.strptime(row["approvedOn"], "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(UTC)
        except ValueError as e:
            raise ParseError(f"mynexthire: unreadable date {row['approvedOn']!r}") from e
    return RawJob(
        external_id=str(row["reqId"]),
        title=row["reqTitle"].strip(),
        url=f"https://{cfg['host']}/employer/jobs",  # job links are script-built (plan D9)
        locations=locations,
        country_codes=country_codes(locations) or ["IN"],
        employment_type=kind,
        posted_at=posted,
        description_html=_jd(row.get("jdDisplay")),
        platform_flags={"intern": True} if kind == "intern" else {},
    )
