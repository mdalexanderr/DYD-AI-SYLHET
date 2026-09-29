#!/usr/bin/env bash
# =============================================================================
# deploy.sh — put a new revision live. plan.md §17.3.
#
#   ./deploy.sh              # pull, install, migrate, verify
#   ./deploy.sh --no-pull    # the code arrived by rsync; just install and verify
#   ./deploy.sh --check      # verify only — run this after any hand-edit
#
# WRITTEN FOR ALWAYSDATA, AND IT WORKS ON CPANEL TOO
#   Both hosts give you SSH and a virtualenv, and neither gives you a build step:
#   the compiled CSS and the React bundle are COMMITTED (§8.1), so there is no Node
#   on the server and no `npm run build` here. If either is missing from the
#   repository, that is a bug in the commit, not something this script patches.
#
# WHAT IT REFUSES TO DO
#   * Write `.env`, or any configuration. A deploy that writes configuration is a
#     deploy that can overwrite it (§17.2 step 6).
#   * Run the migrations before checking the configuration. `flask db upgrade`
#     against the wrong `DATABASE_URL` migrates the wrong database — and on a dev
#     shell without APP_ENV set, "the wrong database" is a local SQLite file.
#   * Swallow a failed preflight. Everything is `set -e`: a red line stops the run
#     with the site still serving the previous revision.
#
# ENVIRONMENT
#   APP_ENV=production must be set HERE, in the shell, not only in the site's panel
#   variables. The panel's variables reach the WEB process (uWSGI); an SSH session
#   gets none of them, and `app/config.py` would then load `.env` and fall back to
#   the development class. `deploy.sh` therefore exports APP_ENV itself and reads
#   the rest from `.env` (chmod 600) — see DEPLOY.md, "Two places for env vars".
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# The virtualenv: $VENV_DIR if the operator set one, else a sibling of the project.
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
PYTHON="$VENV_DIR/bin/python"

DO_PULL=1
CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --no-pull) DO_PULL=0 ;;
    --check)   CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m   %s\n' "$*"; }
warn() { printf '   \033[33mwarn\033[0m %s\n' "$*"; }
die()  { printf '   \033[31mFAIL\033[0m %s\n' "$*" >&2; exit 1; }

# ── 0. The environment, before anything reads it ─────────────────────────────
# APP_ENV IS EXPORTED HERE, BEFORE ANY PYTHON STARTS — and the order is the whole
# point. app/config.py chooses its config class at import time, and it skips `.env`
# entirely once APP_ENV is already `production`. So exporting it and stopping there
# would hide the file from every command below and this deploy would run against
# defaults: an empty SECRET_KEY, no DATABASE_URL.
#
# The fix is to load `.env` into this SHELL first. Every value in it then exists as a
# real environment variable, which is also what the web process gets from the panel —
# so both halves of the deployment are configured from the same file, and skipping
# the file changes nothing.
#
# .env IS THE DEPLOY'S CONFIGURATION, and the panel's variable list is the WEB
# process's. They must agree; DEPLOY.md §5 is the table.
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_DIR/.env"
  set +a
else
  warn "no .env here — running on the environment this shell already has"
fi
export APP_ENV=production   # the assertion, after the file rather than before it

say "Deploying $PROJECT_DIR"
[ -x "$PYTHON" ] || die "no interpreter at $PYTHON — create the venv first:
     python -m venv $VENV_DIR && $VENV_DIR/bin/pip install -r requirements.txt
   or point VENV_DIR at an existing one."
ok "python: $("$PYTHON" -V 2>&1)"

# ── 1. The code ──────────────────────────────────────────────────────────────
if [ "$DO_PULL" = "1" ]; then
  say "Fetching the revision"
  if [ -d .git ]; then
    git rev-parse --abbrev-ref HEAD
    git pull --ff-only
    ok "at $(git rev-parse --short HEAD) — $(git log -1 --pretty=%s)"
  else
    warn "not a git checkout; assuming the files were uploaded. Use --no-pull next time."
  fi
fi

# ── 2. Dependencies ──────────────────────────────────────────────────────────
# Always, not only when requirements.txt changed: a wheel that failed to build on
# the first deploy is the reason the site is down, and pip is cheap when everything
# is already satisfied.
say "Dependencies"
"$PYTHON" -m pip install --quiet --disable-pip-version-check -r requirements.txt
ok "requirements satisfied"

# ── 3. Preflight — configuration, then the schema ────────────────────────────
say "Configuration"
"$PYTHON" -m flask check-config || die "check-config refused this configuration. Nothing was changed."

if [ "$CHECK_ONLY" = "0" ]; then
  say "Database migrations"
  "$PYTHON" -m flask db upgrade
  "$PYTHON" -m flask check-db || die "check-db refused the schema. The site is still on the previous revision."
fi

# ── 4. Directories the app writes to ─────────────────────────────────────────
# Created here rather than assumed, because a missing UPLOAD_ROOT turns every
# image upload into a 500 and a missing BACKUP_ROOT makes the nightly job fail in
# a cron log nobody reads. The paths are asked of the application rather than
# hard-coded, so a deployment that moved UPLOAD_ROOT gets the right directory.
if [ "$CHECK_ONLY" = "0" ]; then
  say "Writable directories"
  paths="$("$PYTHON" -c '
import sys
sys.path.insert(0, ".")
from app.config import BaseConfig, VAR_DIR
print(BaseConfig.UPLOAD_ROOT)
print(BaseConfig.BACKUP_ROOT)
print(VAR_DIR / "cache")
')"
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    mkdir -p "$path"
    ok "$path"
  done <<< "$paths"
fi

# ── 5. The site must actually render ────────────────────────────────────────
say "Rendering every page"
# StrictUndefined, so a template that references a variable nobody passes fails here
# rather than rendering an empty block on a live page (step 2.16).
"$PYTHON" -m flask render-check --all || die "a page failed to render. Investigate before restarting."

# ── 6. Reload ────────────────────────────────────────────────────────────────
# alwaysdata's uWSGI watches the application file when it is configured to; touching
# it is the cheap way to ask for a reload. If the site keeps serving the old code,
# restart it from Web > Sites in the panel — that always works.
say "Asking the web server to reload"
touch wsgi.py
ok "touched wsgi.py"
warn "if the site is still serving the old revision, restart it in the panel (Web > Sites)"

say "Done — $(git rev-parse --short HEAD 2>/dev/null || echo 'uploaded revision')"
