"""Migrations build the same schema the models describe."""

import sqlite3

from alembic import command
from alembic.config import Config


def test_upgrade_adds_the_scrape_run_indexes(tmp_path, monkeypatch):
    db = tmp_path / "jobs.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    command.upgrade(Config("alembic.ini"), "head")
    names = {r[1] for r in sqlite3.connect(db).execute("PRAGMA index_list('scrape_runs')")}
    assert {"ix_scrape_runs_source_started", "ix_scrape_runs_kind_started"} <= names
    command.downgrade(Config("alembic.ini"), "0003")
    names = {r[1] for r in sqlite3.connect(db).execute("PRAGMA index_list('scrape_runs')")}
    assert "ix_scrape_runs_source_started" not in names


def test_closed_alerts_table_starts_with_jobs_already_closed(tmp_path, monkeypatch):
    """Jobs that closed before the upgrade must not all get a "Closed" message at once."""
    db = tmp_path / "jobs.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    command.upgrade(Config("alembic.ini"), "0004")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO companies (id, slug, name, supported) VALUES (1, 'g', 'G', 1)")
    for i, (state, tag) in enumerate(
        [("closed", "liked"), ("closed", "applied"), ("closed", "dismissed"), ("open", "liked")]
    ):
        con.execute(
            "INSERT INTO jobs (id, company_id, source_ids, external_id, url, title, locations,"
            " country_codes, platform_flags, content_hash, analysis_state, state, missed_sweeps,"
            " missed_by_source, first_seen_at, last_seen_at, closed_at) VALUES (?, 1, '[]', ?,"
            " 'u', 't', '[]', '[]', '{}', 'h', 'pending', ?, 0, '{}', '2026-11-01 00:00:00.000000',"
            " '2026-11-02 00:00:00.000000', ?)",
            (i + 1, str(i), state, "2026-11-03 00:00:00.000000" if state == "closed" else None),
        )
        con.execute("INSERT INTO job_user_state (job_id, tag) VALUES (?, ?)", (i + 1, tag))
    con.commit()
    command.upgrade(Config("alembic.ini"), "head")
    rows = sqlite3.connect(db).execute("SELECT job_id, message_id FROM closed_alerts").fetchall()
    assert sorted(rows) == [(1, None), (2, None)]
    command.downgrade(Config("alembic.ini"), "0004")
    tables = {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master")}
    assert "closed_alerts" not in tables
