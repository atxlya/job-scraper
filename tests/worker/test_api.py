from fastapi.testclient import TestClient


def test_healthz(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'jobs.db'}")
    import importlib

    import app.api.main as api
    from app.core.models import Base

    importlib.reload(api)
    Base.metadata.create_all(api._sf.kw["bind"])
    body = TestClient(api.app).get("/healthz").json()
    assert body == {"db": "ok", "last_run_at": None}
