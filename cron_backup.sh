#!/usr/bin/env bash
# =============================================================================
# cron_backup.sh — the nightly database dump. plan.md §17.5.
#
# ALWAYSDATA'S OWN BACKUPS COME FIRST
#   Every plan includes daily backups, kept for 3 days on the free plan, at
#   /home/<account>/admin/backup/<date>/ — including a zstd'd MySQL dump of every
#   database. Restore from the panel, or:
#
#     zstdcat /home/<account>/admin/backup/<date>/mysql/<db>.sql.zst \
#       | mysql -h mysql-<account>.alwaysdata.net -u <account> -p <db>
#
#   SO WHY THIS SCRIPT? Because three days is not long enough for the question that
#   actually gets asked — "what did the register look like when we reported the
#   cohort in January" — and because the uploads directory is NOT in those backups.
#   This writes both, somewhere you control, and keeps 30 days.
#
# SCHEDULE IT IN THE PANEL
#   Web > Advanced > Scheduled tasks (or "Extra > Cron"), command:
#
#     /home/<account>/sylhet/cron_backup.sh >> /home/<account>/sylhet/var/backup.log 2>&1
#
#   Nightly, 02:15 server time. `flask backup` does the work — the DSN is parsed by
#   the application, so no password is ever written into a crontab or into this file.
#
# WHAT IT LEAVES OUT, DELIBERATELY
#   `.env` — a backup that sits next to a dump containing every participant record
#   should not also carry the SECRET_KEY that signs admin sessions.
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
PYTHON="$VENV_DIR/bin/python"

#: How many days an archive is kept. 30 days, so a report written a month ago can
#: still be reproduced. alwaysdata's own 3 days cover "the deploy just broke it".
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"

echo "--- backup started $(date -Is)"

[ -x "$PYTHON" ] || { echo "no interpreter at $PYTHON" >&2; exit 1; }

# The application does all of it: it parses the DSN and hands the password to the
# dump tool through the environment (never through argv or this file), it writes the
# `backups` row the admin screen reads, and it deletes what has expired.
#
# RETENTION IS NOT REPEATED HERE ON PURPOSE. A shell sweep counting files would
# disagree with the rows counting days — and the version that disagrees is the one
# that leaves /admin/backups offering a download of an archive that is gone.
#
# .env IS LOADED INTO THIS SHELL, and that is not a convenience. A scheduled task
# starts with an EMPTY environment — it gets none of the panel's variables — and
# `app/config.py` skips `.env` the moment APP_ENV is production. So exporting APP_ENV
# below while leaving the file on disk would send `flask backup` into production with
# no DATABASE_URL: it would fail, write a FAILED row, and mail nobody. Sourcing the
# file first makes every value a real environment variable, so nothing depends on
# which of the two readers wins.
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_DIR/.env"
  set +a
else
  echo "WARNING: no .env at $PROJECT_DIR — the task must be given the panel's variables" >&2
fi
export APP_ENV=production
"$PYTHON" -m flask backup --keep-days "$KEEP_DAYS"

echo "--- backup finished $(date -Is)"
