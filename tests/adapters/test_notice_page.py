from datetime import UTC, datetime

import httpx
import pytest

from app.adapters.base import GONE, ParseError
from app.adapters.notice_page import LIST_URL, NoticePageAdapter
from tests.conftest import load_fixture


def page(name, status=200):
    return httpx.Response(status, content=load_fixture("notice_page", name))


async def listing(client, mock, site, name, mode="incremental"):
    mock.get(LIST_URL[site]).mock(return_value=page(name))
    return await NoticePageAdapter().list_jobs(client, {"site": site, "allow_empty": True}, mode)


# ---- DRDO ----

DGRE = "dgre-chandigarh-invites-application-paid-internship-enggscience-ugpg-students"
DRDO_NOTICES = "https://drdo.gov.in/drdo/en/offerings/vacancies"


async def test_drdo_parses_boxes(client, mock):
    res = await listing(client, mock, "drdo", "drdo_list")
    assert len(res.jobs) == 9
    assert res.reported_total is None
    assert res.complete is False
    job = next(j for j in res.jobs if j.external_id == DGRE)
    assert job.posted_at == datetime(2026, 11, 10, 12, tzinfo=UTC)
    assert "DGRE/DRPM/TCHR/5205/Voc Trg/2026-01" in job.description_html
    assert "06/12/2026" in job.description_html
    assert job.platform_flags == {"notice": True}
    assert job.country_codes == ["IN"]
    assert job.locations == []


async def test_full_mode_is_complete(client, mock):
    res = await listing(client, mock, "drdo", "drdo_list", mode="full")
    assert res.complete is True


async def test_links_upgraded_to_https(client, mock):
    res = await listing(client, mock, "drdo", "drdo_list")
    assert all(j.url.startswith("https://drdo.gov.in/") for j in res.jobs)


async def test_drdo_detail_finds_pdf(client, mock):
    res = await listing(client, mock, "drdo", "drdo_list")
    job = next(j for j in res.jobs if j.external_id == DGRE)
    mock.get(job.url).mock(return_value=page("drdo_notice"))
    out = await NoticePageAdapter().fetch_detail(client, {"site": "drdo"}, job)
    assert out.apply_url == (
        "https://drdo.gov.in/drdo/sites/default/files/vacancy/advtDGRE10112026.pdf"
    )
    assert out.title == job.title


async def test_drdo_soft_404_is_gone(client, mock):
    res = await listing(client, mock, "drdo", "drdo_list")
    job = res.jobs[0].model_copy(update={"url": f"{DRDO_NOTICES}/no-such-notice-xyz"})
    mock.get(job.url).mock(return_value=page("drdo_missing"))
    assert await NoticePageAdapter().fetch_detail(client, {"site": "drdo"}, job) is GONE


async def test_drdo_wrong_page_raises_parse_error(client, mock):
    with pytest.raises(ParseError):
        await listing(client, mock, "drdo", "drdo_notice")
