# Next work: prompts

Written 2026-11-12 after looking at the dashboard on a copy of the real data (laptop and phone widths). Each prompt below is meant to start a fresh Claude session. Paste one prompt at a time. They all point back to the ground rules here, so these don't need repeating.

Suggested order: 1 → 2 → 4 → 5, then whatever you want next.

| # | Prompt | Size |
|---|---|---|
| 1 | [Phone layout, header and stats](#1-phone-layout-header-and-stats) | M |
| 2 | [Job list clean-up](#2-job-list-clean-up) | M |
| 3 | [Sources page](#3-sources-page) | M |
| 4 | [Keyboard and swipe triage](#4-keyboard-and-swipe-triage) | S–M |
| 5 | [Telegram: tag buttons and "closed" messages](#5-telegram-tag-buttons-and-closed-messages) | L |
| 6 | [Stages after Applied](#6-stages-after-applied) | M |
| 7 | [Same job posted in many places](#7-same-job-posted-in-many-places) | M |
| 8 | ["Eligible for me" view](#8-eligible-for-me-view) | S–M |
| 9 | [Saved searches, alert rules and a daily digest](#9-saved-searches-alert-rules-and-a-daily-digest) | L |
| 10 | [Home-screen app and CSV export](#10-home-screen-app-and-csv-export) | S |
| 11 | [When each company posts internships](#11-when-each-company-posts-internships) | S, but only once there's history |

---

## Ground rules (every prompt)

- Read [DESIGN.md](DESIGN.md) first; it's the source of truth. §2 lists what is out of scope. Then read the latest notes ([deferred-fixes-notes.md](deferred-fixes-notes.md)) so you know what was decided recently.
- Work on a new branch off `main`. Don't commit or merge until I say so.
- Write the failing test first. Backend: `uv run pytest`. Dashboard: `cd web && npm run check`. Both must pass at the end.
- Database changes go in a new Alembic migration in `migrations/versions/`. Never edit an old one.
- Dashboard changes: check the light and dark themes, and both phone (375 px) and laptop (1440 px) widths. DESIGN §7 says the look comes from mockups, so for any layout change show me a quick mockup and wait for my OK before writing UI code.
- To see the real UI, don't touch `data/jobs.db` or `.env`. Copy the database with `sqlite3 data/jobs.db ".backup <scratch>/jobs.db"`, make a throwaway password hash with `app.core.secrets.hash_password`, and run `DATABASE_URL=sqlite:///<scratch>/jobs.db DASHBOARD_PASSWORD_HASH=<hash> uv run uvicorn app.api.main:create_app --factory --port 8001` after `cd web && npm run build`.
- The dashboard is only reachable over Tailscale. Add no public endpoints, no new external services, and no browser requests to third-party sites (no hotlinked logos or fonts) without asking me.
- When done, write a short notes file in `docs/` in the style of `R4-notes.md`: a Status table (tests, what was checked live, **what wasn't checked**), decisions with their cost if wrong, and "Left for later". Update DESIGN.md if behaviour changed.

---

## 1. Phone layout, header and stats

```
Follow the ground rules at the top of docs/next-prompts.md.

Fix the dashboard's phone layout and tidy the header and stats strip (web/src/components/Header.tsx, StatsStrip.tsx, pages/Dashboard.tsx).

The problems, seen at 375×812:
- The header wraps to three rows (search; Mark all as seen / Add company / theme; Log out / Everywhere), then the four stat tiles take two more rows. The first job starts about 80% of the way down the screen. Most visits come from a Telegram link on a phone, so this matters most.
- "Everywhere" is a button on its own and doesn't say what it does. It means "log out on every device".
- "Mark all as seen" acts on the list but sits in the header.
- The stat tiles (New today, Open tech internships, Liked, Applied) can't be clicked.

What I want:
- Phone header: logo and search only. Every other action goes in one ⋯ menu.
- Laptop header: search, Add company, theme, and an account menu holding "Log out" and "Log out everywhere" (keep the existing confirm).
- "Mark all as seen" moves to the list's own header row, next to the count.
- On a phone, the stats become one row of small chips that scrolls sideways. On a laptop, keep the tiles.
- Each stat sets the matching filter in the URL: New today → new only, Liked → tag liked, Applied → tag applied, Open tech internships → clears filters. Use the existing filter params in web/src/filters.ts. Show which one is active.
- Goal: on a 375×812 phone, at least two job cards are visible without scrolling.

Show me a mockup of the phone and laptop header first. Keep the existing tests passing and add tests for the menu and for the stat → filter links.
```

## 2. Job list clean-up

```
Follow the ground rules at the top of docs/next-prompts.md.

Make the job list (web/src/components/JobCard.tsx, JobList.tsx, JobDetail.tsx, pages/Dashboard.tsx) quicker to scan. Four changes:

1. Eligibility badges: today almost every card says "Not checked", which tells me nothing. Show a badge only for "Check needed" (amber) and "Eligible" (green); show nothing while a job is unchecked or being checked. The detail panel keeps its full explanation.
2. Laptop layout: the list column is about 290 px, so titles wrap to 4 lines, while the detail panel shows "Pick a job to see its details here." until something is clicked. Make the list wider (roughly 40/60 with the detail panel; the filters keep 240 px), clamp titles to 2 lines, and open the first job when nothing is selected. Opening it automatically must not mark it seen; check how "seen" works now and keep that behaviour.
3. Company icons are just the first letter (G, H, Q). Give each company a stable color from its slug, and allow an optional local logo: an SVG/PNG file in web/public/logos/<slug>.svg, used when it exists. Don't fetch logos from other sites at runtime. Add logos for the 10 companies with the most jobs, if you can get them from each company's own press/brand page; otherwise list which ones are missing.
4. Locations get cut off ("Ratingen, Nordrhein-Westfalen, Germa…"). Show "City, Country" with the country's flag emoji, "+N" for more locations, and mark India and remote jobs (a small "India" / "Remote" chip). The jobs table already has country codes and the remote type.

Show me a mockup of a card and the laptop layout first. Add tests for the badge rules and the location formatting.
```

## 3. Sources page

```
Follow the ground rules at the top of docs/next-prompts.md.

Improve the Sources page (web/src/pages/Sources.tsx, app/api/sources.py). Today it's a plain table of 65 rows, almost all "OK", sorted by company, so a failing source is easy to miss.

- Sort: failing sources first (by failure streak), then partial or warning, then OK by company. Show a one-line summary on top: "63 OK · 1 partial · 1 failing".
- For each source, add a small chart of its job count over the last 14 days, from scrape_runs (incremental and full runs, read count). A drop should be easy to see. Draw it as inline SVG; add no chart library unless you ask me first.
- Add the last run's duration and kind, and when the next full sweep is due.
- Clicking a row opens that source's last 20 runs: kind, start, duration, status, jobs read vs site total, new/updated/closed, and the error.
- The API should send the chart data in one request for all sources. Check the query time on the real database copy and put it in the notes. scrape_runs grows every 30 minutes, so look at its indexes.
- Phone: the table becomes cards.

Show me a mockup first.
```

## 4. Keyboard and swipe triage

```
Follow the ground rules at the top of docs/next-prompts.md.

Add fast triage to the dashboard so I can go through a day's new jobs quickly.

Keyboard (laptop, list view):
- j / k: next / previous job (the detail panel follows and the card scrolls into view)
- l: Like · a: Applied · d: Dismiss · u: remove tag (the same PUT /api/jobs/{id}/tag the buttons use)
- o: open the posting's apply link in a new tab
- /: focus search · Esc: leave search or close the detail panel
- ?: a small overlay listing the shortcuts
Shortcuts are ignored while typing in an input or textarea (the note box, search). After Dismiss, move to the next job automatically.

Phone: swipe a job card right to Like and left to Dismiss, with the color and icon showing during the swipe and an Undo toast for 5 seconds. Vertical scrolling must still work normally. Use pointer events; add no gesture library without asking me.

Tests: each key, the "not while typing" rule, Undo after a swipe.
```

## 5. Telegram: tag buttons and "closed" messages

```
Follow the ground rules at the top of docs/next-prompts.md.

Two Telegram additions (app/notify/telegram.py, alerts.py, app/worker/).

A. Buttons on each job alert: ❤️ Like · ✅ Applied · 🗑 Dismiss (inline keyboard).
- The dashboard is only on Tailscale, so Telegram can't reach a webhook. Use getUpdates long-polling in the worker, with the offset stored so nothing is handled twice after a restart.
- Accept a button press only from the configured TELEGRAM_CHAT_ID; ignore everything else.
- A press must change the tag exactly as the dashboard's PUT /api/jobs/{id}/tag does, including the tag_history row. Move that logic into one shared function used by both, rather than copying it.
- After a press: answerCallbackQuery with a short "Liked", and edit the message so the buttons show the current tag (pressing it again removes it). Keep the edit that later adds the eligibility result working: whichever edit comes last must keep both the eligibility line and the buttons.
- Grouped burst messages (more than 10 jobs) and first-run summaries get no buttons.
- Existing alerts sent before this change have no buttons; that's fine.

B. A message when a job I liked or applied to closes (state goes to closed by either rule in DESIGN §3): "🔒 Closed: <company> · <title>", with the dashboard link. At most one per job, ever (same idea as the alerts table's unique key). If several close in one run, send one grouped message.

Test with a fake Telegram client the way the existing alert tests do. In the notes, list what wasn't tried against the real bot. Update DESIGN §6.
```

## 6. Stages after Applied

```
Follow the ground rules at the top of docs/next-prompts.md.

Track what happens after I apply. Today a job's tag is liked / applied / dismissed (job_user_state.tag; changes go to tag_history with an optional date and note).

- Add stages after "applied": OA (online assessment), Interview, Offer, Rejected. Decide with me whether these are more tag values or a separate stage field next to tag. Show me both options with their cost before building. Whatever we pick, an applied job must never be hidden (DESIGN §4), including when it's rejected or closed.
- On the job page: a stage picker that appears once a job is Applied, with an optional date and note for each step. Show the history as a small timeline (it's already in tag_history).
- A "My applications" view: every applied job grouped by stage, with company, title, when each stage happened and how long since. It works on phone and laptop.
- The stats strip's "Applied" counts every job applied to, whatever its stage.
- An Alembic migration, with tests for it on a copy of the real database.

Show me a mockup of the stage picker and the applications view first.
```

## 7. Same job posted in many places

```
Follow the ground rules at the top of docs/next-prompts.md.

Some companies post one internship as many jobs, one per country or city (Microsoft and Qualcomm do this), so the same title fills the list several times.

- First, measure it on a copy of the real database: how many open tech internships share company + normalised title, and the biggest groups. Put the numbers in the notes before building anything, and stop and ask me if they're small.
- Group them for display only: the stored jobs, tags, alerts and dedupe rules (DESIGN §4) stay as they are. A group is one card showing "N locations"; opening it lists each location's job with its own link and tag.
- Decide and write down what counts as the same title (case, punctuation, a location or year in the title). Be careful: "Software Engineering Intern – Data" and "– Security" are different jobs.
- Telegram: if one run finds several jobs of the same group, send one alert listing the locations instead of one each. Keep the "at most one alert per job" rule.
- A toggle to turn grouping off.

Tests on recorded real titles from the database, not invented ones.
```

## 8. "Eligible for me" view

```
Follow the ground rules at the top of docs/next-prompts.md.

Add an "Eligible for me" view: the tech internships I can actually apply to as a B.Tech student in India.

- It hides jobs whose title limits them to PhD, Master's or MBA students (app/pipeline/classify.py degree_only) and jobs where Gemini returned "warn" with a quoted restriction (job_analysis). Jobs that aren't checked yet stay visible, marked as unchecked.
- Make it a toggle next to "Tech internships / All jobs", saved in the URL. Then decide with me whether it becomes the default view, and record the decision.
- Show how many jobs it hid ("38 hidden — show them") so nothing disappears silently.
- The filter runs in SQL in /api/jobs and /api/filters, like the other filters. Check the counts on the real database copy and compare them by hand with a few jobs on each side.
```

## 9. Saved searches, alert rules and a daily digest

```
Follow the ground rules at the top of docs/next-prompts.md.

Let me save searches and choose which ones alert me straight away.

- Save the current filters (company, location, eligibility, posted, tag, search text) under a name. Saved searches appear in the filter panel, one click to apply. Store them in the database, not in the browser.
- Each saved search can be set to "Alert now" or "Daily digest".
- Today every new tech internship alerts at once (DESIGN §6). Ask me before changing that default. My suggestion: with no saved alert rules, nothing changes; once there is one, matching jobs alert at once and the rest go into the digest.
- Daily digest: one Telegram message at a time I set (default 20:00 IST): new tech internships not already alerted, liked jobs that closed, and failing sources. Send nothing on a day with nothing to say.
- The rule match must use the same filter code as /api/jobs, not a second copy, so the dashboard and alerts never disagree.
- Keep every rule from DESIGN §6: one alert per job ever, burst grouping, first-run summary, government-notice and partial-source rules.

This touches the alert path, so test it thoroughly with the fake Telegram client and update DESIGN §6.
```

## 10. Home-screen app and CSV export

```
Follow the ground rules at the top of docs/next-prompts.md.

Two small additions.

A. Let me add the dashboard to my phone's home screen (a PWA): web/public/manifest.webmanifest (name, short name, theme colors for light and dark, display standalone, start_url "/"), icons made from the existing Logo / favicon.svg at 192 and 512 px plus a maskable one, an apple-touch-icon, and the meta tags in index.html. No service worker or offline mode: the data must always be live. Check that FastAPI serves the manifest with the right content type and that it's reachable without login (it holds no data), and test it.

B. "Export CSV" on the jobs list: downloads the jobs matching the current filters (company, title, locations, posted date, tag, eligibility, apply URL, dashboard URL, first seen). Done by the API using the same filter code as /api/jobs, behind login, streamed so a 40,000-job export doesn't load everything into memory. Guard against CSV formula injection (cells starting with = + - @).
```

## 11. When each company posts internships

```
Follow the ground rules at the top of docs/next-prompts.md.

I'd like to know when each company usually opens internships, so I know when to watch.

First check whether there's enough data. The scraper started on 2026-11-10, so first_seen_at covers only a few weeks. Posted dates exist for some sources and include only jobs still open, and closed jobs are kept (never deleted). Report how many months of posted dates each of the top 15 companies has. If it's too thin to say anything honest, stop and tell me; I'll come back to this after a few months of running.

If there's enough: one line on a company's jobs, e.g. "Most internships posted Aug–Oct (from 46 postings since Mar 2026)", always showing how many postings it's based on. DESIGN §2 rules out a full analytics page, so keep it to that line, no charts page.
```
