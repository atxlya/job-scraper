"""RSS feed adapter (Zoho Recruit's careers feed, plan D14).

The feed carries everything, so `fetch_detail` re-reads it. Zoho's job pages are
script-rendered and are never fetched. `IST` in pubDate means +05:30.
"""

import html
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from selectolax.lexbor import LexborHTMLParser

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register, utc
from app.adapters.geo import country_codes
from app.http.client import PoliteClient

_LOCATION = re.compile(r"Location:\s*([^<]*)")


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


@register
class RssAdapter:
    name = "rss"
    listing_has_details = True

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        jobs = {j.external_id: j for j in await self._items(client, cfg["url"])}
        return ListingResult(jobs=list(jobs.values()), reported_total=None, complete=mode == "full")

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        for job_now in await self._items(client, cfg["url"]):
            if job_now.external_id == job.external_id:
                return job_now
        return GONE

    async def _items(self, client: PoliteClient, url: str) -> list[RawJob]:
        resp = await client.get(url)
        resp.raise_for_status()
        try:
            root = ElementTree.fromstring(resp.content)
        except ElementTree.ParseError as e:
            raise ParseError(f"{url}: not XML ({e})") from e
        channel = next((c for c in root if _local(c.tag) == "channel"), None)
        if _local(root.tag) != "rss" or channel is None:
            raise ParseError(f"{url}: not an RSS feed (root <{_local(root.tag)}>)")
        return [_to_raw(i) for i in channel if _local(i.tag) == "item"]


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
