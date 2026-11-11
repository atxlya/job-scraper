"""SAP SuccessFactors career sites (Wipro, HCLTech, EY, Deloitte India). The sitemap lists
every job URL with a slug title; job pages carry schema.org microdata and a layout of
labelled tokens. Missing jobs redirect to /errorpage/, which robots.txt disallows.
"""

import re
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx
import pycountry
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.adapters.sitemap import read_urlset
from app.adapters.text import slug_title
from app.http.client import PoliteClient

_MAX_HOPS = 5
_ALPHA2 = re.compile(r"^[A-Z]{2}$")


@register
class SuccessFactorsAdapter:
    name = "successfactors"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        host = cfg["host"]
        job_re = re.compile(
            rf"^https://{re.escape(host)}/(?:[a-z_]+/)?job/(?P<slug>[^/]+)/(?P<id>\d+)/$"
        )
        jobs: dict[str, RawJob] = {}
        for entry in await read_urlset(client, f"https://{host}/sitemap.xml"):
            m = job_re.match(entry.loc)
            if m is None:
                continue
            jobs.setdefault(
                m["id"],
                RawJob(
                    external_id=m["id"],
                    title=slug_title(m["slug"]),
                    url=entry.loc,
                    title_from_url=True,
                ),
            )
        return ListingResult(jobs=list(jobs.values()), reported_total=None, complete=mode == "full")

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        url = job.url
        for _ in range(_MAX_HOPS + 1):
            resp = await client.get(url, follow_redirects=False)
            if not 300 <= resp.status_code < 400:
                break
            location = resp.headers.get("Location", "")
            if urlsplit(location).path.startswith("/errorpage"):
                return GONE
            url = urljoin(url, location)
        else:
            raise httpx.TooManyRedirects(f"more than {_MAX_HOPS} redirects", request=resp.request)
        if resp.status_code in (404, 410):
            return GONE
        resp.raise_for_status()
        return _parse(job, resp.text)


def _parse(job: RawJob, html: str) -> RawJob:
    tree = HTMLParser(html)
    title_node = tree.css_first('[itemprop="title"]')
    title = title_node.text(strip=True) if title_node else ""
    if not title:
        raise ParseError("successfactors: job page without itemprop=title")
    desc_node = tree.css_first('[itemprop="description"]')
    street = _meta(tree, "streetAddress")
    locations = [street] if street else _token_location(tree)
    codes = set(country_codes(locations))
    if street:
        parts = [p.strip() for p in street.split(",")]
        if len(parts) > 1 and _ALPHA2.match(parts[1]) and pycountry.countries.get(alpha_2=parts[1]):
            codes.add(parts[1])
    return job.model_copy(
        update={
            "title": title,
            "title_from_url": False,
            "description_html": _inner(desc_node),
            "posted_at": _posted(tree),
            "locations": locations,
            "country_codes": sorted(codes),
            "apply_url": None,
        }
    )


def _inner(node) -> str | None:
    return (node.inner_html or "").strip() or None if node is not None else None


def _meta(tree: HTMLParser, prop: str) -> str | None:
    node = tree.css_first(f'meta[itemprop="{prop}"]')
    value = (node.attributes.get("content") or "").strip() if node else ""
    return value or None


def _token(tree: HTMLParser, label: str) -> str | None:
    for node in tree.css("span.joblayouttoken-label"):
        if node.text(strip=True).rstrip(":").strip() == label.rstrip(":"):
            sib = node.next
            while sib is not None and sib.tag != "span":
                sib = sib.next
            value = sib.text(strip=True) if sib is not None else ""
            return value or None
    return None


def _token_location(tree: HTMLParser) -> list[str]:
    parts = [v for v in (_token(tree, "City"), _token(tree, "State/Province")) if v]
    return [", ".join(parts)] if parts else []


def _posted(tree: HTMLParser) -> datetime | None:
    if raw := _meta(tree, "datePosted"):
        fmt, text = "%a %b %d %H:%M:%S UTC %Y", raw
    elif raw := _token(tree, "Posting Start Date"):
        fmt, text = "%m/%d/%y", raw
    else:
        return None
    try:
        return datetime.strptime(text, fmt).replace(tzinfo=UTC)
    except ValueError as e:
        raise ParseError(f"successfactors: unreadable posting date {text!r}") from e
