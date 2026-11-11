import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
import pytest

from app.adapters.base import GONE, ParseError, RawJob
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


# ---- ISRO ----

SAC = "SACRecruitment21.html"
ISRO_BASE = "https://www.isro.gov.in/"


async def test_isro_one_notice_per_page(client, mock):
    res = await listing(client, mock, "isro", "isro_list")
    raw = load_fixture("notice_page", "isro_list").decode()
    pages = set(re.findall(r'<td class="news"><a href="([^"]*Recruitment[\w-]*\.html)"', raw))
    assert len(res.jobs) == len(pages) > 10
    assert {j.external_id for j in res.jobs} == pages
    sac = next(j for j in res.jobs if j.external_id == SAC)
    assert sac.title == (
        "Advt No. SAC:02:2026 dated 10.09.2026 - Inviting online applications for the posts "
        "of Junior Research Fellows, Research Associate and Project Scientist-I."
    )
    assert sac.url == ISRO_BASE + SAC
    assert sac.platform_flags == {"notice": True}
    assert "CareerOpportunities.html" not in {j.external_id for j in res.jobs}


async def test_isro_detail_finds_pdf(client, mock):
    job = RawJob(external_id=SAC, title="t", url=ISRO_BASE + SAC)
    mock.get(job.url).mock(return_value=page("isro_notice"))
    out = await NoticePageAdapter().fetch_detail(client, {"site": "isro"}, job)
    assert out.apply_url == (
        "https://www.isro.gov.in/media_isro/pdf/recruitmentNotice/2026/Sept/"
        "SAC_02_2026_dated_09092026.pdf"
    )


async def test_isro_missing_is_gone(client, mock):
    job = RawJob(
        external_id="NoSuchRecruitment99.html",
        title="t",
        url=ISRO_BASE + "NoSuchRecruitment99.html",
    )
    mock.get(job.url).mock(return_value=page("isro_missing", 404))
    assert await NoticePageAdapter().fetch_detail(client, {"site": "isro"}, job) is GONE


async def test_isro_wrong_page_raises_parse_error(client, mock):
    with pytest.raises(ParseError):
        await listing(client, mock, "isro", "drdo_list")


# ---- CDAC ----


async def test_cdac_parses_links(client, mock):
    res = await listing(client, mock, "cdac", "cdac_list")
    by_id = {j.external_id: j for j in res.jobs}
    assert len(by_id) == len(res.jobs) > 20
    pdf = by_id["CORRIGENDUM-ADVT-CORP-JIT-03-2026.pdf"]
    assert pdf.url == (
        "https://www.cdac.in/index.aspx?id=pdf_hrd&dynamicId=CORRIGENDUM-ADVT-CORP-JIT-03-2026.pdf"
    )
    assert pdf.apply_url == pdf.url
    page_notice = by_id["ca_NotificationConsultant09092026"]
    assert page_notice.apply_url is None
    assert page_notice.platform_flags == {"notice": True}
    external = [j for j in res.jobs if j.external_id.startswith("ext:")]
    assert {urlsplit(j.url).netloc for j in external} == {
        "careers.cdac.in",
        "cdac.kspcrecruitment.com",
    }
    assert len({j.external_id for j in external}) == len(external) == 2
    assert all(re.fullmatch(r"ext:[0-9a-f]{12}", j.external_id) for j in external)
    assert "job_archive_jobs" not in by_id


async def test_cdac_strong_heading_prefixes_link(client, mock):
    res = await listing(client, mock, "cdac", "cdac_list")
    job = next(j for j in res.jobs if j.external_id == "Walk-In-Positions-PMS-PE.pdf")
    assert job.title.startswith(
        "Walk-In Interview for Various Positions at C-DAC CINE: Advt. No. CINE/REC/2026/06 "
        "(Guwahati, Assam) — "
    )
    plain = next(j for j in res.jobs if j.external_id == "walkin-CINE-REC-2026-01.pdf")
    assert " — " not in plain.title


async def test_cdac_detail_makes_no_request(client, mock):
    res = await listing(client, mock, "cdac", "cdac_list")
    mock.reset()
    out = await NoticePageAdapter().fetch_detail(client, {"site": "cdac"}, res.jobs[0])
    assert out == res.jobs[0]
    assert mock.calls.call_count == 0


async def test_cdac_missing_marker_raises_parse_error(client, mock):
    with pytest.raises(ParseError):
        await listing(client, mock, "cdac", "barc_list")
