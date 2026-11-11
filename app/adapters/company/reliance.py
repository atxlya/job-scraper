"""Jio and Reliance: two ASP.NET WebForms career portals built on the same code.

Lists are newest first, 10 rows a page; a full run asks for 25 rows a page and walks the
pager select by postback. Job links carry encrypted query values (`func=w+cpdiT6wL4=`),
which are sent exactly as the page wrote them. The job key is JBTITLE (jbID is ignored).
No answer has been seen that means "this job is gone": a bad key gives Jio's error page
(302) or Reliance's profile page, so both are ParseErrors and jobs close by sweeps.
"""

import re
from datetime import UTC, datetime
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.adapters import aspnet
from app.adapters.base import Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.adapters.text import join_sections
from app.http.client import PoliteClient

JIO = "https://careers.jio.com/"
JIO_CATEGORIES = JIO + "frmJobCategories.aspx"
RESULTS_URL = (
    "https://careers.ril.com/rilcareers/frmJobSearch.aspx?"
    "func=w+cpdiT6wL4=&loc=/wASbQn4xyQ=&expreq=/wASbQn4xyQ=&flag=/wASbQn4xyQ="
)  # every function; the search postback redirects here
ENTRIES = "ctl00$MainContent$ddlentries"
MAX_PAGES = 100
_TITLE = re.compile(r"^(.*?)\s*[(\[]\s*(\d+)\s*[)\]]\s*$", re.S)


def split_title(text: str) -> tuple[str, str]:
    """ "Title ( 87543536 )" or "Title [83078441]" → (title, id)."""
    m = _TITLE.match(" ".join((text or "").split()))
    if m is None or not m[1]:
        raise ParseError(f"no job id in title {text!r}")
    return m[1], m[2]


def posted(text: str) -> datetime | None:
    text = " ".join((text or "").split())
    if not text:
        return None
    try:
        return datetime.strptime(text, "%d %b %Y").replace(tzinfo=UTC)
    except ValueError as e:
        raise ParseError(f"unreadable date {text!r}") from e


def _inner(tree: HTMLParser, node_id: str) -> str | None:
    node = tree.css_first(f"#{node_id}")
    return (node.inner_html or "").strip() or None if node is not None else None


def parse_detail(tree: HTMLParser, job: RawJob) -> RawJob:
    date = tree.css_first("#MainContent_lblPostedDate")
    if date is None or not date.text(strip=True):
        # Reliance answers a bad job key with the same page, every field empty.
        raise ParseError("job page without a posted date")
    sections = [
        ("Job responsibilities", _inner(tree, "MainContent_lblSummRole")),
        ("Education", _inner(tree, "MainContent_lblEduReq")),
        ("Experience", _inner(tree, "MainContent_lblExpReq")),
        ("Skills", _inner(tree, "MainContent_lblSkill")),
    ]
    return job.model_copy(update={"description_html": join_sections(sections)})


async def fetch_portal_detail(client: PoliteClient, job: RawJob) -> RawJob:
    # A redirect goes to the error page, which is a ParseError, not "gone".
    return parse_detail(await aspnet.get_page(client, job.url), job)


async def walk_pages(
    client: PoliteClient, url: str, first: HTMLParser, mode: Mode
) -> list[HTMLParser]:
    """The first page, plus in full mode every page at 25 rows a page."""
    shown = aspnet.pages_shown(first)
    if mode != "full":
        return [first]
    if shown is None:
        if _pager_select(first) is not None:
            # A pager without "Showing N of M Pages": reading page 1 alone would look complete.
            raise ParseError("page count missing next to the pager")
        return [first]
    if shown[1] <= 1:
        return [first]
    tree = await aspnet.postback(client, url, first, ENTRIES, {ENTRIES: "25"})
    trees = [tree]
    total = _check(tree, 1)
    if total > MAX_PAGES:
        raise ParseError(f"more than {MAX_PAGES} pages")
    for n in range(2, total + 1):
        select = _pager_select(tree)
        if select is None:
            raise ParseError("pager without PageDropDownList")
        name = select.attributes["name"]
        tree = await aspnet.postback(client, url, tree, name, {name: str(n), ENTRIES: "25"})
        if (now := _check(tree, n)) != total:
            # Jobs added or removed mid-walk shift every row; a later run reads it cleanly.
            raise ParseError(f"page count changed from {total} to {now} mid-walk")
        trees.append(tree)
    return trees


def _pager_select(tree: HTMLParser):
    return next(
        (s for s in tree.css("select[name]") if s.attributes["name"].endswith("PageDropDownList")),
        None,
    )


def _check(tree: HTMLParser, want: int) -> int:
    shown = aspnet.pages_shown(tree)
    if shown is None or shown[0] != want:
        raise ParseError(f"asked for page {want}, got {shown}")
    return shown[1]


@register
class JioAdapter:
    name = "jio"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        categories = _categories(await aspnet.get_page(client, JIO_CATEGORIES))
        wanted = cfg["categories"]
        missing = [c for c in wanted if c not in categories]
        if missing:
            raise ParseError(f"jio: categories not on the page: {missing}")
        intern_codes = set(cfg.get("intern_categories") or [])
        jobs: dict[str, RawJob] = {}
        for code in wanted:
            href, count = categories[code]
            if count == 0:
                continue
            url = urljoin(JIO, href)  # verbatim: encrypted values keep their + / =
            first = await aspnet.get_page(client, url)
            for tree in await walk_pages(client, url, first, mode):
                for job in _jio_rows(tree):
                    if code in intern_codes:  # e.g. 0227 "Apprentice": the site's own facet
                        job = job.model_copy(update={"platform_flags": {"intern": True}})
                    jobs.setdefault(job.external_id, job)
        total = sum(categories[c][1] for c in wanted)
        return ListingResult(
            jobs=list(jobs.values()), reported_total=total, complete=mode == "full"
        )

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        return await fetch_portal_detail(client, job)


def _categories(tree: HTMLParser) -> dict[str, tuple[str, int]]:
    out = {}
    for item in tree.css("li.list-cont"):
        code = item.css_first('input[id^="MainContent_rptJoblist_hdfunctioncode_"]')
        link = item.css_first('a[id^="MainContent_rptJoblist_HRFLink_"]')
        count = item.css_first('span[id^="MainContent_rptJoblist_lblfunctionjobCount_"]')
        if code is None or link is None or count is None:
            continue
        text = count.text(strip=True)
        if not text.isdigit():
            raise ParseError(f"jio: unreadable category count {text!r}")
        out[code.attributes.get("value") or ""] = (link.attributes.get("href") or "", int(text))
    if not out:
        raise ParseError("jio: no categories on frmJobCategories.aspx")
    return out


def _jio_rows(tree: HTMLParser) -> list[RawJob]:
    links = tree.css('a[id^="MainContent_lstJoblist_hylUser_"]')
    if not links and aspnet.pages_shown(tree) is None:
        raise ParseError("jio: category page without job rows")
    jobs = []
    for link in links:
        n = link.attributes["id"].rsplit("_", 1)[1]
        title, job_id = split_title(link.text())
        loc = tree.css_first(f"#MainContent_lstJoblist_Label2_{n}")
        date = tree.css_first(f"#MainContent_lstJoblist_Label1_{n}")
        locations = [loc.text(strip=True)] if loc is not None and loc.text(strip=True) else []
        jobs.append(
            RawJob(
                external_id=job_id,
                title=title,
                url=urljoin(JIO, link.attributes.get("href") or ""),
                locations=locations,
                country_codes=country_codes(locations) or ["IN"],
                posted_at=posted(date.text() if date is not None else ""),
            )
        )
    return jobs


@register
class RilAdapter:
    name = "ril"

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        first = await aspnet.get_page(client, RESULTS_URL)
        jobs: dict[str, RawJob] = {}
        for tree in await walk_pages(client, RESULTS_URL, first, mode):
            for job in _ril_rows(tree):
                jobs.setdefault(job.external_id, job)
        return ListingResult(jobs=list(jobs.values()), reported_total=None, complete=mode == "full")

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        return await fetch_portal_detail(client, job)


def _ril_rows(tree: HTMLParser) -> list[RawJob]:
    table = tree.css_first("table#MainContent_rgJobs")
    if table is None:
        raise ParseError("ril: results page without table#MainContent_rgJobs")
    jobs = []
    for row in table.css("tr"):
        link = row.css_first('a[id^="MainContent_rgJobs_hylUser_"]')
        if link is None:
            continue  # header and pager rows
        cells = row.css("td")
        if len(cells) < 5:
            raise ParseError("ril: job row with fewer than 5 cells")
        title, job_id = split_title(link.text())
        location = cells[3].text(strip=True)
        locations = [location] if location else []
        jobs.append(
            RawJob(
                external_id=job_id,
                title=title,
                # the link has two href attributes; the parser keeps the first (the job URL)
                url=urljoin(RESULTS_URL, link.attributes.get("href") or ""),
                locations=locations,
                country_codes=country_codes(locations) or ["IN"],
                posted_at=posted(cells[4].text()),
            )
        )
    return jobs
