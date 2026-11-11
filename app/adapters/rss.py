"""RSS feed adapter (Zoho Recruit's careers feed, plan D14).

The feed carries everything, so `fetch_detail` looks jobs up in it (read once a run).
Zoho's job pages are script-rendered and are never fetched. `IST` in pubDate means +05:30.
"""

import html
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from selectolax.lexbor import LexborHTMLParser

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register, utc
from app.adapters.geo import country_codes
from app.http.client import PoliteClient

log = logging.getLogger(__name__)
_LOCATION = re.compile(r"Location:\s*([^<]*)")


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


@register
class RssAdapter:
    name = "rss"
    listing_has_details = True

    def __init__(self) -> None:
        self._feed: tuple[dict[str, RawJob], int] | None = None  # read once per run

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        jobs, skipped = await self._items(client, cfg["url"])
        # A skipped item may be a live job: don't let this sweep count towards closing it.
        complete = mode == "full" and skipped == 0
        return ListingResult(jobs=list(jobs.values()), reported_total=None, complete=complete)

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        if self._feed is None:
            self._feed = await self._items(client, cfg["url"])
        jobs, skipped = self._feed
        if job.external_id in jobs:
            return jobs[job.external_id]
        if skipped:
            raise ParseError(f"rss: {skipped} items skipped, so a missing job may not be gone")
        return GONE

    async def _items(self, client: PoliteClient, url: str) -> tuple[dict[str, RawJob], int]:
        resp = await client.get(url)
        resp.raise_for_status()
        try:
            root = ElementTree.fromstring(resp.content)
        except ElementTree.ParseError as e:
            raise ParseError(f"{url}: not XML ({e})") from e
        channel = next((c for c in root if _local(c.tag) == "channel"), None)
        if _local(root.tag) != "rss" or channel is None:
            raise ParseError(f"{url}: not an RSS feed (root <{_local(root.tag)}>)")
        items = [i for i in channel if _local(i.tag) == "item"]
        jobs: dict[str, RawJob] = {}
        skipped = 0
        for item in items:
            try:
                job = _to_raw(item)
            except ParseError as e:
                log.warning("%s: item skipped: %s", url, e)
                skipped += 1
                continue
            jobs.setdefault(job.external_id, job)
        if items and not jobs:
            raise ParseError(f"{url}: every item lacks a title or link")
        return jobs, skipped


def _to_raw(item: ElementTree.Element) -> RawJob:
    f = {_local(c.tag): (c.text or "").strip() for c in item}
    if not f.get("title") or not f.get("link"):
        raise ParseError("rss: item without title or link")
    link = f["link"].split("?", 1)[0]
    description = f.get("description", "")
    m = _LOCATION.search(description)
    locations = [m.group(1).strip()] if m and m.group(1).strip() else []
    span = LexborHTMLParser(description).css_first("span#spandesc")
    return RawJob(
        external_id=f.get("guid") or link,
        title=html.unescape(f["title"]),
        url=link,
        locations=locations,
        country_codes=country_codes(locations),
        description_html=(span.html if span is not None else description) or None,
        posted_at=_posted(f.get("pubDate")),
    )


def _posted(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return utc(parsedate_to_datetime(re.sub(r"\sIST$", " +0530", raw)))
    except (TypeError, ValueError):
        return None
