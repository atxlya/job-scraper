from fastapi.testclient import TestClient

from app.api.main import create_app

from .conftest import PASSWORD, make_settings


def app_with_dist(tmp_path):
    from app.core.db import make_engine  # noqa: PLC0415
    from app.core.models import Base  # noqa: PLC0415

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>JS</title>")
    (dist / "assets" / "app-123.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    s = make_settings(tmp_path)
    Base.metadata.create_all(make_engine(s.database_url))
    return TestClient(create_app(s, web_dist=dist))


def test_spa_routes_return_index(tmp_path):
    c = app_with_dist(tmp_path)
    for path in ("/", "/jobs/12", "/sources", "/login?next=%2F"):
        r = c.get(path)
        assert r.status_code == 200 and "<title>JS</title>" in r.text, path
        assert r.headers["cache-control"] == "no-cache"


def test_assets_and_root_files_served(tmp_path):
    c = app_with_dist(tmp_path)
    r = c.get("/assets/app-123.js")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    assert c.get("/favicon.svg").text == "<svg/>"
    assert c.get("/assets/missing.js").status_code == 404


def test_unknown_api_path_stays_json_404(tmp_path):
    c = app_with_dist(tmp_path)
    assert c.get("/api/nope").status_code == 401  # locked by default: not even a 404
    assert c.post("/api/login", json={"password": PASSWORD}).status_code == 204
    r = c.get("/api/nope")
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}


def test_path_traversal_blocked(tmp_path):
    (tmp_path / "secret.txt").write_text("nope")
    c = app_with_dist(tmp_path)
    r = c.get("/..%2Fsecret.txt")
    assert "nope" not in r.text


def test_no_dist_no_spa(tmp_path):
    c = app_with_dist(tmp_path)
    c2 = TestClient(create_app(make_settings(tmp_path), web_dist=tmp_path / "missing"))
    assert c2.get("/").status_code == 404
    assert c.get("/healthz").status_code == 200
