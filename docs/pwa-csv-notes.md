# Home-screen app and CSV export

Branch `pwa-and-csv`, 2026-11-12, cut from `application-stages`. This is prompt 10 in [next-prompts.md](next-prompts.md). The Export button's placement was agreed from a mockup before its UI code was written.

## Status

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | 740 passing (was 726) |
| Web tests (`cd web && npm run check`) | 140 passing (was 136); type-check clean; build OK |
| Lint (`ruff check`, `ruff format --check`) | Clean |
| On a copy of the real database, in the browser | Before logging in: the manifest is served as `application/manifest+json`, an icon as `image/png`, and the CSV answers 401. After logging in: the CSV row count equals the list's total for 4 filter sets (default 208, all 1,359, Intel 60, liked 8). No cell in the real data needed the formula guard. The button checked at 1440 px and 375 px, light and dark. No server errors |
| 40,000 jobs | A generated database of 40,000 jobs, each with a 5 KB description: the export took 6.0 s on the Mac (5.0 MB of CSV), with a peak of 3.8 MB of Python memory |
| **Not checked** | Adding to a real phone's home screen (iOS Safari or Android Chrome), so not the icon, the name or the status bar either; clicking Export in a browser and opening the file in Excel or Numbers (it was checked through the API only); the export's speed on the Pi |

## What changed

**A. Home-screen app**
- `web/public/manifest.webmanifest`:
  - name "Job Scraper", short name "Jobs"
  - `start_url` and `scope` `/`, `display: standalone`
  - theme `#ffffff`, background `#f6f7f9`
  - icons: 192, 512, and a maskable 512
- `web/public/icons/`: those three icons plus a 180 px `apple-touch-icon.png`.
  - They're drawn from the favicon's artwork by [scripts/make_icons.py](../scripts/make_icons.py), which renders SVG with headless Chrome, so no image library joins the project.
  - The maskable icon and the iOS icon are full squares, because the OS cuts its own shape. The maskable bag is shrunk to sit inside the safe zone.
- `index.html`: tags for the manifest, the apple-touch-icon, standalone mode on iOS and Android, the iOS app title "Jobs", and a status-bar color for each theme.
- `theme.ts`: a theme picked in the app also sets the status-bar color. Otherwise the phone would follow the system theme while the page showed the other one.
- FastAPI sets the manifest's content type itself, instead of relying on the system MIME table, which a slim Docker image may lack. The manifest and icons were already served without login, like the rest of the built page; `/api` stays locked.
- **No service worker** (a test fails if one is added), so there's no offline mode and nothing is cached beyond what the browser already does.

**B. CSV export**
- `GET /api/jobs.csv`, behind login: the same `JobFilters` and the same `_filtered()` query as `/api/jobs`, in the list's order. The file is named `jobs-YYYY-MM-DD.csv` (IST date).
- **Columns:** Company, Title, Locations (joined with "; "), Posted (IST date), Tag, Stage, Eligibility (Eligible / Check needed / Not checked), Apply URL (or the posting's URL), Dashboard URL, First seen (IST).
- **Streamed:**
  - A generator opens its own session and reads with `yield_per(500)`, sending each batch as it's written.
  - Descriptions and Gemini sections are deferred, never loaded.
  - The file starts with a UTF-8 BOM, so Excel doesn't read accented place names as Latin-1.
- **Formula guard:** every text cell starting with `=`, `+`, `-`, `@`, a tab or a carriage return gets a leading `'` (the OWASP list).
- **Dashboard:** "Export CSV" is a plain download link in the list's title row, next to "Mark all as seen", as in the mockup. It's a bordered button on a laptop and a text link on a phone, and it's hidden while the list is empty.

## Decisions

- **A Stage column was added**, which the prompt didn't list, since applied jobs now have stages. *Cost:* one mostly empty column.
- **The Dashboard URL comes from `DASHBOARD_URL`**, or else from the address the request came in on. So an export from `http://pi:8000` links back there.
- **A plain link, not a button that fetches.** The browser streams the file to disk itself, with the login cookie, so no 40,000-row file is held in the page.
- **One theme color in the manifest.** The manifest format has no per-theme colors, so the dark color comes from the `theme-color` meta tags; the manifest's value is the light header color.
- **Icons are committed PNGs** made by a script, not built on each deploy, so the Docker build doesn't need Chrome.

## Bug avoided while building

Running prettier on `JobList.tsx` reformatted the whole file, but this project doesn't use prettier. The file was restored and only the link was added.

## Left for later

- **No offline mode**, as asked. Opened with no network, the home-screen app shows the browser's own error page.
- **No export of the applications view** (`/applications`). Filtering the list by tag Applied and exporting gives the same jobs, with Stage as a column.
