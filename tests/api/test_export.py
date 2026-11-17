"""GET /api/jobs.csv: the jobs list's current filters, as a streamed CSV download."""

import csv
import io
from datetime import UTC, datetime

from app.api import jobs as jobs_api
from app.api.deps import now
from tests.api.conftest import DAY, T0, make_app, seed_job

HEADER = [
    "Company",
    "Title",
    "Category",
    "Locations",
    "Apply URL",
    "Dashboard URL",
    "About",
    "Responsibilities",
    "Requirements",
    "Preferred",
    "Description",
]


def rows(resp) -> list[list[str]]:
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))


def test_needs_login(anon):
    assert anon.get("/api/jobs.csv").status_code == 401


def test_header_and_one_row(client, app, db):
    app.dependency_overrides[now] = lambda: datetime(2026, 11, 12, 20, 0, tzinfo=UTC)  # 13th IST
    j = seed_job(
        db,
        title="Software Engineering Intern",
        locations=["Bengaluru, India", "Pune, India"],
        posted=T0,
        analysis="ok",
    )
    r = client.get("/api/jobs.csv")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert r.headers["content-disposition"] == 'attachment; filename="jobs-2026-11-13.csv"'
    assert r.content.startswith(b"\xef\xbb\xbf")  # BOM: Excel reads it as UTF-8
    header, row = rows(r)
    assert header == HEADER
    assert row == [
        "Google",
        "Software Engineering Intern",
        "",  # not sorted yet
        "Bengaluru, India; Pune, India",
        j.apply_url,
        f"http://testserver/jobs/{j.id}",
        "",
        "",
        "",
        "",
        "x",  # no summary yet, so the full posting
    ]


def test_uses_the_same_filters_as_the_list(client, db):
    seed_job(db, company="Google", title="Data Intern")
    seed_job(db, company="NVIDIA", title="GPU Intern", tag="liked")
    seed_job(db, company="NVIDIA", title="HR Intern", tech=False)
    seed_job(db, company="NVIDIA", title="Dismissed Intern", tag="dismissed")
    for query in (
        "",
        "?company=nvidia",
        "?view=all&company=nvidia",
        "?tag=liked",
        "?dismissed=true",
    ):
        listed = [i["title"] for i in client.get(f"/api/jobs{query}").json()["items"]]
        exported = [r[1] for r in rows(client.get(f"/api/jobs.csv{query}"))[1:]]
        assert exported == listed, query


def test_bad_filter_is_422(client):
    assert client.get("/api/jobs.csv?loc=nowhere").status_code == 422


def test_dashboard_url_setting_wins(tmp_path):
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from tests.api.conftest import PASSWORD  # noqa: PLC0415

    app = make_app(tmp_path, dashboard_url="http://pi:8000/")
    with app.state.session_factory() as s:
        j = seed_job(s)
    with TestClient(app) as c:
        c.post("/api/login", json={"password": PASSWORD})
        assert rows(c.get("/api/jobs.csv"))[1][5] == f"http://pi:8000/jobs/{j.id}"


# Text a spreadsheet would run as a formula (OWASP's list: = + - @ tab, carriage return).
# Titles and locations come from third-party sites, so every text cell gets the guard.
def test_cells_that_look_like_formulas_are_neutralised(client, db):
    for title in (
        '=HYPERLINK("http://x","Apply")',
        "+91 Intern",
        "-Software Intern",
        "@Intern",
        "\tTab Intern",
        "\rCR Intern",
    ):
        seed_job(db, title=title, locations=["=1+1"])
    for r in rows(client.get("/api/jobs.csv?view=all"))[1:]:
        assert r[1][0] == "'" and r[3] == "'=1+1", r


def test_ordinary_cells_are_left_alone(client, db):
    seed_job(db, title="C++ / Embedded Intern - 2027", locations=["São Paulo, Brazil"])
    r = rows(client.get("/api/jobs.csv"))[1]
    assert [r[1], r[3]] == ["C++ / Embedded Intern - 2027", "São Paulo, Brazil"]


def test_streamed_in_batches(client, db, monkeypatch):
    monkeypatch.setattr(jobs_api, "EXPORT_BATCH", 50)
    for i in range(120):
        seed_job(db, title=f"Intern {i:03}", description="<p>" + "x" * 5000 + "</p>")
    statements: list[str] = []
    from sqlalchemy import event  # noqa: PLC0415

    engine = client.app.state.session_factory.kw["bind"]

    def spy(conn, cur, stmt, params, ctx, many):
        statements.append(stmt)

    event.listen(engine, "before_cursor_execute", spy)
    try:
        with client.stream("GET", "/api/jobs.csv") as r:
            chunks = list(r.iter_bytes())
    finally:
        event.remove(engine, "before_cursor_execute", spy)
    body = b"".join(chunks).decode("utf-8-sig")
    assert len(rows_of(body)) == 121  # header + 120 rows
    assert len(chunks) >= 3  # sent as each batch is written, not all at the end
    export = [s for s in statements if "FROM jobs" in s and "jobs_fts" not in s]
    assert export and all("LIMIT" not in s for s in export)  # one query, read in batches


def rows_of(body: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(body)))


def test_description_and_gemini_sections(client, db):
    seed_job(
        db,
        title="ML Intern",
        analysis="ok",
        sections={
            "about": "Train models.",
            "responsibilities": ["Write code", "Run experiments"],
            "requirements": ["Python", "-Linear algebra"],
            "preferred": [],
            "eligibility": ["Final-year students"],
        },
        description=(
            "<h3>About</h3><p>We build <b>models</b>.</p>"
            "<ul><li>Python</li><li>PyTorch</li></ul><p>Line<br>break</p>"
        ),
    )
    row = rows(client.get("/api/jobs.csv"))[1]
    about, resp, req, pref, desc = row[6:]
    assert about == "Train models."
    assert resp == "• Write code\n• Run experiments"
    assert req == "• Python\n• -Linear algebra"
    assert pref == ""
    assert desc == ""  # summarised, so the long posting is left out


def test_not_yet_read_by_gemini_still_has_the_description(client, db):
    seed_job(db, description="<p>Hello</p>")
    row = rows(client.get("/api/jobs.csv"))[1]
    assert row[6:] == ["", "", "", "", "Hello"]


def test_posting_is_plain_text_a_line_per_paragraph(client, db):
    seed_job(
        db,
        description=(
            "<h3>About</h3><p>We build <b>models</b>.</p>"
            "<ul><li>Python</li><li>PyTorch</li></ul><p>Line<br>break</p>"
        ),
    )
    desc = rows(client.get("/api/jobs.csv"))[1][10]
    assert desc == "About\nWe build models.\n• Python\n• PyTorch\nLine\nbreak"


def test_read_but_empty_summary_keeps_the_posting(client, db):
    seed_job(db, analysis="ok", sections={}, description="<p>Hello</p>")
    assert rows(client.get("/api/jobs.csv"))[1][10] == "Hello"


def test_description_is_guarded_and_cut_to_fit_a_cell(client, db):
    seed_job(db, title="A Intern", description="<p>=cmd()</p>")
    seed_job(db, title="B Intern", description="<p>" + "y" * 40_000 + "</p>", first_seen=T0 - DAY)
    got = {r[1]: r[10] for r in rows(client.get("/api/jobs.csv"))[1:]}
    assert got["A Intern"] == "'=cmd()"
    assert len(got["B Intern"]) == jobs_api.CELL_MAX and got["B Intern"].endswith("…")


def test_category_column_and_filter(client, db):
    a = seed_job(db, title="ML Intern")
    b = seed_job(db, title="Quant Intern", first_seen=T0 - DAY)
    seed_job(db, title="Unsorted Intern", first_seen=T0 - 2 * DAY)
    a.category, b.category = "ml", "quant"
    db.commit()
    got = {r[1]: r[2] for r in rows(client.get("/api/jobs.csv"))[1:]}
    assert got == {"ML Intern": "ML / AI", "Quant Intern": "Quant", "Unsorted Intern": ""}
    only = rows(client.get("/api/jobs.csv?category=ml&category=quant"))[1:]
    assert sorted(r[1] for r in only) == ["ML Intern", "Quant Intern"]
