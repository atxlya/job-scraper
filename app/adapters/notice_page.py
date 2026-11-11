"""Government recruitment notice pages (DRDO, ISRO, CDAC, BARC): one adapter, one parser per
site, chosen by cfg["site"]. A notice links to a PDF that is never downloaded; the PDF URL is
the `apply_url`. Every notice carries platform_flags["notice"] so the classifier and alerts
treat it as a PDF notice, and its description is built from the listing text (D8).
"""

import html
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.adapters.base import GONE, Gone, ListingResult, Mode, ParseError, RawJob, register, utc
from app.adapters.text import join_sections
from app.http.client import PoliteClient

_INVISIBLE = str.maketrans("", "", "⁠​")


def _clean(text: str | None) -> str:
    """Whitespace collapsed, zero-width word joiners and spaces removed."""
    return " ".join((text or "").translate(_INVISIBLE).split())


def _notice(
    *,
    external_id: str,
    title: str,
    url: str,
    apply_url: str | None = None,
    advert_no: str | None = None,
    published: str | None = None,
    last_date: str | None = None,
    description: str | None = None,
    posted_at: datetime | None = None,
) -> RawJob:
    """One notice. Only the parts a site has go into the description (D8)."""

    def text(value: str | None) -> str | None:
        return f"<p>{html.escape(value)}</p>" if value else None

    body = join_sections(
        [
            (None, text(title)),
            ("Advertisement No", text(advert_no)),
            ("Published", text(published)),
            ("Last date", text(last_date)),
            (None, description),
        ]
    )
    return RawJob(
        external_id=external_id,
        title=title,
        url=url,
        apply_url=apply_url,
        country_codes=["IN"],
        posted_at=posted_at,
        description_html=body,
        platform_flags={"notice": True},
    )


def _unique(jobs: list[RawJob]) -> list[RawJob]:
    """First notice wins when two share an external_id."""
    seen: dict[str, RawJob] = {}
    for job in jobs:
        seen.setdefault(job.external_id, job)
    return list(seen.values())


def _node_text(node) -> str | None:
    return _clean(node.text()) or None if node else None


def _first_href(tree: HTMLParser, needle: str, base: str) -> str | None:
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        if needle in href:
            return urljoin(base, href)
    return None


# ---- DRDO ----

DRDO_URL = "https://drdo.gov.in/drdo/en/offerings/vacancies"


def _title_of(tree: HTMLParser) -> str:
    node = tree.css_first("title")
    return node.text(strip=True) if node else ""


def parse_drdo(page: str) -> list[RawJob]:
    tree = HTMLParser(page)
    if not _title_of(tree).startswith("Vacancies |"):
        raise ParseError("notice_page drdo: not the vacancies page")
    jobs = []
    for box in tree.css("div.vacanciess-box"):
        title = _node_text(box.css_first(".vacanciess-title"))
        link = box.css_first(".vacanciess-view-node a[href]")
        if not (title and link):
            raise ParseError("notice_page drdo: incomplete vacancy box")
        url = urljoin(DRDO_URL, link.attributes["href"]).replace("http://", "https://", 1)
        published = box.css_first(".vacanciess-date-publish-content time[datetime]")
        desc = box.css_first(".vacanciess-desc")
        jobs.append(
            _notice(
                external_id=urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1],
                title=title,
                url=url,
                advert_no=_node_text(box.css_first(".vacanciess-advertisment-no-content")),
                published=_node_text(published),
                last_date=_node_text(box.css_first(".vacanciess-due-date-content")),
                description=(desc.inner_html or "").strip() or None if desc else None,
                posted_at=_posted(published.attributes["datetime"]) if published else None,
            )
        )
    return jobs


def _posted(value: str | None) -> datetime | None:
    try:
        return utc(datetime.fromisoformat(value)) if value else None
    except ValueError as e:
        raise ParseError(f"notice_page: unreadable date {value!r}") from e


def detail_drdo(job: RawJob, page: str) -> RawJob | Gone:
    tree = HTMLParser(page)
    slug = urlsplit(job.url).path.rstrip("/").rsplit("/", 1)[-1]
    if _title_of(tree).split(" | ", 1)[0] == slug:
        return GONE
    pdf = _first_href(tree, "/sites/default/files/vacancy/", job.url)
    return job.model_copy(update={"apply_url": pdf}) if pdf else job


LIST_URL: dict[str, str] = {"drdo": DRDO_URL}
PARSERS: dict[str, Callable[[str], list[RawJob]]] = {"drdo": parse_drdo}
# Sites whose detail page is fetched: (detail parser). CDAC and BARC link the PDF in the list.
DETAILS: dict[str, Callable[[RawJob, str], RawJob | Gone]] = {"drdo": detail_drdo}


@register
class NoticePageAdapter:
    name = "notice_page"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        site = cfg["site"]
        resp = await client.get(LIST_URL[site])
        resp.raise_for_status()
        return ListingResult(
            jobs=_unique(PARSERS[site](resp.text)), reported_total=None, complete=mode == "full"
        )

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        parse = DETAILS.get(cfg["site"])
        if parse is None:
            return job
        resp = await client.get(job.url)
        resp.raise_for_status()
        return parse(job, resp.text)
