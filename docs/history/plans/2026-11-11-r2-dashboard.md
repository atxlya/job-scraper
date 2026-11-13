# R2a — Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A password-protected web dashboard, served by the existing `api` container, to browse and filter every stored job, read a job's sections and eligibility, tag jobs (Liked / Applied / Dismissed) with notes, see scraper health, and add a company from its careers URL. It follows mockup A, works on phone and laptop, and has light and dark themes.

**Architecture:** FastAPI gains JSON routes under `/api/*`, all behind a signed session cookie, and serves the built React app for every other path. Search uses an SQLite FTS5 table, and a `degree_only` column stores the title-based degree flag so eligibility filters run in SQL. Both are maintained in Python by one `refresh_derived()` call, made from the worker after each ingest and from a `reindex` command. The frontend is React + Vite + TypeScript + Tailwind in `web/`, built in a Node stage of the Docker image. Filter state lives in the URL.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2, Alembic, SQLite FTS5, argon2-cffi, itsdangerous (Starlette sessions), nh3 (HTML sanitising). React 19, Vite, TypeScript (strict), Tailwind CSS 4, React Router 7, TanStack Query 5, `@fontsource-variable/inter`, Vitest + Testing Library.

**Spec:** [docs/DESIGN.md](../../DESIGN.md) §7 (dashboard), §3 (Add company), §4 (data model), §8 (stack). The visual reference is mockup A (`Main.dc.html`) on the [mockups canvas](https://claude.ai/artifact/MNDeo5ywPB3Td9eCdsYgpn). The R1 decisions are in [docs/R1-notes.md](../R1-notes.md). Lever, Greenhouse and the 17 new companies are a separate plan (R2b).

## Decisions this plan makes (the spec is silent or open)

| # | Decision | Why |
|---|---|---|
| D1 | Companies added from the dashboard are stored in the database with `sources.origin = "dashboard"`. `sync_registry` never disables them. | `config/sources.yaml` is baked into the Docker image, and sync disables every source missing from it. |
| D2 | The form detects **Workday, Eightfold and Oracle HCM** URLs. Lever and Greenhouse detection comes with their adapters in R2b. | Those are the platform adapters that exist today. |
| D3 | The password is set with `python -m app.cli set-password`, which prints a `DASHBOARD_PASSWORD_HASH=…` line for `.env`. The cookie-signing secret is generated once and stored in the `settings` table. A session lasts 30 days. | Keeps `.env` to one new line, and nothing secret is committed. |
| D4 | With no password hash set, login answers 503 with the command to run. Every `/api` route except `/api/login` and `/healthz` answers 401 without a session. | The dashboard is never open by accident. |
| D5 | Default view: open tech internships, location **Anywhere**, newest first by `posted_at`, falling back to `first_seen_at`. Filters live in the URL, and the last-used ones are remembered in `localStorage`. | Alerts already cover all locations (§6), and the mockup's "India + Remote" is one click away. |
| D6 | Closed jobs are hidden, except Liked/Applied ones, which stay and show a "Closed" label. Dismissed jobs are hidden unless "Show dismissed" is on. | §4: "A job tagged Applied is never hidden." |
| D7 | "Mark all as seen" marks every job **first seen at or before the moment the list was loaded**. | Jobs that arrive while you read stay new. |
| D8 | A job with no stored description fetches it **on demand** when opened, under the same robots.txt and politeness rules. If the site says it's gone, the job is closed. | R1 stores non-candidates without descriptions (R1-notes, "Detail pages…"). |
| D9 | Posting HTML is sanitised on the server with `nh3` before it reaches the browser. | Descriptions are third-party HTML. |
| D10 | Eligibility badge: **Eligible** (`ok` and no degree flag) · **Check needed** (`warn`, or a degree flag in the title) · **Not checked** (no analysis yet, analysis failed, or `unknown`). | Matches the mockup's three chips, plus the degree warning from 2026-11-11. |
| D11 | Telegram alerts gain a "Dashboard" link when `DASHBOARD_URL` is set. | §6 lists a dashboard link in every alert. |
| D12 | Laptop: three columns (filters · list · detail), with the selected job in `?job=ID`. Phone (< 1024 px): filters fold into a sheet, and tapping a job opens `/jobs/:id`. | Mockup A at its two widths. |
| D13 | The theme follows the system, with a toggle (system / light / dark) remembered in `localStorage`. | §7: light and dark themes. |
| D14 | Fonts are bundled (`@fontsource-variable/inter`), not loaded from Google. | The Pi dashboard should not need the internet to render. |

## Global Constraints

- Python `>=3.13`, `uv`, `ruff check` and `ruff format --check` clean at every commit (line length 100). TypeScript `strict: true`. `npm run check` (tsc + vitest) is clean at every commit that touches `web/`.
- **Never hold a database write open across a network await** (R1 rule). On-demand fetches and test fetches read what they need, close the session, call the network, then open a new session to write.
- **robots.txt is checked before every request**, including the on-demand description fetch and the "Add company" test fetch. All requests go through `PoliteClient`.
- Auth: argon2 password hash; an HTTP-only, `SameSite=Strict` session cookie, `Secure` when `DASHBOARD_URL` starts with `https://`. Mutating routes accept only JSON bodies. No secret is ever committed.
- Closed jobs are never deleted. A Liked or Applied job is never hidden by the default filters (D6).
- Times come from the API as UTC ISO-8601 and are shown in `Asia/Kolkata`.
- Look: mockup A's tokens (below), with dark equivalents. Touch targets ≥ 44 px on phone. Text contrast ≥ 4.5:1 in both themes.
- No new external network calls from the browser: no CDN, no Google Fonts (D14).

**Design tokens (mockup A → CSS variables in `web/src/index.css`)**

| Token | Light | Dark |
|---|---|---|
| `--bg` | `#F6F7F9` | `#0F1115` |
| `--surface` | `#FFFFFF` | `#171A21` |
| `--border` | `#E4E7EC` | `#2A2F3A` |
| `--text` | `#111827` | `#E6E8EC` |
| `--muted` | `#5B6472` | `#9AA3B2` |
| `--accent` / `--accent-hover` | `#2F5BEA` / `#1E3FB0` | `#6E8EF5` / `#9DB2F8` |
| `--ok-fg` / `--ok-bg` / `--ok-bd` | `#1E3FB0` / `#EEF2FE` / `#B7C6F7` | `#B7C6F7` / `#1B2442` / `#33467F` |
| `--warn-fg` / `--warn-bg` / `--warn-bd` | `#8A3B00` / `#FFF4E5` / `#F5C98B` | `#F5C98B` / `#3A2610` / `#6B4518` |
| `--chip-bg` | `#F1F3F5` | `#222733` |

Radius 12 px for cards and 10 px for buttons. Font Inter 14 px / 1.45.

## Review Focus

1. **Posting HTML with `<script>`, `onerror=` or `javascript:` links** must reach the browser stripped (D9). Test: Task 5, `test_description_html_is_sanitised`.
2. **Any `/api` route reached without a session** must answer 401, including routes added later. Test: Task 2, `test_every_api_route_requires_login`, which walks `app.routes`.
3. **Search text with FTS5 syntax** (`"`, `-`, `*`, `AND`, `NEAR(`, a lone `(`) must never cause a 500. It is treated as plain words. Test: Task 1, `test_fts_query_never_raises`.
4. **A job arriving while you read**, then "Mark all as seen", must leave the new job still new (D7). Test: Task 5, `test_mark_all_seen_spares_jobs_after_up_to`.
5. **On-demand fetch when the site is down, robots.txt disallows the page, or the job is gone:** a clear message, no 500, and a gone job closed. Test: Task 6, `test_fetch_description_*`.

---

## File Structure

```
app/
  api/
    main.py          create_app(settings) -> FastAPI; static + SPA fallback; /healthz
    deps.py          get_session(), require_user()
    auth.py          /api/login, /api/logout, /api/me; LoginThrottle
    schemas.py       pydantic response/request models shared by the routers
    jobs.py          /api/jobs, /api/jobs/{id}, tag/note/seen/description, /api/filters, /api/jobs/mark-seen
    sources.py       /api/stats, /api/sources, /api/sources/detect, POST /api/sources
  core/
    eligibility.py   eligibility(job, analysis) -> Eligibility   (shared by alerts + API)
    secrets.py       hash_password(), verify_password(), session_secret(session)
  pipeline/
    derived.py       refresh_derived(session, job_ids); fts_query(text)
    ingest.py        + raw_from_job(), apply_detail()
  sources/
    detect.py        detect(url) -> Detected | None
    checks.py        evaluate(result, mode)   (moved from cli.py)
migrations/versions/0003_dashboard.py
web/                 Vite app (package.json, vite.config.ts, index.html, src/…)
tests/api/           test_auth.py, test_jobs.py, test_detail.py, test_sources.py, test_static.py
tests/pipeline/      test_derived.py
tests/sources/       test_detect.py
```

Test helper used by every `tests/api/*` file. Put it in `tests/api/conftest.py` in Task 2:

```python
@pytest.fixture
def client(tmp_path) -> TestClient:      # logged in, empty file DB (tables + FTS created)
@pytest.fixture
def anon(tmp_path) -> TestClient:        # same app, no session
@pytest.fixture
def db(client) -> Session:               # session on the same DB, for seeding rows
def seed_job(db, company="Google", title="Software Engineering Intern", *, intern=True,
             tech=True, countries=("IN",), first_seen=T0, posted=None, state="open",
             analysis=None, quote=None, tag=None, seen=False, description="<p>x</p>") -> Job
```

`seed_job` also calls `refresh_derived(db, [job.id])`, so FTS and `degree_only` are filled in.

---

### Task 1: Derived fields, search index, source origin

**Files:**
- Create: `migrations/versions/0003_dashboard.py`, `app/pipeline/derived.py`, `tests/pipeline/test_derived.py`
- Modify: `app/core/models.py` (`Job.degree_only`, `Source.origin`), `app/worker/runner.py` (call `refresh_derived` after ingest), `app/cli.py` (`reindex` command), `docker-compose.yml` (`migrate` also runs `reindex`), `app/core/registry.py` (leave `origin="dashboard"` rows alone)

**Interfaces:**
- Produces: `Job.degree_only: str | None` (String(40)), `Source.origin: str` (String(20), default `"registry"`), FTS5 table `jobs_fts(title, company, body)` keyed by `rowid = jobs.id`, `refresh_derived(session, job_ids: Iterable[int]) -> None`, `fts_query(text: str) -> str | None`, CLI `python -m app.cli reindex` (prints `reindexed N jobs`).
- Consumes: `degree_only(title)` from `app/pipeline/classify.py`, `html_to_text` from `app/llm/queue.py`.

- [ ] **Step 1: Write the failing tests** in `tests/pipeline/test_derived.py` (in-memory DB created with `Base.metadata.create_all` plus `create_fts(engine)` from `derived.py`):

```python
def test_refresh_sets_degree_and_search_row(session):
    j = add_job(session, title="Software Engineering PhD Intern", desc="<p>Build <b>compilers</b></p>")
    refresh_derived(session, [j.id])
    assert j.degree_only == "PhD"
    assert search_ids(session, "compilers") == [j.id]      # body text, tags stripped
    assert search_ids(session, "google") == [j.id]         # company name is indexed

def test_refresh_replaces_old_row(session):
    j = add_job(session, title="Data Intern", desc="<p>old words</p>")
    refresh_derived(session, [j.id])
    j.description_html = "<p>new words</p>"
    refresh_derived(session, [j.id])
    assert search_ids(session, "old") == [] and search_ids(session, "new") == [j.id]

@pytest.mark.parametrize("q", ['"', "-", "*", "AND", "NEAR(", "(", "c++", "a OR", "'; drop"])
def test_fts_query_never_raises(session, q):
    add_job(session, title="C++ Intern"); refresh_derived(session, [1])
    search_ids(session, q)                                 # must not raise

def test_fts_query_prefix_matches_words():
    assert fts_query("soft eng") == '"soft"* "eng"*'
    assert fts_query('  "  ') is None

def test_registry_sync_keeps_dashboard_sources(session):
    # a Source with origin="dashboard" missing from the YAML stays enabled after sync_registry
```

`search_ids(session, q)` is a test helper: `SELECT rowid FROM jobs_fts WHERE jobs_fts MATCH :q`, using `fts_query(q)`. It returns `[]` when `fts_query` returns `None`.

- [ ] **Step 2: Run** `uv run pytest tests/pipeline/test_derived.py -v`. Expected: FAIL (`ImportError: refresh_derived`).

- [ ] **Step 3: Implement.**
  - **Migration `0003`:** add the two columns (`origin` with server default `'registry'`). Run `CREATE VIRTUAL TABLE jobs_fts USING fts5(title, company, body, tokenize='unicode61 remove_diacritics 2')`. Add indexes `ix_jobs_kind (is_tech, is_internship, state)` and `ix_jobs_posted (posted_at)`. The downgrade drops all of these.
  - **`create_fts(engine)`:** runs the same `CREATE VIRTUAL TABLE IF NOT EXISTS`. Tests and `create_app` use it when tables come from `create_all`.
  - **`refresh_derived`:** for each job, set `degree_only`, then `DELETE FROM jobs_fts WHERE rowid=:id`, then insert `(id, title, company name, html_to_text(description_html))`.
  - **`fts_query`:** splits on whitespace, drops every character except letters, digits and `+#.`, and wraps each remaining word as `"word"*`. Returns `None` when nothing is left.
  - **Runner:** after `ingest`, call `refresh_derived(s, stats.new_ids + stats.updated_ids)`.
  - **`reindex` CLI:** loops over all job ids in batches of 500. Compose `migrate` command: `alembic upgrade head && python -m app.cli sync-registry && python -m app.cli reindex`.
  - **Registry:** in the disable pass, skip rows whose `origin == "dashboard"`.

- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass (the 193 existing tests plus the new ones).
- [ ] **Step 5: Run** `uv run alembic upgrade head && uv run python -m app.cli reindex` on `data/jobs.db`. Expected: `reindexed 1359 jobs` (or the current count).
- [ ] **Step 6: Commit** `feat: search index, degree flag column and dashboard source origin`.

---

### Task 2: App factory, login and sessions

**Files:**
- Create: `app/core/secrets.py`, `app/api/deps.py`, `app/api/auth.py`, `tests/api/conftest.py`, `tests/api/test_auth.py`
- Modify: `app/api/main.py` (`create_app`), `app/core/settings.py` (`dashboard_password_hash: str | None`, `dashboard_url: str | None`), `app/cli.py` (`set-password`), `.env.example`, `pyproject.toml` (`argon2-cffi`, `itsdangerous`), `tests/worker/test_api.py` (use `create_app`)

**Interfaces:**
- Produces: `create_app(settings: Settings) -> FastAPI`, with `app.state.session_factory` and `app.state.client: PoliteClient` (opened and closed in the lifespan). `get_session(request) -> Iterator[Session]`, `require_user(request) -> None` (raises 401), `now() -> datetime` (UTC; every route that needs the time takes it as a dependency, so tests can freeze it with `app.dependency_overrides[now]`), `hash_password(pw: str) -> str`, `verify_password(hash: str, pw: str) -> bool`, `session_secret(session) -> str`. Routes: `POST /api/login {password}` → 204 or 401/429/503; `POST /api/logout` → 204; `GET /api/me` → `{"ok": true}`. All later routers are mounted with `dependencies=[Depends(require_user)]`.
- `LoginThrottle`: 5 failures within 10 minutes means every attempt gets 429 for 60 s. It is in-memory, per process.

- [ ] **Step 1: Write the failing tests** in `tests/api/test_auth.py`:

```python
def test_login_sets_http_only_strict_cookie(anon):
    r = anon.post("/api/login", json={"password": "pw"})
    assert r.status_code == 204
    c = r.headers["set-cookie"].lower()
    assert "httponly" in c and "samesite=strict" in c

def test_wrong_password_401_then_throttled(anon):
    for _ in range(5): assert anon.post("/api/login", json={"password": "no"}).status_code == 401
    assert anon.post("/api/login", json={"password": "pw"}).status_code == 429

def test_no_password_configured_503_names_the_command(tmp_path):
    r = TestClient(create_app(settings(tmp_path, dashboard_password_hash=None))).post(
        "/api/login", json={"password": "x"})
    assert r.status_code == 503 and "set-password" in r.json()["detail"]

def test_every_api_route_requires_login(anon):
    open_routes = {"/api/login", "/healthz"}
    for route in anon.app.routes:
        if getattr(route, "path", "").startswith("/api") and route.path not in open_routes:
            for m in route.methods - {"HEAD", "OPTIONS"}:
                assert anon.request(m, route.path.replace("{job_id}", "1")).status_code == 401

def test_logout_ends_session(client):
    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401

def test_set_password_cli_prints_env_line(monkeypatch, capsys):
    # getpass returns "pw" twice → output starts "DASHBOARD_PASSWORD_HASH=$argon2id$"
```

In the fixtures, `settings(tmp_path, dashboard_password_hash=hash_password("pw"))` builds a `Settings` pointing at `tmp_path/"jobs.db"`.

- [ ] **Step 2: Run** `uv run pytest tests/api -v`. Expected: FAIL (no `create_app`).
- [ ] **Step 3: Implement.**
  - **Sessions:** Starlette `SessionMiddleware(secret_key=session_secret(...), same_site="strict", https_only=dashboard_url.startswith("https://"), max_age=30*24*3600)`.
  - **Signing secret:** `session_secret` reads or creates `settings` row `session_secret` = `secrets.token_urlsafe(48)`.
  - **Login:** a successful login sets `request.session["user"] = "me"`.
  - **`set-password`:** asks twice with `getpass`, and refuses a mismatch or anything shorter than 8 characters.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: dashboard login with argon2 and signed session cookie`.

---

### Task 3: Shared eligibility and the dashboard link in alerts

**Files:**
- Create: `app/core/eligibility.py`, `tests/core/test_eligibility.py`
- Modify: `app/notify/alerts.py` (use it; `dashboard_url` kwarg), `app/worker/scheduler.py` (pass `settings.dashboard_url`), `tests/notify/test_alerts.py`

**Interfaces:**
- Produces:

```python
class Eligibility(NamedTuple):
    status: Literal["ok", "warn", "pending"]   # D10: pending = Not checked
    degree: str | None          # "PhD", "Master's", … from the title
    quote: str | None           # Gemini's verbatim line, when status came from a warn
    checking: bool              # analysis_state == "pending" (Gemini will still run)
    unclear: bool               # Gemini answered "unknown"

def eligibility(job: Job, analysis: JobAnalysis | None) -> Eligibility
```

Rules: a degree flag or a `warn` with a quote → `"warn"`; `ok` and no degree → `"ok"`; anything else → `"pending"`.
- `format_alert(job, company, analysis, dashboard_url: str | None = None)`. `process_new(...)` and `refresh_after_analysis(...)` take `dashboard_url: str | None = None` and pass it on. The link line becomes `<a href="{apply}">Apply</a> · <a href="{dashboard_url}/jobs/{id}">Dashboard</a>`.

- [ ] **Step 1: Write the failing tests.** Table tests for `eligibility()` covering each D10 case (6 cases: ok, warn+quote, warn without quote, unknown, no analysis + pending, PhD title + ok). In `test_alerts.py`:

```python
def test_dashboard_link_when_configured(session):
    text = format_alert(j, c, None, dashboard_url="http://pi:8000")
    assert f'<a href="http://pi:8000/jobs/{j.id}">Dashboard</a>' in text
    assert "Dashboard" not in format_alert(j, c, None)
```

- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** `_eligibility_lines` builds its lines from `eligibility()`. Every existing alert text stays exactly as it is (the existing alert tests guard this).
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `refactor: shared eligibility rule; dashboard link in alerts`.

---

### Task 4: Job list and filter options

**Files:**
- Create: `app/api/schemas.py`, `app/api/jobs.py`, `tests/api/test_jobs.py`
- Modify: `app/api/main.py` (include the router)

**Interfaces:**
- Produces, in `schemas.py`:

```python
class JobCard(BaseModel):
    id: int; company: str; company_slug: str; title: str
    location: str                       # first 2 locations joined by " · ", then " +N"; "" if none
    posted_at: datetime | None; first_seen_at: datetime
    is_new: bool                        # no JobUserState row, or seen_at is None
    eligibility: Literal["ok", "warn", "pending"]
    tag: Literal["liked", "applied", "dismissed"] | None
    closed: bool

class JobPage(BaseModel):
    total: int; items: list[JobCard]; loaded_at: datetime   # loaded_at: server now, used by D7

class Option(BaseModel): value: str; label: str; count: int
class FilterOptions(BaseModel): companies: list[Option]; countries: list[Option]
```

- `GET /api/jobs` query parameters:
  - `view`: `tech|all` (default `tech`).
  - `company`: list of slugs.
  - `loc`: `anywhere|india|<ISO-2>` (default `anywhere`). `india` means `IN` in `country_codes` or `remote_type == "remote"`.
  - `elig`: list of `ok|warn|pending`.
  - `posted`: `1d|7d|30d|any` (default `any`). Compares against `coalesce(posted_at, first_seen_at)`.
  - `tag`: list of `liked|applied|untagged`.
  - `dismissed`: bool (default false).
  - `q`: search text.
  - `offset`: default 0. `limit`: 1–100, default 50.
  - Sorted by `coalesce(posted_at, first_seen_at) DESC, id DESC`.
- `GET /api/filters?view=` returns companies (by name) and countries (`pycountry` name), each with its count of jobs in that view, highest count first.
- Eligibility in SQL, matching D10:
  - `warn`: `degree_only IS NOT NULL OR (analysis.eligibility = 'warn' AND quote IS NOT NULL)`.
  - `ok`: `analysis.eligibility = 'ok' AND degree_only IS NULL`.
  - `pending`: everything else.

- [ ] **Step 1: Write the failing tests** (in `tests/api/test_jobs.py`, all using `seed_job`):

```python
def test_default_view_is_open_tech_internships_newest_first(client, db):
    a = seed_job(db, title="Software Intern", posted=T0)
    b = seed_job(db, title="Data Intern", posted=T0 + DAY)
    seed_job(db, title="HR Intern", tech=False)
    seed_job(db, title="Senior Engineer", intern=False)
    seed_job(db, title="Closed Intern", state="closed")
    assert [j["id"] for j in client.get("/api/jobs").json()["items"]] == [b.id, a.id]

def test_closed_but_applied_stays_visible(client, db):           # D6
    j = seed_job(db, state="closed", tag="applied")
    item = client.get("/api/jobs").json()["items"][0]
    assert item["id"] == j.id and item["closed"] is True

def test_dismissed_hidden_unless_asked(client, db):
    j = seed_job(db, tag="dismissed")
    assert client.get("/api/jobs").json()["total"] == 0
    assert client.get("/api/jobs?dismissed=true").json()["items"][0]["id"] == j.id

def test_eligibility_filter_matches_badge(client, db):           # D10
    ok = seed_job(db, analysis="ok")
    phd = seed_job(db, title="Software PhD Intern", analysis="ok")
    warn = seed_job(db, analysis="warn", quote="US students only")
    pend = seed_job(db)
    ids = lambda e: {j["id"] for j in client.get(f"/api/jobs?elig={e}").json()["items"]}
    assert ids("ok") == {ok.id} and ids("warn") == {phd.id, warn.id} and ids("pending") == {pend.id}

def test_india_includes_remote(client, db): ...      # IN job + remote US job in; plain US job out
def test_posted_falls_back_to_first_seen(client, db): ...  # posted=None, first_seen 2 days ago: in 7d, out of 1d
def test_tag_untagged_and_company_filters_combine(client, db): ...  # tag=untagged&company=google → only untagged Google jobs
def test_search_finds_description_words(client, db):
    j = seed_job(db, description="<p>Kubernetes operators</p>")
    assert client.get("/api/jobs?q=kubern").json()["items"][0]["id"] == j.id
def test_search_with_fts_syntax_is_200(client, db):
    assert client.get('/api/jobs?q=%22NEAR(').status_code == 200
def test_paging_total_and_limit_cap(client, db):                 # 3 jobs, limit=2 → total 3, 2 items; limit=500 → 422
def test_filter_options_count_within_view(client, db): ...       # a non-tech Google job counts under view=all only
```

- [ ] **Step 2: Run** `uv run pytest tests/api/test_jobs.py -v`. Expected: FAIL (404).
- [ ] **Step 3: Implement** with one SQLAlchemy `select` built from the filters: outer joins to `JobAnalysis` and `JobUserState`, a join to `Company`, and the FTS filter as `Job.id.in_(text("SELECT rowid FROM jobs_fts WHERE jobs_fts MATCH :q"))`. `total` comes from the same query wrapped in `count()`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: job list API with filters, search and paging`.

---

### Task 5: Job detail, tags, notes and "seen"

**Files:**
- Modify: `app/api/schemas.py`, `app/api/jobs.py`, `pyproject.toml` (`nh3`)
- Create: `tests/api/test_detail.py`

**Interfaces:**
- Produces:

```python
class Change(BaseModel): at: datetime; fields: list[str]
class TagEvent(BaseModel): at: datetime; from_tag: str | None; to_tag: str | None
                           event_date: date | None; note: str | None
class JobDetail(JobCard):
    external_id: str; locations: list[str]; employment_type: str | None
    remote_type: str | None; url: str; apply_url: str | None
    degree: str | None; quote: str | None; checking: bool; unclear: bool
    sections: dict | None               # JobAnalysis.sections when analysed
    description_html: str | None        # nh3-sanitised; only when sections is None
    has_description: bool
    note: str | None; changes: list[Change]; tag_history: list[TagEvent]
```

- Routes:
  - `GET /api/jobs/{job_id}` → `JobDetail`, or 404.
  - `POST /api/jobs/{job_id}/seen` → 204.
  - `PUT /api/jobs/{job_id}/tag {tag: liked|applied|dismissed|null, event_date?: date, note?: str}` → `JobDetail`.
  - `PUT /api/jobs/{job_id}/note {note: str ≤ 5000}` → 204.
  - `POST /api/jobs/mark-seen {up_to: datetime}` → `{"marked": int}`.
- Tag changes add a `TagHistory` row. Setting the tag it already has is a no-op with no history row.
- `mark-seen` is a single statement: `INSERT INTO job_user_state(job_id, seen_at) SELECT id, :now FROM jobs WHERE first_seen_at <= :up_to ON CONFLICT(job_id) DO UPDATE SET seen_at = excluded.seen_at WHERE job_user_state.seen_at IS NULL`.
- Sanitising: `nh3.clean(html, tags={"p","br","ul","ol","li","b","strong","i","em","h2","h3","h4","a","table","tr","td","th","thead","tbody"}, link_rel="noopener noreferrer nofollow")`. Only `http`/`https`/`mailto` links survive.

- [ ] **Step 1: Write the failing tests:**

```python
def test_description_html_is_sanitised(client, db):
    j = seed_job(db, description='<p onclick="x()">Hi<script>alert(1)</script>'
                                 '<img src=x onerror=alert(1)><a href="javascript:x">l</a></p>')
    html = client.get(f"/api/jobs/{j.id}").json()["description_html"]
    assert "script" not in html and "onerror" not in html and "onclick" not in html
    assert "javascript:" not in html and "Hi" in html

def test_sections_replace_description_when_analysed(client, db): ...
def test_detail_lists_changes_and_tag_history(client, db): ...
def test_tag_toggle_records_history_once(client, db):
    client.put(f"/api/jobs/{j.id}/tag", json={"tag": "liked"})
    client.put(f"/api/jobs/{j.id}/tag", json={"tag": "liked"})
    client.put(f"/api/jobs/{j.id}/tag", json={"tag": None})
    assert [(e["from_tag"], e["to_tag"]) for e in detail["tag_history"]] == [(None, "liked"), ("liked", None)]
def test_applied_with_date_and_note(client, db): ...
def test_note_saved_and_capped(client, db):                     # 5001 chars → 422
def test_open_marks_seen(client, db): ...                       # POST seen → list item is_new False
def test_mark_all_seen_spares_jobs_after_up_to(client, db):     # Review Focus 4
    old = seed_job(db, first_seen=T0)
    page = client.get("/api/jobs").json()
    late = seed_job(db, first_seen=T0 + HOUR)                    # arrives while reading
    r = client.post("/api/jobs/mark-seen", json={"up_to": page["loaded_at"]})
    assert r.json()["marked"] == 1
    new = {j["id"]: j["is_new"] for j in client.get("/api/jobs").json()["items"]}
    assert new == {old.id: False, late.id: True}
def test_unknown_job_404(client): ...
def test_tag_body_must_be_json(client, db):                     # form-encoded → 422
```

(The test freezes the server clock: `client.app.dependency_overrides[now] = lambda: T0 + 30*MIN`. `loaded_at` then equals that time, and `late` arrives after it.)
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: job detail, tags, notes and mark-as-seen`.

---

### Task 6: Description on demand

**Files:**
- Modify: `app/pipeline/ingest.py` (add `raw_from_job`, `apply_detail`; the runner uses `raw_from_job` in place of `_raw_from_job`), `app/api/jobs.py`
- Test: `tests/api/test_detail.py`, `tests/pipeline/test_ingest.py`

**Interfaces:**
- Produces: `raw_from_job(job: Job) -> RawJob`. `apply_detail(session, job, raw: RawJob, now) -> list[str]` merges non-empty fields the same way `ingest` does: it logs a `JobChange`, re-queues a skipped Gemini analysis (R1 rule), calls `refresh_derived`, and returns the changed field names. `POST /api/jobs/{job_id}/description` → `JobDetail`.
- Errors:
  - `RobotsDisallowed` → 409 `"This site's robots.txt doesn't allow fetching the page."`
  - `httpx.HTTPError` or `ParseError` → 502 `"Couldn't reach {host}. Try again later."`
  - `GONE` → `mark_gone`, then `JobDetail` with `closed: true`.
  - A job that already has a description → `JobDetail` without any fetch.
- The adapter is chosen from the job's first enabled source. The request goes through `app.state.client`. Session pattern: read, close, fetch, then a new session to write (Global Constraints).

- [ ] **Step 1: Write the failing tests.** Add a `fake_adapter` fixture to `tests/api/conftest.py`. It registers an adapter named `fake-api` (pattern from `tests/worker/test_runner.py`). Its behaviour is set per test through `fake_adapter.detail` (a `RawJob`, `GONE`, or an exception to raise) and `fake_adapter.listing` (a `ListingResult`). It counts calls in `fake_adapter.calls`. `seed_job` gets `adapter="fake-api"` so the job's source uses it. Task 7 reuses this fixture.

```python
def test_fetch_description_stores_and_returns(client, db): ...      # description_html now set; JobChange logged
def test_fetch_description_robots_409(client, db): ...
def test_fetch_description_site_down_502_mentions_host(client, db): ...
def test_fetch_description_gone_closes_job(client, db): ...
def test_fetch_description_skips_when_present(client, db): ...      # fake adapter call count stays 0
def test_apply_detail_requeues_skipped_analysis(session, setup): ... # in test_ingest.py
```

- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: fetch a missing job description on demand`.

---

### Task 7: Stats, source health and "Add company"

**Files:**
- Create: `app/sources/detect.py`, `app/sources/checks.py` (move `evaluate` here from `cli.py`), `app/api/sources.py`, `tests/sources/test_detect.py`, `tests/api/test_sources.py`
- Modify: `app/cli.py` (import `evaluate`), `app/api/main.py`, `app/api/schemas.py`

**Interfaces:**
- Produces:

```python
class Detected(NamedTuple): adapter: str; config: dict; key_hint: str
def detect(url: str) -> Detected | None

class Stats(BaseModel):
    new_today: int          # tech internships first seen since 00:00 IST today
    open_tech: int; companies: int      # companies with an enabled source
    liked: int; applied: int; last_applied_at: datetime | None
class SourceHealth(BaseModel):
    key: str; company: str; adapter: str; origin: str; enabled: bool
    status: Literal["ok", "failing", "never_run"]
    last_success_at: datetime | None; last_job_count: int | None
    last_error: str | None; consecutive_failures: int
class AddCompany(BaseModel): company_name: str; url: str
class AddResult(BaseModel): key: str; jobs_found: int; sample_titles: list[str]
```

- Routes:
  - `GET /api/stats` → `Stats`.
  - `GET /api/sources` → `list[SourceHealth]`, failing first, then by company.
  - `POST /api/sources/detect {url}` → `Detected` as JSON, or 422 `"Not a Workday, Eightfold or Oracle HCM careers URL."`
  - `POST /api/sources AddCompany` → 201 `AddResult`. It runs one incremental `list_jobs` test fetch, and saves the `Company` and `Source(origin="dashboard")` **only** if `evaluate()` returns no problems. Otherwise 422 with the problems joined by `; `. A key that already exists → 409.
- Detection rules (D2):
  - **Workday:** `https://{tenant}.wd{N}.myworkdayjobs.com/[{lang}/]{site}[/…]` → `{host, tenant, site}`.
  - **Oracle HCM:** `https://{host}/hcmUI/CandidateExperience/{lang}/sites/{site}[/…]` → `{host, site}`.
  - **Eightfold:** host `*.eightfold.ai`, or a path starting `/careers` with a `pid=` or `/job/` part → `{host, domain}`, where `domain` is `{sub}.com` for `*.eightfold.ai` and otherwise the host minus its first label.
  - `key_hint` is the slug of the tenant, site or subdomain.

- [ ] **Step 1: Write the failing tests.** In `test_detect.py`, a table built from **real URLs** taken from `config/sources.yaml` (one Workday, one Oracle, two Eightfold), plus `https://example.com/jobs` → `None` and a Workday URL with a `/en-US/` language segment. In `test_sources.py`:

```python
def test_stats_counts(client, db): ...      # frozen now = 10:00 IST; tech intern seen 09:00 IST counts, one seen yesterday doesn't
def test_sources_failing_first(client, db): ...   # consecutive_failures=2 → "failing", listed before "ok"; never succeeded → "never_run"
def test_add_company_saves_only_after_good_test_fetch(client, db, fake_adapter): ...
def test_add_company_bad_fetch_saves_nothing(client, db, fake_adapter): ...   # 0 jobs → 422, no Source row
def test_add_company_unknown_url_422(client): ...
def test_added_source_survives_registry_sync(client, db): ...
```

(The test points `detect` at a fake adapter through `monkeypatch`, so no live site is called.)
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Follow the session pattern from Task 6 for the test fetch.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Live check:** with the API running, use `curl` to `POST /api/sources/detect` with one real careers URL per platform. Each should return the same config as the matching entry in `sources.yaml`.
- [ ] **Step 6: Commit** `feat: stats, source health and add-company API`.

---

### Task 8: Frontend scaffold, login page and static serving

**Files:**
- Create:
  - `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/index.html`
  - `web/src/main.tsx`, `web/src/index.css` (tokens from Global Constraints, a `.dark` class plus `prefers-color-scheme`)
  - `web/src/api.ts`, `web/src/types.ts`, `web/src/theme.ts`, `web/src/pages/Login.tsx`
  - `web/src/api.test.ts`, `tests/api/test_static.py`
- Modify: `app/api/main.py` (serve `web/dist`), `Dockerfile` (Node build stage), `.gitignore` (`web/node_modules`, `web/dist`), `.dockerignore`

**Interfaces:**
- Produces:
  - `api.ts`: `api<T>(path: string, init?: RequestInit): Promise<T>`. It sends JSON, and on 401 navigates to `/login?next=<current path>`. It throws `ApiError {status, detail}` otherwise.
  - `types.ts` mirrors `JobCard`, `JobPage`, `JobDetail`, `FilterOptions`, `Stats`, `SourceHealth`, `AddResult`.
  - `theme.ts`: `useTheme(): [mode, setMode]` with `"system" | "light" | "dark"`, kept in `localStorage["theme"]`.
  - Routes: `/login`, `/` (dashboard), `/jobs/:id`, `/sources`.
  - npm scripts: `dev` (Vite on 5173, proxying `/api` to `:8000`), `build`, `check` = `tsc --noEmit && vitest run`.
- Server: when `web/dist/index.html` exists, `/assets/*` is served as static files, and any other non-`/api` GET returns `index.html`. An unknown `/api/*` path stays a JSON 404.

- [ ] **Step 1: Write the failing tests.** `tests/api/test_static.py`: with a temporary dist folder holding `index.html`, `GET /jobs/12` returns that HTML, and `GET /api/nope` returns 404 JSON. `web/src/api.test.ts`: a 401 response calls the navigate hook with `/login?next=%2Fjobs%2F3`, and a 422 response throws `ApiError` carrying the server's `detail`.
- [ ] **Step 2: Run** `uv run pytest tests/api/test_static.py` and `cd web && npm run check`. Expected: FAIL.
- [ ] **Step 3: Implement.** Login page: a centred card with a "Job Scraper" mark, a password field (`<label>` + `<input type="password" autocomplete="current-password">`) and a button. Errors appear inline: wrong password, the 429 message, and the 503 message showing the `set-password` command. Dockerfile: `FROM node:22-slim AS web` → `npm ci && npm run build`, then `COPY --from=web /web/dist ./web/dist`.
- [ ] **Step 4: Run** both checks, then `docker build .`. Expected: pass, and the image builds.
- [ ] **Step 5: Commit** `feat: React app scaffold, login page and SPA serving`.

---

### Task 9: Dashboard list view

**Files:**
- Create:
  - `web/src/filters.ts`, `web/src/filters.test.ts`, `web/src/pages/Dashboard.tsx`
  - `web/src/components/Header.tsx`, `StatsStrip.tsx`, `FilterPanel.tsx`, `JobList.tsx`, `JobCard.tsx`
  - `web/src/components/JobCard.test.tsx`

**Interfaces:**
- Produces, in `filters.ts`:

```ts
type Filters = { view: "tech" | "all"; company: string[]; loc: string; elig: Elig[];
                 posted: "1d" | "7d" | "30d" | "any"; tag: ("liked"|"applied"|"untagged")[];
                 dismissed: boolean; q: string }
const DEFAULTS: Filters      // D5
function toParams(f: Filters): URLSearchParams      // omits values equal to DEFAULTS
function fromParams(p: URLSearchParams): Filters    // ignores unknown or invalid values
function useFilters(): [Filters, (patch: Partial<Filters>) => void]  // URL + localStorage["filters"]
```

- Consumes: `GET /api/jobs`, `/api/filters`, `/api/stats`, `POST /api/jobs/mark-seen`.

- [ ] **Step 1: Write the failing tests.** `filters.test.ts`: round trip `fromParams(toParams(f))` deep-equals `f` for 3 filter sets; defaults produce an empty query string; `?elig=bogus&posted=9y` falls back to defaults. `JobCard.test.tsx`: renders the NEW badge only when `is_new`; maps `ok`/`warn`/`pending` to the labels "Eligible", "Check needed", "Not checked"; shows "Closed" when `closed`; is a real `<button>` (or `<a>` on phone).
- [ ] **Step 2: Run** `npm run check`. Expected: FAIL.
- [ ] **Step 3: Implement**, matching mockup A:
  - **Header:** logo mark, search box (debounced 300 ms into `q`), "Mark all as seen" (sends `loaded_at` from the current page, then refetches), "Add company" (opens the Task 11 dialog), theme toggle.
  - **Stats strip:** four tiles (New today · Open tech internships · Liked · Applied).
  - **Filter panel:**
    - Tech internships / All jobs tabs.
    - Company checklist: top 8 by count, with "+ N more" to expand.
    - Location select: Anywhere, India + Remote, then countries by count.
    - Eligibility chips (Eligible, Check needed, Not checked), posted select and tag chips (Liked, Applied, Untagged), as in the mockup.
    - Show dismissed checkbox.
    - Below 1024 px, the panel becomes a "Filters (n)" button that opens a sheet.
  - **List:** cards as in the mockup, with initials from the company name, plus "Showing X of Y · Load more" (50 at a time, `useInfiniteQuery`). Empty state: "No jobs match these filters" with a "Clear filters" button.
- [ ] **Step 4: Run** `npm run check` and `npm run build`. Expected: pass.
- [ ] **Step 5: Look at it:** run `uv run uvicorn app.api.main:app` against `data/jobs.db` plus `npm run dev`. Check at 1440 px and 390 px wide, in both themes: filters change the list, and the URL updates and survives a reload.
- [ ] **Step 6: Commit** `feat: dashboard list view with filters, stats and search`.

---

### Task 10: Job detail panel and page

**Files:**
- Create: `web/src/components/JobDetail.tsx`, `web/src/components/JobDetail.test.tsx`, `web/src/pages/JobPage.tsx`
- Modify: `web/src/pages/Dashboard.tsx` (third column, `?job=` selection)

**Interfaces:**
- Consumes: `GET /api/jobs/{id}`, `POST …/seen`, `PUT …/tag`, `PUT …/note`, `POST …/description`.
- `JobDetail` props: `{ id: number; onClose?: () => void }`. It is used in the dashboard's third column (laptop) and on `/jobs/:id` (phone or a direct link).

- [ ] **Step 1: Write the failing tests** (`JobDetail.test.tsx`, with a mocked `api`):
  - Clicking "Like" on an untagged job sends `{tag: "liked"}`; clicking it again sends `{tag: null}`.
  - "Applied" opens a small form (date defaulting to today in IST, optional note) before sending.
  - The note is saved 800 ms after typing stops, and shows "Saved".
  - When `has_description` is false, `POST …/description` is called once, and a 409 or 502 `detail` message is shown in place of the sections.
  - The eligibility box shows the degree line and the quote when both exist.
- [ ] **Step 2: Run** `npm run check`. Expected: FAIL.
- [ ] **Step 3: Implement**, following mockup A's detail column:
  - **Top:** company · external ID; title; locations · employment type · posted · first seen.
  - **Eligibility box:** coloured by status. The head comes from D10. Then "⚠ For PhD students only (from the title)" when there is a degree flag, the quote in italics, and a note: "Checked by Gemini…", or "Not checked yet — updates automatically", or "Gemini couldn't tell — read the posting".
  - **Buttons:** "Apply on {company}" (`apply_url` or `url`, `target="_blank" rel="noopener"`), "Original posting", Like, Applied, Dismiss. Active ones are highlighted, and clicking an active one removes the tag.
  - **Body:** the sections (About, Responsibilities, Requirements, Preferred, Eligibility), or the sanitised description HTML (rendered with `dangerouslySetInnerHTML`, since it is server-sanitised per D9, and styled with prose classes), or a loading state.
  - **Note** box.
  - **History footer:** tag history and changes, newest first.
  - **Seen:** opening the panel calls `POST …/seen` and clears the NEW badge in the list cache.
- [ ] **Step 4: Run** `npm run check` and `npm run build`. Expected: pass.
- [ ] **Step 5: Look at it** with real data: open a Google job (has sections), an Accenture non-internship (no description, so it fetches on demand), and a PhD job (shows the degree line). Check at 390 px wide too.
- [ ] **Step 6: Commit** `feat: job detail with tags, notes, sections and on-demand description`.

---

### Task 11: Health panel, sources page and "Add company" dialog

**Files:**
- Create: `web/src/components/HealthPanel.tsx`, `web/src/pages/Sources.tsx`, `web/src/components/AddCompanyDialog.tsx`, `web/src/components/AddCompanyDialog.test.tsx`
- Modify: `web/src/components/FilterPanel.tsx` (health card under the filters, as in the mockup)

**Interfaces:**
- Consumes: `GET /api/sources`, `POST /api/sources/detect`, `POST /api/sources`.

- [ ] **Step 1: Write the failing tests** (`AddCompanyDialog.test.tsx`):
  - Pasting a URL calls detect and shows "Workday · tenant broadcom · site External_Career".
  - An unknown URL shows the 422 message, and the Save button stays disabled.
  - Save shows "Testing…", then "Added — 60 jobs found" with up to 5 sample titles.
  - A failed test fetch shows the problems, and nothing is added.
- [ ] **Step 2: Run** `npm run check`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - **Health card:** "N healthy · M failing", then each failing source with its company, error and failure streak. "All sources" links to `/sources`.
  - **Sources page:** a table (company, source key, platform, origin, last success as relative time, jobs, failures, last error), failing first. It scrolls horizontally inside its box on phone.
  - **Dialog:** a native `<dialog>` with a company name field, careers URL field, detected-platform line, Cancel and Save, and focus trapped inside.
- [ ] **Step 4: Run** `npm run check` and `npm run build`. Expected: pass.
- [ ] **Step 5: Commit** `feat: scraper health, sources page and add-company dialog`.

---

### Task 12: Deployment, docs and end-to-end check

**Files:**
- Modify: `docker-compose.yml` (no new service; the `api` already serves the dashboard), `docs/RUNBOOK.md` (a "Dashboard" section: `set-password`, `DASHBOARD_URL`, `http://<pi-tailscale-name>:8000`, `npm run dev` for development), `.env.example` (`DASHBOARD_PASSWORD_HASH=`, `DASHBOARD_URL=`), `docs/DESIGN.md` §7 (link to this plan's decisions D1–D14), create `docs/R2-notes.md` (same format as R1-notes)

- [ ] **Step 1: Full checks:** run `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` and `cd web && npm run check && npm run build`. Expected: all clean.
- [ ] **Step 2: Real data, laptop and phone:**
  - Run `uv run uvicorn app.api.main:app --port 8000` against `data/jobs.db`, with a password set.
  - Check the following:
    1. Wrong password → error. Right password → dashboard.
    2. Stats are non-zero, and the default list shows open tech internships, newest first.
    3. Each filter changes the list: company, India + Remote, Check needed (should include the PhD jobs), posted 7 days, search "kubernetes".
    4. Opening a job clears NEW. Like, then unlike, writes two history rows.
    5. An Accenture non-internship fetches its description on demand.
    6. "Mark all as seen" clears every NEW badge.
    7. The health card shows 32 healthy.
    8. "Add company", tried with one real URL per platform, detects correctly. Cancel without saving.
    9. Both themes, at 390 px and 1440 px.
- [ ] **Step 3: Docker:** `docker build .` succeeds, and the image contains `web/dist/index.html`.
- [ ] **Step 4: Commit** `docs: dashboard runbook and R2 notes`.
