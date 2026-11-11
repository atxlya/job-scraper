from urllib.parse import parse_qs

import httpx
import pytest
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.adapters import aspnet
from app.adapters.base import ParseError
from tests.conftest import load_fixture

URL = "https://careers.techmahindra.com/CurrentOpportunity.aspx"
PAGER = "ctl00$ContentPlaceHolder1$rptPager$ctl01$lnkPage"


@pytest.fixture
def page():
    return HTMLParser(load_fixture("aspnet", "techm_page_1").decode("utf-8"))


def test_form_fields(page):
    fields = aspnet.form_fields(page)
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        assert fields[name]
    assert "ctl00$ContentPlaceHolder1$ddlCountry" in fields
    assert "ctl00$ContentPlaceHolder1$DataListRecommended$ctl00$btn_jobs" not in fields


def test_postback_target():
    href = f"javascript:__doPostBack('{PAGER}','')"
    assert aspnet.postback_target(href) == PAGER
    with pytest.raises(ParseError):
        aspnet.postback_target("/x.aspx")


async def test_postback_posts_fields_and_target(client, mock, page):
    route = mock.post(URL).mock(return_value=httpx.Response(200, text="<html>ok</html>"))
    tree = await aspnet.postback(client, URL, page, PAGER, {"extra": "1"})
    assert tree.css_first("html") is not None
    body = parse_qs(route.calls[0].request.content.decode())
    assert body["__EVENTTARGET"] == [PAGER]
    assert body["__VIEWSTATE"] == [aspnet.form_fields(page)["__VIEWSTATE"]]
    assert body["extra"] == ["1"]


async def test_postback_redirect_raises(client, mock, page):
    loc = "/error.aspx?aspxerrorpath=/frmjobdescription.aspx"
    mock.post(URL).mock(return_value=httpx.Response(302, headers={"Location": loc}))
    error = mock.get(url__regex=r".*/error\.aspx.*").mock(return_value=httpx.Response(200))
    with pytest.raises(ParseError, match="302"):
        await aspnet.postback(client, URL, page, PAGER)
    assert error.call_count == 0


def test_pages_shown():
    assert aspnet.pages_shown(HTMLParser("<span>Showing 1 of 4 Pages</span>")) == (1, 4)
    assert aspnet.pages_shown(HTMLParser("<p>nothing</p>")) is None
