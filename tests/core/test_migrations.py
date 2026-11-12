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
