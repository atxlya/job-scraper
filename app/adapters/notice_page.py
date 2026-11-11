"""Government recruitment notice pages (DRDO, ISRO, CDAC, BARC): one adapter, one parser per
site, chosen by cfg["site"]. A notice links to a PDF that is never downloaded; the PDF URL is
the `apply_url`. Every notice carries platform_flags["notice"] so the classifier and alerts
treat it as a PDF notice, and its description is built from the listing text (D8).
"""

import hashlib
import html
import re
from collections.abc import Callable
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlsplit

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


def _https(url: str, host: str) -> str:
    """http:// becomes https:// for the site's own host only (DRDO writes http links to a
    site that serves https); other hosts and any "http://" inside the query are left alone."""
    parts = urlsplit(url)
    if parts.scheme == "http" and (parts.hostname or "").removeprefix("www.") == host:
        return parts._replace(scheme="https").geturl()
    return url


def _first_href(tree: HTMLParser, needle: str, base: str) -> str | None:
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        if needle in href:
            return urljoin(base, href)
    return None


# ---- DRDO ----

DRDO_URL = "https://drdo.gov.in/drdo/en/offerings/vacancies"
DRDO_HOST = "drdo.gov.in"


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
        url = _https(urljoin(DRDO_URL, link.attributes["href"]), DRDO_HOST)
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
    return job.model_copy(update={"apply_url": _https(pdf, DRDO_HOST)}) if pdf else job


# ---- ISRO ----

ISRO_URL = "https://www.isro.gov.in/Careers.html"
_ISRO_PAGE = re.compile(r"(?i)Recruitment[\w-]*\.html$")


def parse_isro(page: str) -> list[RawJob]:
    tree = HTMLParser(page)
    if _title_of(tree) != "Careers":
        raise ParseError("notice_page isro: not the careers page")
    jobs = []
    for link in tree.css("td.news a[href]"):
        href = link.attributes["href"] or ""
        if not _ISRO_PAGE.search(href):
            continue
        title = _clean(link.attributes.get("title")) or _clean(link.text()).removesuffix(
            "Read More"
        )
        url = urljoin(ISRO_URL, href)
        name = urlsplit(url).path.rsplit("/", 1)[-1]
        jobs.append(
            _notice(
                external_id=name,
                title=title.strip() or _name_title(name),
                url=url,
            )
        )
    return jobs


def _name_title(name: str) -> str:
    """ "DOSRecruitment10.html" → "DOS Recruitment 10", for a link with no text."""
    stem = name.rsplit(".", 1)[0]
    words = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[A-Za-z])(?=\d)", " ", stem)
    return " ".join(words.replace("-", " ").replace("_", " ").split())


def detail_isro(job: RawJob, page: str) -> RawJob:
    pdf = _first_href(HTMLParser(page), "/media_isro/pdf/", job.url)
    return job.model_copy(update={"apply_url": pdf}) if pdf else job


# ---- CDAC ----

CDAC_URL = "https://www.cdac.in/index.aspx?id=current_jobs"
_CDAC_FORM = re.compile(
    r"(?i)\b(application\s+form|interview\s+application|annexure|proforma|format)\b"
)
_CDAC_NOT_NOTICES = {"print_page", "career", "job_archive_jobs", "profile"}


def parse_cdac(page: str) -> list[RawJob]:
    content = HTMLParser(page).css_first("div#content")
    if content is None or not any(
        _clean(h.text()) == "Current Openings" for h in content.css("h3")
    ):
        raise ParseError("notice_page cdac: no Current Openings heading")
    jobs = []
    for link in content.css("a[href]"):
        query = parse_qs(urlsplit(link.attributes["href"] or "").query)
        text = _clean(link.text())
        if not text or query.get("id", [""])[0] in _CDAC_NOT_NOTICES:
            continue
        title, paragraph = _cdac_title(link, text)
        if paragraph is not None and _CDAC_FORM.search(text):
            continue  # an advertisement's application form or annexure, not a new opening
        url = urljoin(CDAC_URL, link.attributes["href"])
        key = (query.get("dynamicId") or query.get("id") or [None])[0]
        is_pdf = url.endswith(".pdf") or query.get("id", [""])[0].startswith("pdf_")
        jobs.append(
            _notice(
                external_id=key or "ext:" + hashlib.sha1(title.encode()).hexdigest()[:12],
                title=title,
                url=url,
                apply_url=url if is_pdf else None,
            )
        )
    return jobs


def _cdac_title(link, text: str) -> tuple[str, int | None]:
    """The link text, led by the bold heading of its paragraph when that is not the link,
    and that paragraph's id when a heading was used."""
    inside = {s.mem_id for s in link.css("strong")}
    paragraph = link.parent
    while paragraph is not None and paragraph.tag != "p":
        paragraph = paragraph.parent
    if paragraph is not None:
        for strong in paragraph.css("strong"):
            heading = _clean(strong.text())
            if strong.mem_id not in inside and heading and heading != text:
                return f"{heading} — {text}", paragraph.mem_id
    return text, None


# ---- BARC ----

BARC_URL = "https://www.barc.gov.in/careers/recruitment.html"
_BARC_HEAD = ["Advertisement No.", "Title", "Last Date", "Details"]


def parse_barc(page: str) -> list[RawJob]:
    tree = HTMLParser(page)
    table = next(
        (t for t in tree.css("table") if [_clean(h.text()) for h in t.css("th")] == _BARC_HEAD),
        None,
    )
    if table is None:
        raise ParseError("notice_page barc: no vacancy table")
    jobs = []
    for row in table.css("tr"):
        cells = row.css("td")
        if not cells:
            continue  # the header row, whether or not it sits in <thead>
        if len(cells) == 1 and cells[0].css_first("a[href]") is None:
            continue  # one cell across the table: "no vacancies at present"
        link = cells[3].css_first("a[href]") if len(cells) == 4 else None
        title = _barc_title(cells[1]) if link else ""
        if not title:
            raise ParseError("notice_page barc: incomplete vacancy row")
        url = urljoin(BARC_URL, link.attributes["href"])
        jobs.append(
            _notice(
                external_id=urlsplit(url).path.rsplit("/", 1)[-1],
                title=title,
                url=url,
                apply_url=url,
                advert_no=_node_text(cells[0]),
                last_date=_node_text(cells[2]),
            )
        )
    return jobs


def _barc_title(cell) -> str:
    """The cell's text up to the first <br> or <b>; what follows is the form download link."""
    parts = []
    node = cell.child
    while node is not None and node.tag not in ("br", "b"):
        parts.append(node.text())
        node = node.next
    return _clean("".join(parts))


LIST_URL: dict[str, str] = {"drdo": DRDO_URL, "isro": ISRO_URL, "cdac": CDAC_URL, "barc": BARC_URL}
PARSERS: dict[str, Callable[[str], list[RawJob]]] = {
    "drdo": parse_drdo,
    "isro": parse_isro,
    "cdac": parse_cdac,
    "barc": parse_barc,
}
# Sites whose detail page is fetched. CDAC and BARC link the PDF in the list.
DETAILS: dict[str, Callable[[RawJob, str], RawJob | Gone]] = {
    "drdo": detail_drdo,
    "isro": detail_isro,
}
# Sites that answer a missing notice with a real 404 (DRDO answers 200, see detail_drdo).
GONE_ON_404 = {"isro"}


def _site(cfg: dict) -> str:
    site = cfg.get("site")
    if site not in PARSERS:
        raise ParseError(f"notice_page: unknown site {site!r}")
    return site


@register
class NoticePageAdapter:
    name = "notice_page"

    @staticmethod
    def validate_config(cfg: dict) -> None:
        if cfg.get("site") not in PARSERS:
            raise ValueError(f"unknown notice site {cfg.get('site')!r}; one of {sorted(PARSERS)}")

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        site = _site(cfg)
        resp = await client.get(LIST_URL[site])
        resp.raise_for_status()
        return ListingResult(
            jobs=_unique(PARSERS[site](resp.text)), reported_total=None, complete=mode == "full"
        )

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        parse = DETAILS.get(_site(cfg))
        if parse is None:
            return job
        resp = await client.get(job.url)
        if resp.status_code == 404 and cfg["site"] in GONE_ON_404:
            return GONE
        resp.raise_for_status()
        return parse(job, resp.text)
