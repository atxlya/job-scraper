"""Read a sitemap <urlset>; tags are matched by local name so any namespace works."""

from typing import NamedTuple
from xml.etree import ElementTree

from app.adapters.base import ParseError
from app.http.client import PoliteClient


class SitemapUrl(NamedTuple):
    loc: str
    lastmod: str | None


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


async def read_urlset(client: PoliteClient, url: str) -> list[SitemapUrl]:
    resp = await client.get(url)
    resp.raise_for_status()
    try:
        root = ElementTree.fromstring(resp.content)
    except ElementTree.ParseError as e:
        raise ParseError(f"{url}: not XML ({e})") from e
    if _local(root.tag) != "urlset":
        raise ParseError(f"{url}: root is <{_local(root.tag)}>, expected <urlset>")
    out: list[SitemapUrl] = []
    for entry in root:
        if _local(entry.tag) != "url":
            continue
        fields = {_local(c.tag): (c.text or "").strip() for c in entry}
        if fields.get("loc"):
            out.append(SitemapUrl(fields["loc"], fields.get("lastmod") or None))
    return out
