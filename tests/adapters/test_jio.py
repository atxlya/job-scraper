from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx
import pytest

from app.adapters.base import ParseError, RawJob
from app.adapters.company.reliance import JioAdapter, split_title
from tests.conftest import load_fixture

CFG = {"categories": ["0206", "0210", "0216", "0222", "0227"]}
BASE = "https://careers.jio.com/"
IT = BASE + "frmfuncwisejob.aspx?func=2pGaMqAexDY=&desc=am1AraTXtX4/W/EJK6dzzw==&flag=/wASbQn4xyQ="
DETAIL = (
    BASE + "frmjobdescription.aspx?JBTITLE=LfU6zpqJcdE0brlVYTD9Ug==&jbID=hjrQwM31d8l2ht/"
    "amRk93Q==&funcCode=am1AraTXtX4/W/EJK6dzzw=="
)
ROBOTS = """User-agent: Googlebot
User-agent: *
Allow: /
Disallow: /frmLogin.aspx
Disallow: /frmForgotPassword.aspx
Disallow: /admin/
"""
PAGER = "ctl00$MainContent$lstJoblist$DataPager1$ctl00$PageDropDownList"


def html(name: str) -> httpx.Response:
    return httpx.Response(200, content=load_fixture("jio", name))


@pytest.fixture
def jio(mock):
    """Every Jio GET: categories page, else a category page (it_p1). Records raw URLs."""
    mock.get("https://careers.jio.com/robots.txt").mock(
        return_value=httpx.Response(200, text=ROBOTS)
    )
    seen: list[bytes] = []

    def get(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.raw_path)
        if request.url.path == "/frmJobCategories.aspx":
            return html("categories")
        return html("it_p1")

    def post(request: httpx.Request) -> httpx.Response:
        body = parse_qs(request.content.decode())
        if body["__EVENTTARGET"] == ["ctl00$MainContent$ddlentries"]:
            return html("it_25")
        assert body["__EVENTTARGET"] == [PAGER] and body[PAGER] == ["2"]
        return html("it_25_p2")

    mock.get(url__regex=r"https://careers\.jio\.com/frm.*").mock(side_effect=get)
    posts = mock.post(url__regex=r"https://careers\.jio\.com/frm.*").mock(side_effect=post)
    return seen, posts


def test_split_title():
    assert split_title("Manager Operations and Support ( 87543536 )") == (
        "Manager Operations and Support",
        "87543536",
    )
    assert split_title("Const Engr - CHO Projects Civil [83078441]") == (
        "Const Engr - CHO Projects Civil",
        "83078441",
    )
    with pytest.raises(ParseError):
        split_title("No id here")


async def test_reported_total_is_sum_of_chosen_categories(client, jio):
    seen, _ = jio
    res = await JioAdapter().list_jobs(client, CFG, "incremental")
    assert res.reported_total == 169 + 33 + 21 + 0 + 24
    assert not any(b"func=xiFo6zLluvo=" in raw for raw in seen)  # 0222 has 0 jobs
    assert len(seen) == 1 + 4


async def test_parses_category_page(client, jio):
    res = await JioAdapter().list_jobs(client, {"categories": ["0210"]}, "incremental")
    assert len(res.jobs) == 10 and res.complete is False
    first = res.jobs[0]
    assert first.external_id == "87543536"
    assert first.title == "Manager Operations and Support"
    assert first.locations == ["Mumbai"] and first.country_codes == ["IN"]
    assert first.posted_at == datetime(2026, 11, 4, tzinfo=UTC)
    assert first.url == DETAIL


async def test_full_pages_with_postbacks(client, jio):
    _, posts = jio
    res = await JioAdapter().list_jobs(client, {"categories": ["0210"]}, "full")
    bodies = [parse_qs(c.request.content.decode()) for c in posts.calls]
    assert bodies[0]["ctl00$MainContent$ddlentries"] == ["25"]
    assert bodies[1][PAGER] == ["2"]
    assert len(res.jobs) == 33 and res.complete is True


async def test_incremental_reads_first_page_only(client, jio):
    _, posts = jio
    await JioAdapter().list_jobs(client, CFG, "incremental")
    assert posts.call_count == 0


async def test_category_url_sent_verbatim(client, jio):
    seen, _ = jio
    await JioAdapter().list_jobs(client, {"categories": ["0210"]}, "incremental")
    assert seen[1] == IT.removeprefix("https://careers.jio.com").encode()


async def test_unknown_category_raises(client, jio):
    with pytest.raises(ParseError):
        await JioAdapter().list_jobs(client, {"categories": ["9999"]}, "incremental")


def job() -> RawJob:
    return RawJob(external_id="87543536", title="Manager Operations and Support", url=DETAIL)


async def test_detail(client, mock):
    mock.get(url__regex=r"https://careers\.jio\.com/frmjobdescription.*").mock(
        return_value=html("detail")
    )
    got = await JioAdapter().fetch_detail(client, CFG, job())
    assert "global technical support" in got.description_html
    assert "B.E/B.Tech/MCA" in got.description_html
    assert "Minimum 8 years - Maximum 15 years" in got.description_html
    assert got.title == "Manager Operations and Support"


async def test_detail_error_redirect_raises(client, mock):
    loc = "/error.aspx?aspxerrorpath=/frmjobdescription.aspx"
    mock.get(url__regex=r"https://careers\.jio\.com/frmjobdescription.*").mock(
        return_value=httpx.Response(302, headers={"Location": loc})
    )
    error = mock.get(url__regex=r".*/error\.aspx.*").mock(return_value=httpx.Response(200))
    with pytest.raises(ParseError):  # raised, so never GONE
        await JioAdapter().fetch_detail(client, CFG, job())
    assert error.call_count == 0


async def test_intern_categories_flag_their_jobs(client, jio):
    cfg = {"categories": ["0227"], "intern_categories": ["0227"]}
    res = await JioAdapter().list_jobs(client, cfg, "incremental")
    assert res.jobs and all(j.platform_flags == {"intern": True} for j in res.jobs)
    plain = await JioAdapter().list_jobs(client, {"categories": ["0210"]}, "incremental")
    assert all(j.platform_flags == {} for j in plain.jobs)
