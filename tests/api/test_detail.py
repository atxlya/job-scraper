from datetime import UTC, datetime

from app.api.deps import now
from app.core.models import JobChange

from .conftest import HOUR, MIN, T0, seed_job


def detail(client, j):
    return client.get(f"/api/jobs/{j.id}").json()


def test_description_html_is_sanitised(client, db):
    j = seed_job(
        db,
        description='<p onclick="x()">Hi<script>alert(1)</script>'
        '<img src=x onerror=alert(1)><a href="javascript:x">l</a>'
        '<a href="https://ok.example/apply">ok</a></p>',
    )
    html = detail(client, j)["description_html"]
    assert "script" not in html and "onerror" not in html and "onclick" not in html
    assert "javascript:" not in html and "<img" not in html
    assert "Hi" in html and 'href="https://ok.example/apply"' in html
    assert 'rel="noopener noreferrer nofollow"' in html


def test_sections_replace_description_when_analysed(client, db):
    sec = {
        "about": "A",
        "responsibilities": ["r"],
        "requirements": [],
        "preferred": [],
        "eligibility": [],
    }
    j = seed_job(db, analysis="ok", sections=sec)
    d = detail(client, j)
    assert d["sections"] == sec and d["description_html"] is None and d["has_description"]


def test_detail_fields(client, db):
    j = seed_job(db, title="Software PhD Intern", analysis="warn", quote="US only")
    d = detail(client, j)
    assert d["eligibility"] == "warn" and d["degree"] == "PhD" and d["quote"] == "US only"
    assert d["url"] == f"https://jobs.example/{j.id}" and d["external_id"] == j.external_id
    assert d["checking"] is False and d["unclear"] is False and d["note"] is None


def test_no_description(client, db):
    j = seed_job(db, description=None)
    d = detail(client, j)
    assert d["has_description"] is False and d["description_html"] is None


def test_detail_lists_changes_and_tag_history(client, db):
    j = seed_job(db)
    db.add(JobChange(job_id=j.id, changed_at=T0 + HOUR, fields=["description"]))
    db.commit()
    client.put(f"/api/jobs/{j.id}/tag", json={"tag": "liked"})
    d = detail(client, j)
    assert d["changes"] == [{"at": "2026-11-10T09:00:00Z", "fields": ["description"]}]
    assert [(e["from_tag"], e["to_tag"]) for e in d["tag_history"]] == [(None, "liked")]


def test_tag_toggle_records_history_once(client, db):
    j = seed_job(db)
    client.put(f"/api/jobs/{j.id}/tag", json={"tag": "liked"})
    client.put(f"/api/jobs/{j.id}/tag", json={"tag": "liked"})
    d = client.put(f"/api/jobs/{j.id}/tag", json={"tag": None}).json()
    assert d["tag"] is None
    assert [(e["from_tag"], e["to_tag"]) for e in d["tag_history"]] == [
        (None, "liked"),
        ("liked", None),
    ]


def test_applied_with_date_and_note(client, db):
    j = seed_job(db)
    d = client.put(
        f"/api/jobs/{j.id}/tag",
        json={"tag": "applied", "event_date": "2026-11-12", "note": "via referral"},
    ).json()
    assert d["tag"] == "applied"
    e = d["tag_history"][-1]
    assert e["event_date"] == "2026-11-12" and e["note"] == "via referral"


def test_note_saved_and_capped(client, db):
    j = seed_job(db)
    assert client.put(f"/api/jobs/{j.id}/note", json={"note": "OA on 14 Dec"}).status_code == 204
    assert detail(client, j)["note"] == "OA on 14 Dec"
    assert client.put(f"/api/jobs/{j.id}/note", json={"note": "x" * 5001}).status_code == 422


def test_note_keeps_tag_and_tag_keeps_note(client, db):
    j = seed_job(db)
    client.put(f"/api/jobs/{j.id}/note", json={"note": "n"})
    client.put(f"/api/jobs/{j.id}/tag", json={"tag": "liked"})
    d = detail(client, j)
    assert d["note"] == "n" and d["tag"] == "liked"


def test_open_marks_seen(client, db):
    j = seed_job(db)
    assert client.get("/api/jobs").json()["items"][0]["is_new"] is True
    assert client.post(f"/api/jobs/{j.id}/seen").status_code == 204
    assert client.get("/api/jobs").json()["items"][0]["is_new"] is False


def test_mark_all_seen_spares_jobs_after_up_to(client, app, db):
    app.dependency_overrides[now] = lambda: T0 + 30 * MIN
    old = seed_job(db, first_seen=T0)
    seed_job(db, first_seen=T0 - HOUR, seen=True)  # already seen: not counted again
    page = client.get("/api/jobs").json()
    late = seed_job(db, first_seen=T0 + HOUR)  # arrives while reading
    r = client.post("/api/jobs/mark-seen", json={"up_to": page["loaded_at"]})
    assert r.json() == {"marked": 1}
    new = {j["id"]: j["is_new"] for j in client.get("/api/jobs").json()["items"]}
    assert new[old.id] is False and new[late.id] is True


def test_mark_all_seen_exact_boundary(client, db):
    j = seed_job(db, first_seen=datetime(2026, 11, 10, 8, 0, 0, 500000, tzinfo=UTC))
    r = client.post("/api/jobs/mark-seen", json={"up_to": "2026-11-10T08:00:00.500000Z"})
    assert r.json() == {"marked": 1}
    assert client.get("/api/jobs").json()["items"][0]["id"] == j.id


def test_unknown_job_404(client):
    for r in (
        client.get("/api/jobs/999"),
        client.put("/api/jobs/999/tag", json={"tag": "liked"}),
        client.post("/api/jobs/999/seen"),
    ):
        assert r.status_code == 404 and r.json()["detail"] == "Job not found"


def test_tag_body_must_be_json(client, db):
    j = seed_job(db)
    r = client.put(f"/api/jobs/{j.id}/tag", data={"tag": "liked"})
    assert r.status_code == 422
    assert client.put(f"/api/jobs/{j.id}/tag", json={"tag": "loved"}).status_code == 422
