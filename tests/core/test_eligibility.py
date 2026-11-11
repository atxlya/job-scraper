from datetime import UTC, datetime

import pytest

from app.core.eligibility import Eligibility, eligibility
from app.core.models import Job, JobAnalysis

T0 = datetime(2026, 11, 10, tzinfo=UTC)


def job(title="Software Intern", state="pending", intern=True, tech=True):
    return Job(title=title, analysis_state=state, is_internship=intern, is_tech=tech)


def analysis(e, quote=None):
    return JobAnalysis(eligibility=e, eligibility_quote=quote, sections={}, created_at=T0)


@pytest.mark.parametrize(
    ("j", "a", "expected"),
    [
        (job(state="done"), analysis("ok"), Eligibility("ok", None, None, False, False)),
        (
            job(state="done"),
            analysis("warn", "US students only"),
            Eligibility("warn", None, "US students only", False, False),
        ),
        # A warning without its quote is not trusted (R1 rule): unclear, not a warning.
        (job(state="done"), analysis("warn"), Eligibility("pending", None, None, False, True)),
        (job(state="done"), analysis("unknown"), Eligibility("pending", None, None, False, True)),
        (job(), None, Eligibility("pending", None, None, True, False)),
        (job(state="failed"), None, Eligibility("pending", None, None, False, False)),
        (
            job("Software PhD Intern", "done"),
            analysis("ok"),
            Eligibility("warn", "PhD", None, False, False),
        ),
        (job("MBA Intern"), None, Eligibility("warn", "MBA", None, True, False)),
        # Gemini only reads possible tech internships, so nothing is coming for these.
        (job(intern=False), None, Eligibility("pending", None, None, False, False)),
        (job(tech=False), None, Eligibility("pending", None, None, False, False)),
        (job(intern=None, tech=None), None, Eligibility("pending", None, None, True, False)),
    ],
)
def test_eligibility(j, a, expected):
    assert eligibility(j, a) == expected


@pytest.mark.parametrize("flag", ["notice", "partial", "snippet"])
def test_jobs_gemini_never_reads_say_why(flag):
    j = Job(
        title="Software Intern",
        analysis_state="skipped",
        is_internship=True,
        is_tech=True,
        platform_flags={flag: True},
    )
    assert eligibility(j, None) == Eligibility("pending", None, None, False, False, flag)


def test_notice_still_waiting_for_gemini_has_no_reason():
    j = Job(title="Walk-in", analysis_state="pending", platform_flags={"notice": True})
    assert eligibility(j, None).unchecked is None
