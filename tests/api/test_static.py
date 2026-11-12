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


# --- home-screen app (PWA) ------------------------------------------------------------------

import json  # noqa: E402
from pathlib import Path  # noqa: E402

PUBLIC = Path(__file__).resolve().parents[2] / "web" / "public"


def test_manifest_is_served_without_login_as_manifest_json(tmp_path, monkeypatch):
    import starlette.responses  # noqa: PLC0415

    # The Pi's slim image may have no /etc/mime.types: don't rely on the system table.
    monkeypatch.setattr(starlette.responses, "guess_type", lambda *a, **k: (None, None))
    c = app_with_dist(tmp_path)
    (tmp_path / "dist" / "manifest.webmanifest").write_text('{"name": "Job Scraper"}')
    r = c.get("/manifest.webmanifest")  # no login
    assert r.status_code == 200 and r.json() == {"name": "Job Scraper"}
    assert r.headers["content-type"].startswith("application/manifest+json")
    assert r.headers["cache-control"] == "no-cache"


def test_icons_are_served_without_login(tmp_path):
    c = app_with_dist(tmp_path)
    (tmp_path / "dist" / "icons").mkdir()
    (tmp_path / "dist" / "icons" / "icon-192.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    r = c.get("/icons/icon-192.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_api_still_needs_login_next_to_the_manifest(tmp_path):
    c = app_with_dist(tmp_path)
    assert c.get("/api/jobs").status_code == 401


def png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n", path
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def test_the_real_manifest_and_its_icons():
    m = json.loads((PUBLIC / "manifest.webmanifest").read_text())
    assert m["name"] == "Job Scraper" and m["short_name"] == "Jobs"
    assert (m["start_url"], m["scope"], m["display"]) == ("/", "/", "standalone")
    assert m["theme_color"] and m["background_color"]
    by_purpose = {(i["sizes"], i.get("purpose", "any")): i for i in m["icons"]}
    assert set(by_purpose) == {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")}
    for (sizes, _), icon in by_purpose.items():
        w, h = png_size(PUBLIC / icon["src"].lstrip("/"))
        assert f"{w}x{h}" == sizes and icon["type"] == "image/png"
    assert png_size(PUBLIC / "icons" / "apple-touch-icon.png") == (180, 180)


def test_index_html_links_the_manifest_and_has_no_service_worker():
    html = (PUBLIC.parent / "index.html").read_text()
    for tag in (
        '<link rel="manifest" href="/manifest.webmanifest" />',
        '<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />',
        '<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)" />',
        '<meta name="theme-color" content="#171a21" media="(prefers-color-scheme: dark)" />',
        '<meta name="apple-mobile-web-app-title" content="Jobs" />',
    ):
        assert tag in html, tag
    src = PUBLIC.parent / "src"
    assert not any("serviceWorker" in p.read_text() for p in src.rglob("*.ts*")), "no offline mode"
