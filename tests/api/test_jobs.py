from .conftest import DAY, T0, seed_job


def ids(client, query=""):
    return [j["id"] for j in client.get(f"/api/jobs{query}").json()["items"]]


def test_default_view_is_open_tech_internships_newest_first(client, db):
    a = seed_job(db, title="Software Intern", posted=T0)
    b = seed_job(db, title="Data Intern", posted=T0 + DAY)
    seed_job(db, title="HR Intern", tech=False)
    seed_job(db, title="Senior Engineer", intern=False)
    seed_job(db, title="Closed Intern", state="closed")
    assert ids(client) == [b.id, a.id]


def test_card_fields(client, db):
    j = seed_job(
        db,
        title="ML Intern",
        locations=["Bengaluru, India", "Pune, India", "Hyderabad, India"],
        posted=T0,
    )
    page = client.get("/api/jobs").json()
    assert page["total"] == 1 and "loaded_at" in page
    card = page["items"][0]
    assert card == {
        "id": j.id,
        "company": "Google",
        "company_slug": "google",
        "title": "ML Intern",
        "location": "Bengaluru, India · Pune, India +1",
        "posted_at": "2026-11-10T08:00:00Z",
        "first_seen_at": "2026-11-10T08:00:00Z",
        "is_new": True,
        "eligibility": "pending",
        "tag": None,
        "closed": False,
    }


def test_all_view_includes_non_tech(client, db):
    seed_job(db, title="Software Intern")
    seed_job(db, title="HR Intern", tech=False)
    seed_job(db, title="Senior Engineer", intern=False)
    assert len(ids(client, "?view=all")) == 3


def test_closed_but_applied_stays_visible(client, db):
    j = seed_job(db, state="closed", tag="applied")
    seed_job(db, title="Closed and liked", state="closed", tag="liked")
    seed_job(db, title="Closed untagged", state="closed")
    items = client.get("/api/jobs").json()["items"]
    assert {i["id"] for i in items} == {j.id, j.id + 1}
    assert all(i["closed"] for i in items)


def test_dismissed_hidden_unless_asked(client, db):
    j = seed_job(db, tag="dismissed")
    assert client.get("/api/jobs").json()["total"] == 0
    assert ids(client, "?dismissed=true") == [j.id]


def test_eligibility_filter_matches_badge(client, db):
    ok = seed_job(db, analysis="ok")
    phd = seed_job(db, title="Software PhD Intern", analysis="ok")
    warn = seed_job(db, analysis="warn", quote="US students only")
    pend = seed_job(db)
    unclear = seed_job(db, analysis="unknown")

    def got(e):
        return {
            j["id"]: j["eligibility"] for j in client.get(f"/api/jobs?elig={e}").json()["items"]
        }

    assert got("ok") == {ok.id: "ok"}
    assert got("warn") == {phd.id: "warn", warn.id: "warn"}
    assert got("pending") == {pend.id: "pending", unclear.id: "pending"}
    assert len(ids(client, "?elig=ok&elig=warn")) == 3


def test_india_includes_remote(client, db):
    india = seed_job(db, countries=("IN",))
    remote_us = seed_job(db, countries=("US",), remote="remote")
    seed_job(db, countries=("US",))
    assert set(ids(client, "?loc=india")) == {india.id, remote_us.id}


def test_country_filter(client, db):
    us = seed_job(db, countries=("US", "GB"))
    seed_job(db, countries=("IN",))
    assert ids(client, "?loc=GB") == [us.id]


def test_posted_falls_back_to_first_seen(client, app, db):
    from app.api.deps import now

    app.dependency_overrides[now] = lambda: T0 + 2 * DAY
    j = seed_job(db, posted=None, first_seen=T0)
    assert ids(client, "?posted=7d") == [j.id]
    assert ids(client, "?posted=1d") == []
    old_post = seed_job(db, posted=T0 - 10 * DAY, first_seen=T0 + DAY)
    assert old_post.id not in ids(client, "?posted=7d")


def test_tag_untagged_and_company_filters_combine(client, db):
    g_plain = seed_job(db, company="Google")
    seed_job(db, company="Google", tag="liked")
    seed_job(db, company="NVIDIA")
    assert ids(client, "?tag=untagged&company=google") == [g_plain.id]
    assert len(ids(client, "?tag=untagged&tag=liked&company=google")) == 2


def test_search_finds_description_words(client, db):
    j = seed_job(db, description="<p>Kubernetes operators</p>")
    seed_job(db, description="<p>Nothing relevant</p>")
    assert ids(client, "?q=kubern") == [j.id]


def test_search_with_fts_syntax_is_200(client, db):
    seed_job(db)
    for q in ["%22NEAR(", "AND", "-", "*", "%28"]:
        assert client.get(f"/api/jobs?q={q}").status_code == 200


def test_paging_total_and_limit_cap(client, db):
    for d in range(3):
        seed_job(db, posted=T0 + d * DAY)
    page = client.get("/api/jobs?limit=2").json()
    assert page["total"] == 3 and len(page["items"]) == 2
    rest = client.get("/api/jobs?limit=2&offset=2").json()
    assert len(rest["items"]) == 1
    assert client.get("/api/jobs?limit=500").status_code == 422


def test_bad_filter_values_422(client):
    assert client.get("/api/jobs?view=nope").status_code == 422
    assert client.get("/api/jobs?elig=bogus").status_code == 422


def test_filter_options_count_within_view(client, db):
    seed_job(db, company="Google", countries=("IN",))
    seed_job(db, company="Google", title="HR Intern", tech=False, countries=("US",))
    seed_job(db, company="NVIDIA", countries=("IN",))
    tech = client.get("/api/filters").json()
    assert tech["companies"] == [
        {"value": "google", "label": "Google", "count": 1},
        {"value": "nvidia", "label": "NVIDIA", "count": 1},
    ]
    assert tech["countries"] == [{"value": "IN", "label": "India", "count": 2}]
    every = client.get("/api/filters?view=all").json()
    assert every["companies"][0] == {"value": "google", "label": "Google", "count": 2}
    assert {"value": "US", "label": "United States", "count": 1} in every["countries"]
