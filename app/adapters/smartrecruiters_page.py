"""SmartRecruiters public job pages, read as JSON (plan D8). PhonePe and Swiggy list
their jobs on their own sites but link here, so their descriptions come from these pages.

`jobs.smartrecruiters.com` has no robots.txt. `api.smartrecruiters.com` (whose robots.txt
allows only LinkedInBot) is never used.
"""

import re
from datetime import datetime

from app.adapters.base import GONE, Gone, ParseError, RawJob, utc
from app.adapters.text import join_sections
from app.http.client import PoliteClient

SR_ID = re.compile(r"/(\d+)-[^/?#]*")
SECTIONS = ("companyDescription", "jobDescription", "qualifications", "additionalInformation")


async def fetch_posting(client: PoliteClient, url: str) -> dict | Gone:
    """A removed posting answers 404 with an HTML page (recorded 2026-11-11)."""
    resp = await client.get(url, headers={"Accept": "application/json"})
    if resp.status_code in (404, 410):
        return GONE
    resp.raise_for_status()
    try:
        posting = resp.json()
        posting["content"]["sections"]  # noqa: B018 - shape check
    except (ValueError, KeyError, TypeError) as e:
        raise ParseError(f"smartrecruiters: not a posting at {url}") from e
    if not posting.get("jobTitle"):
        raise ParseError(f"smartrecruiters: posting without jobTitle at {url}")
    return posting


def apply_posting(job: RawJob, posting: dict) -> RawJob:
    sections = posting["content"]["sections"]
    parts = [
        ((sections.get(k) or {}).get("title"), (sections.get(k) or {}).get("text"))
        for k in SECTIONS
    ]
    posted = posting.get("postedDate")
    return job.model_copy(
        update={
            "description_html": join_sections(parts),
            "posted_at": utc(datetime.fromisoformat(posted)) if posted else job.posted_at,
            "employment_type": posting.get("employmentType") or job.employment_type,
            "apply_url": posting.get("applyUrl") or job.url,
            "locations": job.locations
            or ([posting["jobAdLocation"]] if posting.get("jobAdLocation") else []),
        }
    )
