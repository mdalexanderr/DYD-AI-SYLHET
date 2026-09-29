#!/usr/bin/env bash
# =============================================================================
# rollback.sh — go back to the previous revision. plan.md §17.4.
#
#   ./rollback.sh                 # back one commit, reinstall, verify
#   ./rollback.sh <rev>           # a specific revision
#   ./rollback.sh --list          # what is available
#
# WHAT THIS DOES NOT DO, ON PURPOSE
#   It does not touch the database. A schema change is not undone by going back a
#   commit: the code from before the migration expects a table that no longer
#   exists — or, worse, an older column layout that is silently read as valid.
#   `flask db downgrade` is printed rather than run, because a downgrade that drops
#   a column drops the column's DATA, and whether that is acceptable is a decision
#   about the programme's records rather than about this deployment.
#
#     Roll the code back first. If the app then reports a schema problem, read the
#     migration's own docstring — this project writes them for exactly this moment —
#     and decide. alwaysdata also keeps three days of daily backups, which is the
#     answer to "I already ran the downgrade".
#
# THE SAFEST ROLLBACK IS USUALLY NOT THIS SCRIPT
#   On alwaysdata, a site that is serving errors usually needs `git checkout` of a
#   known-good revision and a restart. That is what this is, with the preflight and
#   the dependency install that make it safe to run without thinking.
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
PYTHON="$VENV_DIR/bin/python"

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '   \033[32mok\033[0m   %s\n' "$*"; }
warn() { printf '   \033[33mwarn\033[0m %s\n' "$*"; }
die()  { printf '   \033[31mFAIL\033[0m %s\n' "$*" >&2; exit 1; }

[ -d .git ] || die "not a git checkout — there is no revision to go back to.
   If the code was uploaded by rsync, roll back by uploading the previous copy."
[ -x "$PYTHON" ] || die "no interpreter at $PYTHON (set VENV_DIR)"

TARGET=""
case "${1:-}" in
  --list) git log --oneline -15; exit 0 ;;
  "")     TARGET="HEAD~1" ;;
  *)      TARGET="$1" ;;
esac

git rev-parse --verify --quiet "$TARGET^{commit}" >/dev/null \
  || die "'$TARGET' is not a revision in this repository"

# The environment, exactly as deploy.sh does it: `.env` into the shell FIRST, then
# assert production. The app skips `.env` once APP_ENV is production, so a value the
# file carries has to be exported here to reach the CLI subprocesses below — and an
# SSH session gets none of the panel's variables.
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_DIR/.env"
  set +a
fi
export APP_ENV=production

say "Current: $(git rev-parse --short HEAD) — $(git log -1 --pretty=%s)"
say "Target:  $(git rev-parse --short "$TARGET") — $(git log -1 --pretty=%s "$TARGET")"

# Refuse to throw away uncommitted work: on a server that is usually a hand-edit
# somebody made at 2am to keep the site up, and it may be the fix worth keeping.
if ! git diff --quiet || ! git diff --cached --quiet; then
  warn "there are uncommitted changes in this checkout:"
  git status --short
  die "commit or discard them first — 'git stash' keeps them recoverable"
fi

git checkout --detach "$TARGET"
ok "checked out $(git rev-parse --short HEAD)"

say "Dependencies"
"$PYTHON" -m pip install --quiet --disable-pip-version-check -r requirements.txt
ok "requirements satisfied"

say "Configuration"
"$PYTHON" -m flask check-config || die "this revision's configuration check failed — roll forward again"

say "The schema, read-only"
# check-db is a READER: it reports what is wrong and changes nothing. That is the
# right call here, because the question at this moment is "does this revision agree
# with the database", not "make them agree".
if "$PYTHON" -m flask check-db; then
  ok "the database matches this revision"
else
  warn "the database does NOT match this revision."
  warn "If the schema moved forward, the new columns are still there and this older"
  warn "code simply ignores them — that is usually harmless. To undo the migration:"
  warn "    $PYTHON -m flask db downgrade -1"
  warn "Read the migration file first. A downgrade drops the column's DATA, and"
  warn "alwaysdata's own daily backups (3 days) are the way back from one you regret."
fi

say "Rendering every page"
"$PYTHON" -m flask render-check --all \
  || die "this revision does not render. Check out the revision you came from and try again."

touch wsgi.py
say "Rolled back to $(git rev-parse --short HEAD) (detached HEAD)"
warn "deploy.sh will refuse to run on a detached HEAD — return to the branch first:"
warn "    git checkout main && ./deploy.sh"
