# Job list clean-up

Branch `job-list-cleanup`, 2026-11-12. This is prompt 2 in [next-prompts.md](next-prompts.md). The mockup was approved before any UI code was written.

## Status

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | 658 passing (was 616), 42 of them new tests for locations |
| Web tests (`cd web && npm run check`) | 88 passing (was 73); type-check clean; build OK |
| Lint (`ruff check`, `ruff format --check`) | Clean |
| Locations on real data | All 489 distinct first locations in the database run through the new code and checked by eye; the odd ones are listed under "Left for later" |
| On a copy of the real database | Laptop 1440 light and dark, 1024 light, phone 375 dark. List 413 px, details 619 px at 1440; no sideways scrolling. An auto-opened job made **no** `/seen` or `/description` request |
| **Not checked** | The Eligible badge on real data (this database has no Gemini results yet; it's covered by tests); flags on Windows (it shows the two letters, e.g. "DE", instead of a flag); a real phone |

## What changed

**1. Eligibility badges.** A card shows "Eligible" or "Check needed" only once there is a result. While a job is unchecked or being checked it shows nothing. The detail panel still explains the status in full. On a phone this alone fits about six cards on screen instead of four.

**2. Laptop layout.**
- The filters keep 240 px; the list and the details split the rest 40/60 (413 / 619 px at 1440).
- Titles stop at 2 lines.
- The list's title row is now two lines on laptops too (title; then count and "Mark all as seen"). At 413 px a single row wrapped badly.
- With no job picked, the first job in the list opens and is outlined as selected.
- **How "seen" worked, and still works:** opening a job's details sends `POST /api/jobs/{id}/seen` and clears its NEW badge.
  - An auto-opened job doesn't send it. The job counts as seen only once you click it (`JobDetail`'s new `picked` prop).
  - An auto-opened job also doesn't fetch a missing description from the company's site (plan D8). Otherwise every page load or filter change would make a request to a careers site you never clicked on. It shows a "Fetch description" button instead.
  - It has no close button. Closing a job you picked brings the first job back.

**3. Company icons.**
- Initials sit on a color worked out from the company's slug (FNV-1a hash → hue), so a company always gets the same color. The color has separate light and dark versions.
- A logo is used when there's a file `web/src/logos/<slug>.svg` or `.png`. These are bundled at build time; nothing is fetched from other sites while the page runs.
  - *Differs from the prompt:* the prompt said `web/public/logos/`. Vite can't list files in `public/` from code, so a missing logo would have meant a 404 request for every company.
- Logos for the 10 companies with the most open jobs:

| Company | Result | Source |
|---|---|---|
| Honeywell | ✅ "H" mark | honeywell.com newsroom page: `/content/dam/honcorp/us-en/common-assets/logos/hon-honeywell-technologies-logo-mini.svg` |
| KPMG India | ✅ wordmark | kpmg.com/in/en/media.html header: `…/header_v2/logo.coreimg.svg/…/logo.svg` |
| American Express | ✅ blue box | about.americanexpress.com newsroom: `aexp-static.com/…/img/logos/dls-logo-bluebox-solid.svg` |
| PwC | ❌ missing | pwc.com answers 403 to scripts (bot protection, not bypassed) |
| Oracle | ❌ missing | oracle.com answers 403 |
| Intel | ❌ missing | intel.com answers 403 |
| Barclays | ❌ missing | No logo file on its press pages (the logo is drawn in the page) |
| JPMorgan Chase | ❌ missing | Same as Barclays |
| Dell | ❌ missing | Its newsroom only links a favicon PNG, which came back empty |
| Philips | ❌ missing | Only a white footer logo, invisible on a white tile; I didn't recolor it |

  Every SVG was checked for scripts, event handlers and external links before it was added (none had any). To add a logo, drop `<slug>.svg` into `web/src/logos/` and rebuild.

**4. Locations.**
- The API sends five new card fields: `place` ("Ratingen, Germany"), `country` (ISO code, for the flag), `more_places`, `india` and `remote`.
- `location` (all the locations) stays; it's now the tooltip on the card's second line.
- The parsing is in `app/api/place.py` and copes with each site's style:
  - City first: "Ratingen, Nordrhein-Westfalen, Germany"
  - Country first: "Finland, Satakunta, Tampere", "US, California, Folsom"
  - Code first: "ES - Madrid, Spain"
  - No country: "California - San Francisco", "O'Fallon, Missouri"
  - State codes: "Abilene, TX, United States"
  - Office codes: "IND-Bangalore Electronic City - S1", "USA-CA - Promontory B"
  - All capitals: "BOURNEMOUTH"
  - Notes: "(do not use) Mumbai …"
  - Remote: "Remote - Germany"
- Only the job's own country codes count as countries, so "Georgia" (a US state) and "IN" (Indiana) aren't read as countries.
- The **India** chip shows when any location is in India. **Remote** shows when the remote type is "remote" or a location says "Remote".
- Short country names: USA, UK, UAE, Russia, South Korea; the rest use pycountry's common name.

## Decisions

- **Locations are worked out on the server,** next to the data, and tested in Python against real strings. *Cost:* five more fields per card in `/api/jobs` (about 60 bytes each).
- **The India chip shows even when the place already says India.** It's there for jobs whose *first* location is somewhere else, and for scanning the list quickly. It was in the approved mockup.
- **Philips's white logo wasn't recolored.** Changing a brand mark felt like the wrong call. *Cost:* Philips keeps its initials.

## Left for later

- **Office addresses with no separator stay long,** e.g. "Milano Via Turati 25-27, Italy", "Zürich Uraniastrasse 9, Switzerland", "1530 FM 973 Taylor, USA". Splitting a street from a city inside one phrase needs a list of cities.
- **"Illinois - Chicago" with no country code reads "Illinois".** It's one source; its country codes are empty, so the state can't be recognised.
- **"N Locations"** (Workday's own text when a job has many locations) is shown as is.
- **At 1024 px the list column is about 230 px wide,** so titles wrap. The 40/60 split could switch on at 1280 px instead, keeping 50/50 below that.
- **KPMG's logo is a wide wordmark,** so it's small in a 40 px tile.
- **Logos still missing** for seven of the top ten companies (table above). If you have the files, drop them into `web/src/logos/`.
