"""Health checks for a listing result, shared by `live-check` and "Add company"."""

from app.adapters.base import ListingResult
from app.worker.runner import _mismatch

MISSING_LIMIT = 0.05


def evaluate(result: ListingResult, mode: str, cfg: dict | None = None) -> list[str]:
    """Problems that make a check fail. Empty list means healthy. A source whose config
    has `allow_empty` (a site with no openings right now) may return 0 jobs."""
    n = len(result.jobs)
    if n == 0:
        return [] if (cfg or {}).get("allow_empty") else ["0 jobs returned"]
    problems = []
    if mode == "full" and _mismatch(n, result.reported_total):
        problems.append(f"count mismatch: read {n}, site reports {result.reported_total}")
    missing = sum(1 for j in result.jobs if not j.title or not j.url)
    if missing / n > MISSING_LIMIT:
        problems.append(f"{missing}/{n} jobs missing title or url")
    return problems
