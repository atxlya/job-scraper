# Phone layout, header and stats

Branch `phone-header`, 2026-11-12. This is prompt 1 in [next-prompts.md](next-prompts.md). The mockup was approved before any UI code was written.

## Status

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | 616 passing (was 615) |
| Web tests (`cd web && npm run check`) | 73 passing (was 49); type-check clean; build OK |
| Lint (`ruff check`, `ruff format --check`) | Clean |
| On a copy of the real database (1,359 jobs) | Phone 375×812 dark and light, tablet 768 light, laptop 1024 and 1440 dark and light: no sideways scrolling at any width |
| Goal: two job cards visible on a 375×812 phone | **Four** fully visible; the first starts at 227 px (it used to start about 580 px down, so not even one card fit) |
| Liked tile → list | 8 on the tile, 8 in the list |
| **Not checked** | A real phone (only the browser's phone emulation); the "New today" filter on a day with new jobs (the copy had 0 today; it's covered by a backend test with jobs either side of midnight IST); the Sources and job pages on a phone, beyond the tests |

## What changed

**Header**
- **Phone:** logo, search and one ⋯ menu with Add company, Sources, Theme (cycles System → Light → Dark and keeps the menu open), Log out, and Log out everywhere… (keeps its confirm). "Sources" isn't offered on the Sources page itself. The "Job Scraper" name is hidden on phones; the logo link still has it as its label.
- **Laptop (1024 px and up):** search, Add company, the theme button, and an **Account** menu with the two log-outs.
- The menu is a new `components/Menu.tsx`: a WAI-ARIA menu button. Esc or a click outside closes it, focus goes back to the button, and ↑/↓/Home/End move between items.

**Stats**
- The four stats are buttons. Phone: one row of small chips that scrolls sideways ("Open" is short for "Open tech internships"). Tablet and laptop (768 px and up): the tiles as before.
- Each one applies a whole filter set (`PRESETS` in `filters.ts`), so the list matches the number:
  - New today → `?new=today`
  - Open tech internships → no filters
  - Liked → `?view=all&tag=liked`
  - Applied → `?view=all&tag=applied`
- A stat shows as active (blue, `aria-pressed`) only while the filters match its preset exactly. Adding a company filter, for example, turns it off. The open job (`?job=`) is kept.

**List header**
- "Mark all as seen" moved from the header to the list's title row, next to the count. It's a text link on phones and a small button on laptops.
- On phones the Filters button sits next to the list title, and the filter panel opens under that row. Before, the panel opened above the button and pushed it down the page.

**New filter: `new=today`**
- `GET /api/jobs?new=today`: jobs first seen since midnight IST. It's the same rule as the stats tile, and both now use one helper, `ist_midnight()` in `app/api/deps.py`.
- The filter panel has a "First seen today" chip under Posted, so the filter can be seen and removed there too.
- It isn't remembered with the other filters in the browser, because tomorrow it would show an empty list.

## Decisions

- **A stat replaces the filters instead of adding to them** (you chose this). *Cost:* clicking a stat loses the filters you had set, search included.
- **Liked and Applied switch to "All jobs".** Their counts include non-tech jobs, so "Tech internships" would show fewer than the number. *Cost:* the list title changes to "All jobs" when you click them.
- **A new `new=today` filter, not "Posted: last 24 hours"** (you chose this). *Cost:* one more query parameter in the API.
- **Phone vs laptop header at 1024 px** (the existing `WIDE` breakpoint), **chips vs tiles at 768 px.** A tablet gets the ⋯ menu with tiles. *Cost:* none seen at 768; this is the width where four tiles first fit.
- **Theme in the phone menu is one item that cycles,** as in the mockup, not three choices.

## Left for later

- **"Open tech internships" counts slightly differently from its list.** The tile counts dismissed jobs; the list hides them and shows closed jobs you liked or applied to. The two numbers can differ by a few. This was already true before; making them agree means changing either the stats query or plan D6.
- **The filters you last used are remembered** (plan D5). After you click Liked, the next visit opens on Liked. This is the existing behaviour, but it's now one tap away, so you'll notice it more.
- At 1024 px the job list column is narrow. That's prompt 2.
- The project has no ESLint config (`npx eslint` asks for one). Type-checking and tests cover the web code.
