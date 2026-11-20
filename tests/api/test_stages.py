"""Stages after Applied: PUT /api/jobs/{id}/stage and GET /api/applications."""

from app.api.deps import now
from tests.api.conftest import DAY, T0, seed_job


def apply(client, j, on="2026-11-03", note=None):
    body = {"tag": "applied", "event_date": on}
    if note:
        body["note"] = note
    return client.put(f"/api/jobs/{j.id}/tag", json=body).json()


def stage(client, j, s, on=None, note=None):
    return client.put(f"/api/jobs/{j.id}/stage", json={"stage": s, "event_date": on, "note": note})


def test_stage_needs_applied_first(client, db):
    j = seed_job(db)
    r = stage(client, j, "oa")
    assert r.status_code == 409 and r.json()["detail"] == "Mark it Applied first."


def test_unknown_job_is_404(client):
    assert stage(client, type("J", (), {"id": 999})(), "oa").status_code == 404


def test_bad_stage_is_422(client, db):
    j = seed_job(db)
    apply(client, j)
    assert stage(client, j, "hired").status_code == 422


def test_detail_shows_stage_steps_and_history(client, db):
    j = seed_job(db)
    apply(client, j, note="via referral")
    stage(client, j, "oa", on="2026-11-08", note="HackerRank")
    d = stage(client, j, "interview", on="2026-11-12").json()
    assert d["tag"] == "applied" and d["stage"] == "interview"
    assert [(s["stage"], s["on"], s["note"]) for s in d["steps"]] == [
        ("applied", "2026-11-03", "via referral"),
        ("oa", "2026-11-08", "HackerRank"),
        ("interview", "2026-11-12", None),
    ]
    assert [(e["from_stage"], e["to_stage"]) for e in d["tag_history"]] == [
        (None, None),
        (None, "oa"),
        ("oa", "interview"),
    ]


def test_card_carries_the_stage(client, db):
    j = seed_job(db)
    apply(client, j)
    stage(client, j, "offer")
    [card] = client.get("/api/jobs").json()["items"]
    assert (card["tag"], card["stage"]) == ("applied", "offer")


def test_closed_applied_job_is_never_hidden(client, db):
    j = seed_job(db, state="closed")
    apply(client, j)
    stage(client, j, "interview")
    items = client.get("/api/jobs", params={"view": "all"}).json()["items"]
    assert [i["id"] for i in items] == [j.id]
    applied = client.get("/api/jobs", params={"view": "all", "tag": "applied"}).json()["items"]
    assert [i["id"] for i in applied] == [j.id]


def test_rejected_leaves_the_job_lists_but_stays_in_applications(client, db):
    j = seed_job(db, title="Rejected Intern")
    other = seed_job(db, title="Live Intern")
    apply(client, j)
    apply(client, other)
    stage(client, j, "rejected")
    for params in ({}, {"view": "all"}, {"tag": "applied"}, {"view": "all", "tag": "applied"}):
        titles = [i["title"] for i in client.get("/api/jobs", params=params).json()["items"]]
        assert titles == ["Live Intern"], params
    csv_text = client.get("/api/jobs.csv", params={"view": "all"}).text
    assert "Rejected Intern" not in csv_text
    apps = client.get("/api/applications").json()
    assert {(a["title"], a["stage"]) for a in apps} == {
        ("Rejected Intern", "rejected"),
        ("Live Intern", None),
    }
    assert client.get(f"/api/jobs/{j.id}").json()["stage"] == "rejected"  # still openable
    stage(client, j, "interview")  # a rejection undone: back in the lists
    titles = {i["title"] for i in client.get("/api/jobs").json()["items"]}
    assert titles == {"Live Intern", "Rejected Intern"}


def test_stats_counts_rejections_apart_and_dates_the_apply(client, app, db):
    app.dependency_overrides[now] = lambda: T0 + DAY
    a, b, c = seed_job(db), seed_job(db, company="NVIDIA"), seed_job(db, company="Barclays")
    for j in (a, b, c):
        apply(client, j)
    app.dependency_overrides[now] = lambda: T0 + 5 * DAY
    stage(client, b, "interview")
    stage(client, c, "rejected")
    st = client.get("/api/stats").json()
    assert (st["applied"], st["rejected"]) == (2, 1)  # matches the Applied list
    assert st["last_applied_at"] == "2026-11-11T08:00:00Z"  # the apply, not the stage step


def test_removing_applied_clears_the_stage(client, db):
    j = seed_job(db)
    apply(client, j)
    stage(client, j, "oa")
    d = client.put(f"/api/jobs/{j.id}/tag", json={"tag": None}).json()
    assert d["stage"] is None and d["steps"] == []
    assert stage(client, j, "oa").status_code == 409


def test_back_to_just_applied(client, db):
    j = seed_job(db)
    apply(client, j)
    stage(client, j, "oa")
    d = stage(client, j, None).json()
    assert d["stage"] is None
    assert [s["stage"] for s in d["steps"]] == ["applied", "oa", "applied"]


def test_applications_lists_every_applied_job_newest_step_first(client, app, db):
    app.dependency_overrides[now] = lambda: T0
    old = seed_job(db, title="Old Intern")
    apply(client, old, on="2026-10-20")
    stage(client, old, "offer", on="2026-11-10")
    new = seed_job(db, company="NVIDIA", title="New Intern")
    apply(client, new, on="2026-11-11")
    seed_job(db, title="Liked one", tag="liked")
    seed_job(db, title="Dismissed one", tag="dismissed")
    rows = client.get("/api/applications").json()
    assert [(r["title"], r["stage"], r["last_on"]) for r in rows] == [
        ("New Intern", None, "2026-11-11"),
        ("Old Intern", "offer", "2026-11-10"),
    ]
    first = rows[1]
    assert first["company"] == "Google" and first["closed"] is False
    assert [(s["stage"], s["on"]) for s in first["steps"]] == [
        ("applied", "2026-10-20"),
        ("offer", "2026-11-10"),
    ]


def test_applications_needs_login(anon):
    assert anon.get("/api/applications").status_code == 401


def test_applications_uses_two_queries(client, db):
    from sqlalchemy import event

    for i in range(5):
        apply(client, seed_job(db, title=f"Intern {i}"))
    engine = client.app.state.session_factory.kw["bind"]
    statements: list[str] = []

    def count(conn, cur, stmt, params, ctx, many):
        statements.append(stmt)

    event.listen(engine, "before_cursor_execute", count)
    try:
        assert len(client.get("/api/applications").json()) == 5
    finally:
        event.remove(engine, "before_cursor_execute", count)
    work = [s for s in statements if "tag_history" in s or "job_user_state" in s]
    assert len(work) == 2  # the jobs, then all their history; not one query per job
