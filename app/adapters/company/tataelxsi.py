"""Tata Elxsi: an HTML job board, 8 cards a page, newest first. A missing job answers with a
redirect to the home page.
"""

import re
from datetime import UTC, datetime

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.http.client import PoliteClient

LISTING = "https://www.tataelxsi.com/careers/job-openings"
_PAGE = re.compile(r"[?&]page=(\d+)")


@register
class TataElxsiAdapter:
    name = "tataelxsi"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        first = HTMLParser((await _get(client, 1)).text)
        pages = [first]
        if mode == "full":
            last = max((int(m[1]) for m in _PAGE.finditer(first.html or "")), default=1)
            for n in range(2, last + 1):
                pages.append(HTMLParser((await _get(client, n)).text))
        jobs = [job for tree in pages for job in _cards(tree)]
        return ListingResult(jobs=jobs, reported_total=None, complete=mode == "full")

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        resp = await client.get(job.url, follow_redirects=False)
        if 300 <= resp.status_code < 400:
            return GONE
        resp.raise_for_status()
        tree = HTMLParser(resp.text)
        if tree.css_first("div.jbpam") is None:
            raise ParseError("tataelxsi: job page without div.jbpam")
        title = tree.css_first("div.jbpam h2")
        body = tree.css_first("div.jbpam1")
        apply = tree.css_first("a.japlynw")
        return job.model_copy(
            update={
                "title": title.text(strip=True) if title else job.title,
                "description_html": (body.inner_html or "").strip() or None if body else None,
                "apply_url": apply.attributes.get("href") if apply else None,
            }
        )


async def _get(client: PoliteClient, page: int):
    resp = await client.get(LISTING, params={"page": page})
    resp.raise_for_status()
    return resp


def _cards(tree: HTMLParser) -> list[RawJob]:
    if tree.css_first("div#job_listing") is None:
        raise ParseError("tataelxsi: listing page without div#job_listing")
    jobs = []
    for card in tree.css("div.jjbcdeo1"):
        link = card.css_first("a.jknmre")
        title = card.css_first("h3")
        info = card.css_first("div.jjbcdeo11 p")
        date = card.css_first("div.jjbcdeo12 p")
        href = link.attributes.get("href") if link else None
        if not (href and title and info and date):
            raise ParseError("tataelxsi: incomplete job card")
        place = " ".join(info.text().split("|")[0].split())
        locations = [p.strip() for p in place.split(" / ") if p.strip()]
        posted = _posted(date.text(strip=True))
        jobs.append(
            RawJob(
                external_id=href.rstrip("/").rsplit("/", 1)[1],
                title=title.text(strip=True),
                url=href,
                locations=locations,
                country_codes=country_codes(locations),
                posted_at=posted,
            )
        )
    return jobs


def _posted(text: str) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%d %b %Y").replace(tzinfo=UTC)
    except ValueError as e:
        raise ParseError(f"tataelxsi: unreadable date {text!r}") from e
