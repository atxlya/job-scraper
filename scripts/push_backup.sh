#!/usr/bin/env sh
# Copy the newest backup to another machine (e.g. your Mac over Tailscale).
# Run weekly from the Pi's crontab, see docs/RUNBOOK.md.
#   BACKUP_PUSH_TARGET=user@my-mac:/Users/me/job-scraper-backups scripts/push_backup.sh
set -eu
DIR="${BACKUP_DIR:-$(dirname "$0")/../backups}"
TARGET="${BACKUP_PUSH_TARGET:?set BACKUP_PUSH_TARGET}"
NEWEST="$(ls -1t "$DIR"/jobs-*.db 2>/dev/null | head -n 1 || true)"
[ -n "$NEWEST" ] || { echo "no backups in $DIR"; exit 0; }
HOST="${TARGET%%:*}"; HOST="${HOST#*@}"
if ! ssh -o BatchMode=yes -o ConnectTimeout=10 "${TARGET%%:*}" true 2>/dev/null; then
  echo "$HOST unreachable, skipping this week"; exit 0
fi
rsync -a "$NEWEST" "$TARGET/"
echo "pushed $NEWEST to $TARGET"
