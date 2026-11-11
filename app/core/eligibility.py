"""One eligibility rule for alerts, the dashboard badge and its filter. See plan D10."""

from typing import Literal, NamedTuple

from app.core.models import Job, JobAnalysis
from app.pipeline.classify import degree_only


class Eligibility(NamedTuple):
    status: Literal["ok", "warn", "pending"]  # pending = "Not checked" in the dashboard
    degree: str | None  # "PhD", "Master's", … when the title limits the role
    quote: str | None  # Gemini's verbatim line behind a warning
    checking: bool  # Gemini hasn't run yet but will
    unclear: bool  # Gemini ran and couldn't tell
    # Why Gemini will never read this job: a PDF notice, a title-only listing, or a
    # search summary (platform flags). None when it did, will, or the job isn't a candidate.
    unchecked: Literal["notice", "partial", "snippet"] | None = None


_NEVER_READ = ("notice", "partial", "snippet")


def eligibility(job: Job, analysis: JobAnalysis | None) -> Eligibility:
    degree = degree_only(job.title)
    if analysis is None:
        # Gemini only reads jobs that may be tech internships (app/llm/queue.py next_jobs).
        may_be_candidate = job.is_internship is not False and job.is_tech is not False
        checking = job.analysis_state == "pending" and may_be_candidate
        flags = job.platform_flags or {}
        unchecked = (
            next((f for f in _NEVER_READ if flags.get(f)), None)
            if job.analysis_state == "skipped"
            else None
        )
        status = "warn" if degree else "pending"
        return Eligibility(status, degree, None, checking, False, unchecked)
    if analysis.eligibility == "warn" and analysis.eligibility_quote:
        return Eligibility("warn", degree, analysis.eligibility_quote, False, False)
    if analysis.eligibility == "ok":
        return Eligibility("warn" if degree else "ok", degree, None, False, False)
    return Eligibility("warn" if degree else "pending", degree, None, False, True)
