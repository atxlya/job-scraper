# Telegram: tag buttons and "closed" messages

Branch `telegram-buttons`, 2026-11-12. This is prompt 5 in [next-prompts.md](next-prompts.md). There's no dashboard change, so no mockup was needed.

## Status

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | 703 passing (was 667) |
| Web tests (`cd web && npm run check`) | 120 passing, no change |
| Lint (`ruff check`, `ruff format --check`) | Clean |
| Tests break when the fix is undone | Checked by hand for three: eligibility edit without buttons (3 tests fail), no lock around the redraw (1 fails), the "tagged after it closed" rule removed (1 fails) |
| Migration 0005 on a copy of the real database | Upgrades cleanly. Nothing to seed: the 8 tagged jobs are all liked and open. The "closed" query takes about 10 ms; an alert for a real liked job draws with "✓ Liked" |
| **Not tried against the real bot** | See the list below |

**Not tried against the real bot.** Every Telegram call was tested against a fake Bot API (respx), like the existing alert tests. Nothing was sent to Telegram, and `.env` wasn't touched. So these are unproven:
- That Telegram accepts the `reply_markup` as built, and shows three buttons in one row on a phone (long labels such as "✓ Dismissed" might be cut short).
- That `getUpdates` with `allowed_updates: ["callback_query"]` and a 50 s hold works from the Pi, and the 65 s HTTP wait is long enough.
- **`getUpdates` refuses to work while a webhook is set on the bot** (409). If one was ever set, remove it with `deleteWebhook` once.
- Only one process may poll a bot. If a second worker runs (say on the Mac while the Pi is up, with the same token), each gets "Conflict" errors; the worker logs them and backs off.
- The exact text of the "message is not modified" error, which is treated as success. It was copied from the Bot API's usual answer, not seen live.
- Editing an alert that's several days old. Bots can edit their own messages without a time limit, as far as is known, but that hasn't been seen here.
- Answering a press after the worker was down for a while: Telegram rejects answers to old presses ("query is too old"). The tag is still set and the message still redrawn; only the small notice is lost. This is tested with a fake error only.
- A `TELEGRAM_CHAT_ID` that is a group. Then any member's press counts (see Decisions).

## What changed

**A. Buttons on job alerts**
- `app/core/tags.py`: `set_tag()` is the one place a tag changes. It creates the job's state row (insert-or-ignore, as before) and adds a `tag_history` row when the tag really changes. `PUT /api/jobs/{id}/tag` and the Telegram handler both call it. The API keeps its 404 check before it.
- `app/notify/telegram.py`: `send` and `edit` take optional buttons. `get_updates` and `answer_callback` are new. Error messages now carry Telegram's own description, so "message is not modified" can be told apart and ignored.
- `app/notify/alerts.py`: `render_alert()` draws an alert's text and buttons from the database as they are now. The first send, the eligibility edit and the redraw after a press all use it. The eligibility edit and the press redraw hold one lock (`channel.message_lock`) while they read and edit. A test makes a slow eligibility edit race a press, and it ends with both parts only because of the lock.
- `app/notify/buttons.py`: handles one update. A button's data is `t:<job id>:<l|a|d|->`.
  - Presses from another chat are ignored, with no answer.
  - Bad data gets "Unknown button"; a job that doesn't exist gets "Job not found".
  - The tag change and the next offset go in one commit, before anything is sent to Telegram.
  - An update that crashes the handler is logged and skipped, so it can't hold up all later presses.
- `app/worker/poller.py`: the long-poll loop. It runs as a task beside the scheduler when Telegram is configured. On errors it waits 5 s, then 10, 20, … up to 5 minutes.

**B. "Closed" messages**
- `app/notify/closed.py`: after each round of sources (`run_all`), it looks for closed jobs tagged liked or applied that have no `closed_alerts` row. One job gets "🔒 Closed: <b>company</b> · title" and a Dashboard link (or the posting's link if `DASHBOARD_URL` isn't set). Several get one grouped message, cut at 30 lines like the burst message.
- A row is written only after the send works, so a failed send is retried next round.
- Migration `0005` adds `closed_alerts`, unique on the job. It also marks jobs that are already closed and tagged as handled, so the first round after deploying doesn't announce old closures.

## Decisions

- **A button sets what its label says, not "toggle".** "❤️ Like" sets liked; "✓ Liked" removes the tag. *Why:* a press handled twice, or pressed on an old message after a dashboard change, can't flip the tag the wrong way. *Cost if wrong:* none found; it's what "pressing it again removes it" looks like.
- **Applied from Telegram is dated today (IST), with no note,** the same as the `a` key. *Cost if wrong:* to record another date or a note, use the dashboard form.
- **The configured chat is what's checked, not the person.** In a private chat with the bot those are the same. *Cost if wrong:* if `TELEGRAM_CHAT_ID` is ever a group, every member can tag your jobs.
- **"Closed" looks at the jobs' state after each round, not at what the round closed.** *Why:* it also catches jobs closed by the dashboard's "fetch description" (which can't send Telegram messages, being the API process), and retries a failed send for free. *Cost if wrong:* a job closed from the dashboard is reported up to 30 minutes later, after the next round.
- **A job tagged only after it closed isn't reported** (a `tag_history` row later than `closed_at`). *Cost if wrong:* changing liked → applied after the job closed but before the round ends skips the message. Closures the worker finds are reported when that round ends, so the window is the rest of the round.
- **The offset lives in `settings`,** not a new table. Only `closed_alerts` needed a migration.

## Left for later

- **A tag set on the dashboard doesn't redraw the Telegram buttons straight away.** They catch up at the alert's next edit. The API process has no Telegram client; doing it would mean sending from the API or a queue the worker reads.
- **Grouped burst messages have no buttons,** as asked. Jobs in them can only be tagged from the dashboard.
- **No "closed" message for a job you dismissed or never tagged,** as asked.
- **No reply when you type to the bot.** Only button presses are asked for; text messages are skipped.
