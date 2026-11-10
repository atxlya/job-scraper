from app.adapters.base import ListingResult, RawJob
from app.sources.checks import evaluate


def jobs(n, missing=0):
    return [RawJob(external_id=str(i), title="" if i < missing else "T", url="u") for i in range(n)]


def test_zero_jobs_fails():
    assert "0 jobs" in evaluate(ListingResult(jobs=[], reported_total=0, complete=True), "full")[0]


def test_count_mismatch_fails_in_full_only():
    r = ListingResult(jobs=jobs(50), reported_total=100, complete=True)
    assert any("count" in p for p in evaluate(r, "full"))
    assert evaluate(r, "incremental") == []


def test_missing_titles_over_5_percent_fails():
    r = ListingResult(jobs=jobs(100, missing=6), reported_total=100, complete=True)
    assert any("missing" in p for p in evaluate(r, "full"))


def test_healthy_passes():
    assert evaluate(ListingResult(jobs=jobs(100), reported_total=101, complete=True), "full") == []
