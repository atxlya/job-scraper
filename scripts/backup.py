"""Nightly SQLite backup with 30-day retention.

    python scripts/backup.py DB_PATH OUT_DIR [--keep-days 30] [--loop --at 03:00]

Uses SQLite's online backup API, so it is safe while the worker is writing.
--loop runs forever and backs up once a day at --at (Asia/Kolkata).
"""

import argparse
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def backup(db: Path, out: Path, keep_days: int) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"jobs-{datetime.now(IST):%Y%m%d}.db"
    tmp = target.with_suffix(".db.part")
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    dst = sqlite3.connect(tmp)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    tmp.replace(target)
    cutoff = time.time() - keep_days * 86400
    for old in out.glob("jobs-*.db"):
        if old != target and old.stat().st_mtime < cutoff:
            old.unlink()
    return target


def seconds_until(at: str) -> float:
    hour, minute = (int(x) for x in at.split(":"))
    now = datetime.now(IST)
    nxt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("db", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--keep-days", type=int, default=30)
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--at", default="03:00")
    a = ap.parse_args()
    if not a.loop:
        print(backup(a.db, a.out, a.keep_days))
        return
    while True:
        time.sleep(seconds_until(a.at))
        if a.db.exists():
            print(backup(a.db, a.out, a.keep_days), flush=True)


if __name__ == "__main__":
    main()
