"""Barclays (Radancy/TalentBrew front end). Listing cards come as HTML inside JSON;
job pages carry a schema.org JobPosting (JSON-LD) with the full posted date.
"""

import json
import re
from datetime import UTC, datetime

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.http.client import PoliteClient

PER_PAGE = 100
_LDJSON = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


@register
class BarclaysAdapter:
    name = "barclays"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        jobs: dict[str, RawJob] = {}
        page, total, pages = 1, None, 1
        while True:
            html = await self._page(client, cfg, page)
            tree = HTMLParser(html)
            if total is None:
                total, pages = (
                    _attr_int(tree, "data-total-results"),
                    _attr_int(tree, "data-total-pages"),
                )
            for job in self._cards(cfg, tree):
                jobs.setdefault(job.external_id, job)
            if mode == "incremental" or page >= pages:
                break
            page += 1
        complete = mode == "full" and page >= pages
        return ListingResult(jobs=list(jobs.values()), reported_total=total, complete=complete)

    async def _page(self, client, cfg, page: int) -> str:
        params = {
            "CurrentPage": page,
            "RecordsPerPage": PER_PAGE,
            "Keywords": "",
            "SearchType": 5,
            "OrganizationIds": cfg["org_id"],
            "SearchResultsModuleName": "Search Results",
            "SearchFiltersModuleName": "Search Filters",
            "SortCriteria": 1,
            "SortDirection": 1,
        }
        for i, f in enumerate(cfg.get("facets") or []):
            params[f"FacetFilters[{i}].ID"] = f["id"]
            params[f"FacetFilters[{i}].FacetType"] = f["type"]
        resp = await client.get(f"{cfg['base']}/search-jobs/results", params=params)
        resp.raise_for_status()
        try:
            html = resp.json()["results"]
        except (ValueError, KeyError, TypeError) as e:
            raise ParseError("barclays: results JSON shape changed") from e
        if not isinstance(html, str) or "data-total-results" not in html:
            raise ParseError("barclays: results HTML without totals")
        return html

    def _cards(self, cfg: dict, tree: HTMLParser):
        for link in tree.css("a[data-job-id]"):
            job_id = link.attributes.get("data-job-id")
            href = link.attributes.get("href")
            title = link.text(strip=True)
            if not job_id or not href or not title:
                raise ParseError("barclays: card without id/link/title")
            card = link.parent
            loc_node = card.css_first(".job-location") if card else None
            locations = [p.strip() for p in (loc_node.text() if loc_node else "").split(";")]
            locations = [p for p in locations if p]
            yield RawJob(
                external_id=job_id,
                title=title,
                url=f"{cfg['base']}{href}",
                locations=locations,
                country_codes=country_codes(locations),
            )

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        resp = await client.get(job.url)
        if resp.status_code == 404 or "Custom Job Error" in resp.text[:5000]:
            return GONE
        resp.raise_for_status()
        posting = None
        for block in _LDJSON.findall(resp.text):
            try:
                data = json.loads(block)
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("@type") == "JobPosting":
                posting = data
                break
        if posting is None:
            raise ParseError("barclays: job page without JobPosting JSON-LD")
        posted = None
        if posting.get("datePosted"):
            posted = datetime.fromisoformat(posting["datePosted"]).replace(tzinfo=UTC)
        apply_node = HTMLParser(resp.text).css_first('a[href$="/apply"]')
        return job.model_copy(
            update={
                "description_html": posting.get("description"),
                "employment_type": posting.get("employmentType"),
                "posted_at": posted,
                "apply_url": apply_node.attributes.get("href") if apply_node else job.url,
            }
        )


def _attr_int(tree: HTMLParser, attr: str) -> int:
    node = tree.css_first(f"[{attr}]")
    if node is None:
        raise ParseError(f"barclays: missing {attr}")
    return int(node.attributes[attr])
