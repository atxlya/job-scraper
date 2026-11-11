from urllib.parse import parse_qs

import httpx
import pytest
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.adapters import aspnet
from app.adapters.base import ParseError, RawJob
from app.adapters.company.techmahindra import LIST_URL, TechMahindraAdapter, parse_cards
from tests.conftest import load_fixture


def page(name: str) -> bytes:
    return load_fixture("techmahindra", name)


def html(name: str) -> httpx.Response:
    return httpx.Response(200, content=page(name))


def target(name: str, label: str) -> str:
    """The postback target of the pager link labelled `label` on fixture `name`."""
    tree = HTMLParser(page(name).decode("utf-8"))
    link = next(
        a for a in tree.css('a[href^="javascript:__doPostBack"]') if a.text(strip=True) == label
    )
    return aspnet.postback_target(link.attributes["href"])


def codes(name: str) -> set[str]:
    tree = HTMLParser(page(name).decode("utf-8"))
    return {n.attributes["value"] for n in tree.css('input[id$="_HdnJobCode"]')}


def posted_targets(route) -> list[str]:
    return [parse_qs(c.request.content.decode())["__EVENTTARGET"][0] for c in route.calls]


def serve_posts(mock, answers: dict[str, str], default: str | None = None):
    def answer(request: httpx.Request) -> httpx.Response:
        tgt = parse_qs(request.content.decode())["__EVENTTARGET"][0]
        return html(answers.get(tgt, default))

    return mock.post(LIST_URL).mock(side_effect=answer)


async def test_parses_cards(client, mock):
    mock.get(LIST_URL).mock(return_value=html("last"))
    res = await TechMahindraAdapter().list_jobs(client, {}, "full")
    assert {j.external_id for j in res.jobs} == codes("last")


def test_card_fields():
    tree = HTMLParser(page("page_1").decode("utf-8"))
    jobs = {j.external_id: j for j in parse_cards(tree)}
    assert len(jobs) == 12 and set(jobs) == codes("page_1")
    job = jobs["92890"]
    assert job.title == "Avionics Systems Engineer"
    assert job.locations == ["MONTREAL"]
    assert job.url == f"{LIST_URL}#job-92890"
    assert "3D" in job.description_html and "7 - 10 Years" in job.description_html


async def test_incremental_reads_first_last_and_before_last(client, mock):
    get = mock.get(LIST_URL).mock(return_value=html("page_1"))
    post = serve_posts(
        mock, {target("page_1", "Last"): "last", target("last", "41"): "before_last"}
    )
    res = await TechMahindraAdapter().list_jobs(client, {}, "incremental")
    assert get.call_count == 1
    assert posted_targets(post) == [target("page_1", "Last"), target("last", "41")]
    assert {j.external_id for j in res.jobs} == codes("page_1") | codes("last") | codes(
        "before_last"
    )
    assert res.complete is False and res.reported_total is None


async def test_full_stops_on_last_page(client, mock):
    get = mock.get(LIST_URL).mock(return_value=html("last"))
    post = serve_posts(mock, {}, default="last")
    res = await TechMahindraAdapter().list_jobs(client, {}, "full")
    assert get.call_count == 1 and post.call_count == 0
    assert res.complete is True
    assert len(res.jobs) == len(codes("last"))


async def test_full_requests_next_page(client, mock):
    mock.get(LIST_URL).mock(return_value=html("page_1"))
    post = serve_posts(mock, {target("page_1", "2"): "page_2"}, default="last")
    with pytest.raises(ParseError, match="asked for page 3"):
        await TechMahindraAdapter().list_jobs(client, {}, "full")
    assert posted_targets(post) == [target("page_1", "2"), target("page_2", "3")]


async def test_wrong_page_raises(client, mock):
    mock.get(LIST_URL).mock(return_value=html("page_1"))
    serve_posts(mock, {}, default="last")
    with pytest.raises(ParseError, match="asked for page 2"):
        await TechMahindraAdapter().list_jobs(client, {}, "full")


async def test_listing_without_table_raises(client, mock):
    mock.get(LIST_URL).mock(
        return_value=httpx.Response(200, content=load_fixture("tataelxsi", "home"))
    )
    with pytest.raises(ParseError):
        await TechMahindraAdapter().list_jobs(client, {}, "incremental")


async def test_fetch_detail_makes_no_request(client, mock):
    job = RawJob(external_id="92890", title="Avionics Systems Engineer", url=f"{LIST_URL}#job-1")
    route = mock.route(url__regex=r"https://careers\.techmahindra\.com/(?!robots).*")
    assert await TechMahindraAdapter().fetch_detail(client, {}, job) is job
    assert route.call_count == 0


def test_card_text_not_escaped_twice():
    tree = HTMLParser(page("page_2").decode("utf-8"))
    job = next(j for j in parse_cards(tree) if j.external_id == "95857")
    shown = HTMLParser(job.description_html).body.text()
    assert "P&amp;C" in shown  # what a browser shows on the site itself
    assert "P&amp;amp;C" not in shown


async def test_full_without_next_link_but_later_pages_raises(client, mock):
    broken = page("page_1").replace(
        b'id="ctl00_ContentPlaceHolder1_rptPager_ctl01_lnkPage" class="page_enabled"',
        b'id="ctl00_ContentPlaceHolder1_rptPager_ctl01_lnkPage" class="page_other"',
    )
    mock.get(LIST_URL).mock(return_value=httpx.Response(200, content=broken))
    post = serve_posts(mock, {}, default="last")
    with pytest.raises(ParseError, match="no link to page 2"):
        await TechMahindraAdapter().list_jobs(client, {}, "full")
    assert post.call_count == 0
