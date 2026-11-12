# Job Scraper

A self-hosted tracker for **tech internships**. It reads the official careers sites of 61 companies, stores every job it finds, and sends a Telegram alert for each new tech internship, with an eligibility check for a student based in India. A dashboard, reachable over Tailscale, is for browsing, tagging and tracking applications.

It is built to run 24/7 on a Raspberry Pi 5 with Docker Compose. [docs/DESIGN.md](docs/DESIGN.md) is the source of truth for what it does and why.

## What it does

- **Scraping.**
  - Platform adapters (Workday, Eightfold, Oracle HCM, Lever, Greenhouse, SuccessFactors, RSS, government notice pages and more) plus company-specific ones.
  - An incremental check every 30 minutes, a full sweep every night, and a daily re-check of the jobs you track.
  - robots.txt is checked before every request, each host is rate-limited, and nothing gets around bot protection.
- **Classification.** Keyword rules decide what is an internship and what is tech. Gemini (free tier, paced well under its limits) splits each posting into sections and quotes any line that could rule out a student in India. A quote that isn't in the posting is rejected.
- **Telegram alerts.**
  - One message per new tech internship, edited in place once the eligibility check finishes.
  - ❤️ Like · ✅ Applied · 🗑 Dismiss buttons under each alert.
  - A "🔒 Closed" message when a job you liked or applied to closes.
  - A warning when a scraper keeps failing.
- **Dashboard** (React).
  - Filters and full-text search.
  - Keyboard and swipe triage.
  - Application stages after Applied (OA → Interview → Offer / Rejected) and a "Your applications" view.
  - A Sources health page, CSV export, and an install as a home-screen app.

## Stack

Python 3.13 · FastAPI · SQLAlchemy 2 + Alembic · SQLite (WAL) · APScheduler · httpx · Gemini (`google-genai`) · React + Vite + TypeScript + Tailwind · Docker Compose (arm64 and amd64).

## Quick start (Mac or Linux)

You need [uv](https://docs.astral.sh/uv/) and Node 22.

```bash
uv sync
cd web && npm install && cd ..
cp .env.example .env            # add your Telegram and Gemini keys (both optional)
uv run python -m app.cli set-password   # paste the line it prints into .env
uv run alembic upgrade head
```

Run one scrape, then the dashboard at http://localhost:8000:

```bash
uv run python -m app.cli run-once --mode incremental
cd web && npm run build && cd ..
uv run uvicorn app.api.main:create_app --factory --port 8000
```

Start the scheduler (scrapes, alerts, Telegram buttons) in another terminal:

```bash
uv run python -m app.worker.scheduler
```

## Run it with Docker (Raspberry Pi)

```bash
docker compose up -d --build
docker compose logs -f worker
```

This starts four services:

| Service | What it does |
|---|---|
| `migrate` | Prepares the database, then exits |
| `worker` | Scrapes, classifies, sends alerts and reads the Telegram buttons |
| `api` | The dashboard on port 8000 |
| `backup` | A nightly SQLite backup |

[docs/RUNBOOK.md](docs/RUNBOOK.md) covers the Telegram bot, Gemini key, Pi setup with Tailscale, backups and restoring.

## Tests

```bash
uv run pytest                    # backend
cd web && npm run check          # dashboard: type-check and tests
uv run python -m app.cli live-check   # every source against the live sites
```

Adapter tests run against recorded real responses in `tests/fixtures/` (`scripts/record_fixture.py`), not invented sample jobs.

## Layout

```
app/
  adapters/   one module per careers platform or company
  pipeline/   storing, dedupe, change and close detection, rules
  llm/        Gemini provider, pacing, queue
  notify/     Telegram alerts, buttons, closed-job and health messages
  worker/     scheduler, runner, Telegram long-polling
  api/        FastAPI routes, login, CSV export
  core/       settings, database models, tags and stages
config/       sources.yaml (company registry), keywords.yaml
migrations/   Alembic
web/          React dashboard
docs/         design, runbook, per-company findings, build notes
```

## Docs

- [DESIGN.md](docs/DESIGN.md): scope, data model, alerts, dashboard.
- [RUNBOOK.md](docs/RUNBOOK.md): set up, run, back up, restore.
- [companies.md](docs/companies.md): each company's careers site, and the ones that can't be supported.
- The `*-notes.md` files: what each piece of work changed, what was checked and what wasn't.

## Notes

- **Single user.** A password login; the dashboard is meant to be reached only over Tailscale, never the public internet.
- **No secrets in the repo:** keys and the password hash live in `.env`, which is git-ignored.
- **Out of scope** (see DESIGN §2): applying automatically, logging in to company sites, getting around bot protection, ranking jobs against a resume.
