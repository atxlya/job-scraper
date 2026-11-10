import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backup.py"


def make_db(path: Path, rows: int) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, title TEXT)")
    con.executemany("INSERT INTO jobs (title) VALUES (?)", [(f"t{i}",) for i in range(rows)])
    con.commit()
    con.close()


def test_backup_creates_valid_db(tmp_path):
    db, out = tmp_path / "jobs.db", tmp_path / "backups"
    make_db(db, 3)
    subprocess.run([sys.executable, str(SCRIPT), str(db), str(out)], check=True)
    [copy] = list(out.glob("jobs-*.db"))
    assert sqlite3.connect(copy).execute("SELECT count(*) FROM jobs").fetchone()[0] == 3


def test_backup_prunes_older_than_30_days(tmp_path):
    db, out = tmp_path / "jobs.db", tmp_path / "backups"
    make_db(db, 1)
    out.mkdir()
    old, recent = out / "jobs-20260901.db", out / "jobs-20261101.db"
    for f in (old, recent):
        f.write_bytes(b"x")
    now = time.time()
    os.utime(old, (now - 31 * 86400, now - 31 * 86400))
    os.utime(recent, (now - 9 * 86400, now - 9 * 86400))
    subprocess.run([sys.executable, str(SCRIPT), str(db), str(out)], check=True)
    names = sorted(p.name for p in out.glob("jobs-*.db"))
    assert old.name not in names and recent.name in names and len(names) == 2
