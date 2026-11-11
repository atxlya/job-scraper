"""Tech Mahindra: server-rendered job cards, 12 a page, paged by ASP.NET postbacks.

Pages are ordered by job code, ascending, so the newest jobs are on the last pages. There
is no public job page: the card's text is the description. Card order inside a page
shuffles per request; a card's identity is its HdnJobCode.
"""

import html
import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.adapters import aspnet
from app.adapters.base import Gone, ListingResult, Mode, ParseError, RawJob, register
from app.adapters.geo import country_codes
from app.adapters.text import join_sections
from app.http.client import PoliteClient

LIST_URL = "https://careers.techmahindra.com/CurrentOpportunity.aspx"
MAX_PAGES = 200
_FIELD = re.compile(r"<b>\s*([^<:]+?)\s*</b>\s*:\s*([^<]*)", re.I)


@register
class TechMahindraAdapter:
    name = "techmahindra"
    listing_has_details = True

    async def list_jobs(self, client: PoliteClient, cfg: dict, mode: Mode) -> ListingResult:
        tree = await aspnet.get_page(client, LIST_URL)
        trees = [tree]
        if mode == "full":
            current = _current(tree)
            while (link := _link(tree, str(current + 1))) is not None:
                if len(trees) >= MAX_PAGES:
                    raise ParseError(f"techmahindra: more than {MAX_PAGES} pages")
                tree = await _go(client, tree, link, current + 1)
                trees.append(tree)
                current += 1
            if _more_pages(tree, current):
                # A pager that still offers later pages but no link to the next one: stopping
                # here would report a short read as complete and close real jobs.
                raise ParseError(f"techmahindra: no link to page {current + 1}")
        else:
            last_link = _link(tree, "Last")
            if last_link is not None:
                last = await aspnet.postback(client, LIST_URL, tree, last_link)
                n = _current(last)
                if n <= _current(tree) or _link(last, "Last") is not None:
                    # Not the last page: new jobs would wait for the nightly run.
                    raise ParseError(f'techmahindra: "Last" answered page {n}')
                trees.append(last)
                before = _link(last, str(n - 1))
                if before is not None:
                    trees.append(await _go(client, last, before, n - 1))
        jobs: dict[str, RawJob] = {}
        for t in trees:
            for job in parse_cards(t):
                jobs.setdefault(job.external_id, job)
        return ListingResult(jobs=list(jobs.values()), reported_total=None, complete=mode == "full")

    async def fetch_detail(self, client: PoliteClient, cfg: dict, job: RawJob) -> RawJob | Gone:
        return job  # no public job page: the card was the whole posting


async def _go(client: PoliteClient, tree: HTMLParser, target: str, want: int) -> HTMLParser:
    answer = await aspnet.postback(client, LIST_URL, tree, target)
    got = _current(answer)
    if got != want:
        raise ParseError(f"techmahindra: asked for page {want}, got {got}")
    return answer


def _pager(tree: HTMLParser):
    return tree.css('a[id^="ctl00_ContentPlaceHolder1_rptPager_"]')


def _current(tree: HTMLParser) -> int:
    for a in _pager(tree):
        text = a.text(strip=True)
        if "page_disabled" in (a.attributes.get("class") or "") and text.isdigit():
            return int(text)
    if tree.css_first("table#ctl00_ContentPlaceHolder1_DataListRecommended") is None:
        raise ParseError("techmahindra: page without the job table")
    return 1  # a single page has no pager


def _more_pages(tree: HTMLParser, current: int) -> bool:
    for a in _pager(tree):
        if "page_enabled" not in (a.attributes.get("class") or ""):
            continue
        text = a.text(strip=True)
        if text in ("Last", ">>") or (text.isdigit() and int(text) > current):
            return True
    return False


def _link(tree: HTMLParser, label: str) -> str | None:
    for a in _pager(tree):
        if a.text(strip=True) == label and "page_enabled" in (a.attributes.get("class") or ""):
            return aspnet.postback_target(a.attributes.get("href") or "")
    return None


def _child(kids, tag: str):
    return next((k for k in kids if k.tag == tag), None)


def parse_cards(tree: HTMLParser) -> list[RawJob]:
    if tree.css_first("table#ctl00_ContentPlaceHolder1_DataListRecommended") is None:
        raise ParseError("techmahindra: page without the job table")
    jobs = []
    for code_node in tree.css('input[id$="_HdnJobCode"]'):
        code = (code_node.attributes.get("value") or "").strip()
        card = code_node.parent
        kids = list(card.iter()) if card is not None else []
        category = _child(kids, "span")
        title = _child(kids, "div")
        details = _child(kids, "p")
        if not (code and title and details):
            raise ParseError("techmahindra: incomplete job card")
        fields = {
            k.lower(): " ".join(html.unescape(v).split())
            for k, v in _FIELD.findall(details.html or "")
        }
        location = fields.get("location", "")
        locations = [location] if location else []
        sections = [
            ("Skill set", fields.get("skill set")),
            ("Experience", fields.get("experience")),
            ("Location", location),
            ("Category", category.text(strip=True) if category else None),
        ]
        jobs.append(
            RawJob(
                external_id=code,
                title=" ".join(title.text().split()),
                url=f"{LIST_URL}#job-{code}",
                locations=locations,
                country_codes=country_codes(locations),
                description_html=join_sections(
                    [(h, f"<p>{html.escape(v)}</p>" if v else None) for h, v in sections]
                ),
            )
        )
    return jobs
