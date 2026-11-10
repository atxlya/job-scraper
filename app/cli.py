"""Command line.

python -m app.cli sync-registry
python -m app.cli live-check [--source KEY] [--mode incremental|full]
python -m app.cli run-once --mode incremental|full|tracked [--source KEY]
python -m app.cli analyze-one --job-id N
python -m app.cli reindex
python -m app.cli set-password
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.adapters.base import ADAPTERS, ListingResult
from app.core.models import Company, Source
from app.core.registry import load_registry, sync_registry
from app.core.settings import get_settings
from app.worker.runner import _mismatch, run_all
from app.worker.scheduler import build_ctx

ROOT = Path(__file__).resolve().parents[1]
MISSING_LIMIT = 0.05


def evaluate(result: ListingResult, mode: str) -> list[str]:
    """Problems that make a live check fail. Empty list means healthy."""
    problems = []
    n = len(result.jobs)
    if n == 0:
        return ["0 jobs returned"]
    if mode == "full" and _mismatch(n, result.reported_total):
        problems.append(f"count mismatch: read {n}, site reports {result.reported_total}")
    missing = sum(1 for j in result.jobs if not j.title or not j.url)
    if missing / n > MISSING_LIMIT:
        problems.append(f"{missing}/{n} jobs missing title or url")
    return problems


async def live_check(only: str | None, mode: str) -> int:
    ctx = build_ctx(get_settings())
    specs = load_registry(ROOT / "config" / "sources.yaml")
    failures = 0
    print(f"{'source':28} {'jobs':>6} {'total':>7} {'complete':>8}  result")
    for spec in specs:
        if not spec.supported:
            continue
        for src in spec.sources:
            if only and src.key != only:
                continue
            adapter = ADAPTERS[src.adapter]()
            try:
                result = await adapter.list_jobs(ctx.client, src.config, mode)
                problems = evaluate(result, mode)
                line = (
                    f"{src.key:28} {len(result.jobs):>6} {result.reported_total!s:>7} "
                    f"{result.complete!s:>8}  "
                )
            except Exception as e:  # noqa: BLE001
                problems = [f"{type(e).__name__}: {e}"[:200]]
                line = f"{src.key:28} {'-':>6} {'-':>7} {'-':>8}  "
            failures += bool(problems)
            print(line + ("OK" if not problems else "FAIL " + "; ".join(problems)), flush=True)
    await ctx.client.aclose()
    print(f"\n{failures} source(s) failed")
    return 1 if failures else 0


async def run_once(mode: str, only: str | None) -> int:
    ctx = build_ctx(get_settings())
    with ctx.session_factory() as s:
        sync_registry(s, load_registry(ROOT / "config" / "sources.yaml"))
        s.commit()
    runs = await run_all(ctx, mode, only=only)
    with ctx.session_factory() as s:
        for r in runs:
            src = s.get(Source, r.source_id)
            print(
                f"{src.key:28} {r.status:8} found={r.jobs_found} new={r.new_count} "
                f"closed={r.closed_count} {r.error or ''}"
            )
    await ctx.client.aclose()
    return 1 if any(r.status == "failed" for r in runs) else 0


async def analyze_one(job_id: int) -> int:
    from app.core.models import Job  # noqa: PLC0415
    from app.llm.provider import validate_quotes  # noqa: PLC0415
    from app.llm.queue import html_to_text  # noqa: PLC0415

    ctx = build_ctx(get_settings())
    if ctx.provider is None:
        print("GEMINI_API_KEY is not set", file=sys.stderr)
        return 2
    with ctx.session_factory() as s:
        job = s.get(Job, job_id)
        if job is None:
            print(f"no job {job_id}", file=sys.stderr)
            return 2
        company = s.get(Company, job.company_id)
        text = html_to_text(job.description_html)
        title = job.title
    result = validate_quotes(await ctx.provider.analyze(title, text), text)
    print(
        json.dumps(
            {"company": company.name, "title": title, **result.model_dump()},
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def sync() -> int:
    ctx = build_ctx(get_settings())
    with ctx.session_factory() as s:
        sync_registry(s, load_registry(ROOT / "config" / "sources.yaml"))
        s.commit()
        n = len(s.scalars(select(Source).where(Source.enabled.is_(True))).all())
    print(f"registry synced at {datetime.now(UTC):%Y-%m-%d %H:%M} UTC: {n} enabled sources")
    return 0


def reindex() -> int:
    """Fill the search index and degree flags for every job (safe to re-run)."""
    from app.core.models import Job  # noqa: PLC0415
    from app.pipeline.derived import refresh_derived  # noqa: PLC0415

    ctx = build_ctx(get_settings())
    with ctx.session_factory() as s:
        ids = list(s.scalars(select(Job.id).order_by(Job.id)))
        for i in range(0, len(ids), 500):
            refresh_derived(s, ids[i : i + 500])
            s.commit()
    print(f"reindexed {len(ids)} jobs")
    return 0


def set_password() -> int:
    """Ask for the dashboard password and print the line to put in .env."""
    import getpass  # noqa: PLC0415

    from app.core.secrets import hash_password  # noqa: PLC0415

    pw = getpass.getpass("Dashboard password: ")
    if len(pw) < 8:
        print("Use at least 8 characters.", file=sys.stderr)
        return 1
    if getpass.getpass("Again: ") != pw:
        print("The two passwords don't match.", file=sys.stderr)
        return 1
    print("Add this line to .env, then restart the api:")
    # Single quotes stop .env loaders from treating the hash's "$" as variables.
    print(f"DASHBOARD_PASSWORD_HASH='{hash_password(pw)}'")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync-registry")
    lc = sub.add_parser("live-check")
    lc.add_argument("--source")
    lc.add_argument("--mode", choices=["incremental", "full"], default="full")
    ro = sub.add_parser("run-once")
    ro.add_argument("--mode", choices=["incremental", "full", "tracked"], required=True)
    ro.add_argument("--source")
    ao = sub.add_parser("analyze-one")
    ao.add_argument("--job-id", type=int, required=True)
    sub.add_parser("reindex")
    sub.add_parser("set-password")
    a = ap.parse_args(argv)
    if a.cmd == "set-password":
        return set_password()
    if a.cmd == "reindex":
        return reindex()
    if a.cmd == "sync-registry":
        return sync()
    if a.cmd == "live-check":
        return asyncio.run(live_check(a.source, a.mode))
    if a.cmd == "run-once":
        return asyncio.run(run_once(a.mode, a.source))
    return asyncio.run(analyze_one(a.job_id))


if __name__ == "__main__":
    sys.exit(main())
