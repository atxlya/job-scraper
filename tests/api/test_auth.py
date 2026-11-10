from fastapi.testclient import TestClient

from app.cli import main as cli_main
from app.core.secrets import verify_password
from app.core.settings import Settings

from .conftest import PASSWORD, make_app


def test_login_sets_http_only_strict_cookie(anon):
    r = anon.post("/api/login", json={"password": PASSWORD})
    assert r.status_code == 204
    c = r.headers["set-cookie"].lower()
    assert "httponly" in c and "samesite=strict" in c and "secure" not in c
    assert anon.get("/api/me").json() == {"ok": True}


def test_cookie_secure_when_dashboard_is_https(tmp_path):
    with TestClient(make_app(tmp_path, dashboard_url="https://pi.tail.ts.net")) as c:
        r = c.post("/api/login", json={"password": PASSWORD})
        assert "secure" in r.headers["set-cookie"].lower()


def test_wrong_password_401_then_throttled(anon):
    for _ in range(5):
        assert anon.post("/api/login", json={"password": "no"}).status_code == 401
    r = anon.post("/api/login", json={"password": PASSWORD})
    assert r.status_code == 429


def test_no_password_configured_503_names_the_command(tmp_path):
    with TestClient(make_app(tmp_path, dashboard_password_hash=None)) as c:
        r = c.post("/api/login", json={"password": "x"})
    assert r.status_code == 503 and "set-password" in r.json()["detail"]


def test_every_api_route_requires_login(anon):
    open_routes = {"/api/login", "/healthz"}
    checked = 0
    # The OpenAPI schema lists every route, including ones in included routers.
    for path, ops in anon.app.openapi()["paths"].items():
        if not path.startswith("/api") or path in open_routes:
            continue
        for m in ops:
            r = anon.request(m.upper(), path.replace("{job_id}", "1"))
            assert r.status_code == 401, f"{m} {path} -> {r.status_code}"
            checked += 1
    assert checked >= 2  # /api/me and /api/logout at least


def test_logout_ends_session(client):
    assert client.post("/api/logout").status_code == 204
    assert client.get("/api/me").status_code == 401


def test_session_survives_app_restart(tmp_path):
    """The signing secret is stored in the DB, so a restart doesn't log you out."""
    app1 = make_app(tmp_path)
    with TestClient(app1) as c:
        c.post("/api/login", json={"password": PASSWORD})
        cookies = dict(c.cookies)
    with TestClient(make_app(tmp_path), cookies=cookies) as c:
        assert c.get("/api/me").status_code == 200


def test_set_password_cli_prints_env_line(monkeypatch, capsys, tmp_path):
    answers = iter(["hunter2hunter2", "hunter2hunter2"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    assert cli_main(["set-password"]) == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("DASHBOARD_PASSWORD_HASH='$argon2id$") and line.endswith("'")
    env = tmp_path / ".env"
    env.write_text(line + "\n")
    s = Settings(_env_file=env)
    assert verify_password(s.dashboard_password_hash, "hunter2hunter2")


def test_set_password_cli_rejects_mismatch_and_short(monkeypatch):
    answers = iter(["hunter2hunter2", "different1", "short", "short"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    assert cli_main(["set-password"]) == 1
    assert cli_main(["set-password"]) == 1
