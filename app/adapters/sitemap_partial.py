"""Title-only sitemap sources (Cognizant, SAP). Their job pages sit behind Cloudflare and are
never requested: the title is the URL slug, and fetch_detail returns the job unchanged.
"""

import re

from app.adapters.base import Gone, ListingResult, Mode, RawJob, register
from app.adapters.sitemap import read_urlset
from app.adapters.text import slug_title
from app.http.client import PoliteClient


def _job_re(cfg: dict) -> re.Pattern:
    try:
        job_re = re.compile(cfg["job_url"])
    except (KeyError, TypeError, re.error) as e:
        raise ValueError(f"job_url is not a valid regex: {e}") from e
    missing = {"id", "slug"} - set(job_re.groupindex)
    if missing:
        raise ValueError(f"job_url lacks the named group(s) {sorted(missing)} (needs id and slug)")
    return job_re


@register
class SitemapPartialAdapter:
    name = "sitemap_partial"

    @staticmethod
    def validate_config(cfg: dict) -> None:
        _job_re(cfg)

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        job_re = _job_re(cfg)
        jobs: dict[str, RawJob] = {}
        for entry in await read_urlset(client, cfg["sitemap"]):
            m = job_re.match(entry.loc)
            if m is None:
                continue
            jobs.setdefault(
                m["id"],
                RawJob(
                    external_id=m["id"],
                    title=slug_title(m["slug"]),
                    url=entry.loc,
                    platform_flags={"partial": True},
                ),
            )
        return ListingResult(jobs=list(jobs.values()), reported_total=None, complete=mode == "full")

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        return job
