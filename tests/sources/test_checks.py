from app.adapters.base import ListingResult
from app.sources.checks import evaluate


def test_zero_jobs_fails_unless_allow_empty():
    empty = ListingResult(jobs=[], reported_total=0, complete=True)
    assert evaluate(empty, "full") == ["0 jobs returned"]
    assert evaluate(empty, "full", {"allow_empty": True}) == []
    assert evaluate(empty, "full", {}) == ["0 jobs returned"]
