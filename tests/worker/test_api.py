from fastapi.testclient import TestClient

from tests.api.conftest import make_app


def test_healthz(tmp_path):
    with TestClient(make_app(tmp_path)) as c:
        assert c.get("/healthz").json() == {"db": "ok", "last_run_at": None}
