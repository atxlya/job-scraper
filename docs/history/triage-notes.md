# Keyboard and swipe triage

Branch `triage`, 2026-11-12. This is prompt 4 in [next-prompts.md](next-prompts.md). The mockup and three questions were answered before any UI code was written.

## Status

| Check | Result |
|---|---|
| Backend tests (`uv run pytest`) | 667 passing (was 666); the new one reproduces a server race this work exposed (below) |
| Web tests (`cd web && npm run check`) | 120 passing (was 101): every key, the "not while typing" rule, keys with Ctrl/Cmd/Alt, keys pressed in quick succession, swipes (right, left, short, vertical, no accidental open), Undo by button and by `z`, the toast's 5 seconds |
| Lint (`ruff check`, `ruff format --check`) | Clean |
| On a copy of the real database | Laptop: `j j l d z` and `?` all worked, with no server errors after the fix. Phone (browser emulation, mouse drag): swipe left dismissed a card, showed the toast, and Undo brought it back |
| **Not checked** | A real phone's touch swipes and vertical scrolling (`touch-action: pan-y` leaves vertical scrolling to the browser, but only a real touch screen proves it); Safari |

## What changed

**Keyboard** (laptop width; ignored while typing in a field and with Ctrl, Cmd or Alt held):

| Key | Does |
|---|---|
| `j` / `k` | Next / previous job. The detail panel follows, the card scrolls into view, and the job counts as seen. At the end of the loaded list, `j` loads more |
| `l` | Like, or remove it if liked (same as the button) |
| `a` | Applied, dated today, with no note (you chose this over opening the form), or remove it if applied |
| `d` | Dismiss, move to the next job, and show Undo (or un-dismiss a dismissed job, when "show dismissed" is on) |
| `u` | Remove the tag |
| `z` | Undo the last dismiss or swipe, while its toast is showing |
| `o` | Open the apply link (or the posting) in a new tab |
| `/` | Focus search (the slash isn't typed) |
| `Esc` | Leave search; otherwise close the job you opened |
| `?` | The list of shortcuts |

A "Press ? for shortcuts" hint sits under the list until you open the list once.

All keys use the same `PUT /api/jobs/{id}/tag` as the buttons (`web/src/tagging.ts`).

**Phone swipes** (`components/SwipeCard.tsx`, pointer events, no library):
- Right = Like (blue, "♥ Like" shows as the card slides); left = Dismiss (amber, "Dismiss ✕").
- It commits past a third of the card's width (at least 80 px); otherwise the card springs back.
- The direction is decided after 10 px. A drag that starts vertical is left to the browser to scroll.
- The click at the end of a swipe doesn't open the job.
- Swiping right on a job that's already liked does nothing.

**Undo toast** (`components/Toast.tsx`): "Dismissed · title" or "Liked · title", with an Undo button and a bar showing the time left. It lasts 5 seconds. Undo restores the tag the job had before (not just "none"), and after a keyboard dismiss it reopens the job.

## Bugs found while checking, now fixed

1. **A server error when "seen" and a tag arrive together** (fixed in `app/api/jobs.py`).
   - Moving to a new job with `j` marks it seen; pressing `l` straight after tags it. Both requests looked for the job's state row, found none, and both tried to create it. The second one failed with a unique-constraint error (500), and the preview showed two of them.
   - The row is now created with insert-or-ignore.
   - The new backend test makes two requests check at the same moment on purpose. It fails without the fix.
   - This bug existed before; triage just makes it easy to hit.
2. **Keys pressed quickly acted on the wrong job.**
   - `j j l` in a fast burst liked the first job, because each key read the open job from the last screen update.
   - The dashboard now keeps the open job in a ref that moves as soon as a key moves it.
3. **A mouse drag on a card started the browser's own link drag,** which cancels the swipe. Cards set `draggable={false}`. It matters for a narrow desktop window; phones don't drag links on a swipe.

## Decisions

- **`a` marks applied today, without the form** (you chose this). *Cost:* to record a different date or a note, use the button or edit the history.
- **Undo after `d` too, plus `z`** (you chose this).
- **Moving with `j`/`k` marks the job seen,** the same as clicking it. Only the job the dashboard opens by itself stays unseen.
- **A swipe sets the tag; the keys toggle it,** as the buttons do. *Cost:* swiping right on a liked job does nothing, rather than removing the like.

## Left for later

- **No triage keys on a phone with a keyboard,** or on a tablet narrower than 1024 px. The keys follow the laptop layout, where there's a detail panel.
- **An Undo after the toast is gone** isn't possible. Dismissed jobs can still be found with "Show dismissed".
- **Swipes on the job page** (`/jobs/:id` on a phone) aren't supported; only cards in the list swipe.
