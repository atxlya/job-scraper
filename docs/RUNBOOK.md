# Runbook

How to set up, run, check and restore the job scraper. The same steps work on the Mac (for testing) and on the Raspberry Pi.

## 1. One-time setup

### Telegram bot
1. In Telegram, message **@BotFather**, send `/newbot`, and pick a name. BotFather replies with a **token**.
2. Send any message to your new bot.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and find `"chat":{"id": ...}`. That number is your **chat ID**.

### Gemini key
1. Go to <https://aistudio.google.com/apikey> and create a key. The free tier is enough.
2. Your actual limits are shown at <https://aistudio.google.com/rate-limit>. The worker paces itself well below them: 5 requests/minute and at most 250 a day by default.

### `.env`
```bash
cp .env.example .env
```
Then fill in `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` and `GEMINI_API_KEY`. Never commit `.env`.

Both keys are optional:
- **Without Telegram:** jobs are stored, and alerts wait until it is configured.
- **Without Gemini:** jobs are stored and alerted, just without the eligibility check.

## 2. Run it

### On the Mac (testing)
Install the dependencies and prepare the database:
```bash
uv sync
```
```bash
uv run alembic upgrade head
```
Check that every source returns real jobs:
```bash
uv run python -m app.cli live-check --mode incremental
```
Do one real run into `data/jobs.db`:
```bash
uv run python -m app.cli run-once --mode incremental
```
On the first run, each company's existing internships are stored without individual alerts. You get one Telegram summary per company instead, e.g. "Loaded 12 existing internships from Google". After that, you get one alert per new internship.

### With Docker (Mac or Pi)
```bash
docker compose up -d --build
docker compose logs -f worker
```
This starts four services:

| Service | What it does |
|---|---|
| `migrate` | Prepares the database, then exits |
| `worker` | Runs the schedule below |
| `api` | Health check at `http://<host>:8000/healthz` |
| `backup` | Nightly backup at 03:00 IST into `./backups`, keeping 30 days |

The worker's schedule (all times IST):

| When | Run |
|---|---|
| Every 30 min | Quick check for new jobs |
| 02:00 | Full sweep of every source |
| 04:00 | Re-check Liked/Applied jobs and Google jobs for closures |
| Every 60 s | Gemini analysis of queued jobs |

### On the Raspberry Pi
1. Install Raspberry Pi OS 64-bit, then Docker:
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
   Then add yourself to the docker group:
   ```bash
   sudo usermod -aG docker $USER
   ```
2. Start Docker on boot. The containers restart themselves (`restart: unless-stopped`).
   ```bash
   sudo systemctl enable docker
   ```
3. Install Tailscale so you can reach the Pi from anywhere:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   ```
   ```bash
   sudo tailscale up
   ```
4. `git clone` this repo, copy `.env` over, then start everything:
   ```bash
   docker compose up -d --build
   ```

## 3. Weekly backup copy to the Mac

On the Mac, turn on **System Settings › General › Sharing › Remote Login**. Then, on the Pi, copy your SSH key to the Mac:
```bash
ssh-copy-id you@your-mac
```
Add this line to the Pi's crontab (`crontab -e`). It runs every Sunday at 05:00:
```
0 5 * * 0 BACKUP_PUSH_TARGET=you@your-mac:/Users/you/job-scraper-backups /home/pi/job-scraper/scripts/push_backup.sh >> /home/pi/push_backup.log 2>&1
```
If the Mac is offline, that week is skipped quietly.

## 4. Restore from a backup
```bash
docker compose stop worker api backup
cp backups/jobs-YYYYMMDD.db data/jobs.db
rm -f data/jobs.db-wal data/jobs.db-shm
docker compose up -d
```

## 5. Adding or fixing a company
Edit `config/sources.yaml` (see `docs/companies.md` for each platform's settings). Then check the new source against the live site:
```bash
uv run python -m app.cli live-check --source <key>
```
Restart the worker afterwards; it re-reads the registry on start:
```bash
docker compose restart migrate worker
```

## 6. When something breaks
- **Telegram "⚠️ <source> failed 3 runs in a row":** run the live check for that source to see the error:
  ```bash
  uv run python -m app.cli live-check --source <key>
  ```
- **Telegram "⚠️ N of M sources failing — network down?":** check the Pi's network. Nothing else is wrong.
- **"job count dropped from X to Y":** the site probably changed. The live check shows whether parsing still works.

## R1 verification

See [R1-notes.md](R1-notes.md) for the full results and the decisions made during the build. In short:

- **Tests:** 172 pass. **Live check:** all 32 sources return real jobs. **Real runs:** 1,351 jobs on the first run, with no duplicates on the second.
- **Still to do, needs your Telegram + Gemini keys:** run `uv run python -m app.cli analyze-one --job-id <id>` against a real job, then leave `docker compose up -d` running for 24 h with a test Telegram chat.
