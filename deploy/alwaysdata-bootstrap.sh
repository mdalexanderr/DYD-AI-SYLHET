#!/usr/bin/env bash
# =============================================================================
# alwaysdata-bootstrap.sh — first-boot provisioner for the free plan.
#
# Run by a panel Scheduled task, not by hand:
#
#   curl -fsSL https://raw.githubusercontent.com/mdalexanderr/DYD-AI-SYLHET/main/deploy/alwaysdata-bootstrap.sh \
#     | SECRET_KEY=… DATABASE_URL=… APP_URL=… ALLOWED_HOSTS=… bash
#
# SECRETS COME FROM THE ENVIRONMENT, NEVER FROM THIS FILE.
#   The scheduled task starts with an EMPTY environment (it gets none of the
#   panel's variables), so the task command passes them as `VAR=…` prefixes to
#   the `bash` that runs this script. The app refuses to boot without them, and
#   this script refuses to continue without them — both fail loudly instead of
#   writing a half-configured server.
#
# IDEMPOTENT BY DESIGN.
#   The task may fire more than once before it is deleted. Every step is safe to
#   re-run: clone is skipped when the repository already exists, the virtualenv
#   is recreated in place, pip and the Flask steps are all idempotent.
# =============================================================================

set -euo pipefail

say() { printf '== [bootstrap] %s\n' "$*"; }

: "${SECRET_KEY:?SECRET_KEY is required}"
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${APP_URL:?APP_URL is required}"
: "${ALLOWED_HOSTS:?ALLOWED_HOSTS is required}"

ADMIN_URL_PREFIX="${ADMIN_URL_PREFIX:-ops-sylhet}"
UPLOAD_ROOT="${UPLOAD_ROOT:-$HOME/sylhet-uploads}"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/sylhet-var/backups}"
MAIL_PROVIDER="${MAIL_PROVIDER:-dryrun}"
MAIL_DEFAULT_SENDER="${MAIL_DEFAULT_SENDER:-noreply@mdalexander.alwaysdata.net}"
ADMIN_2FA_REQUIRED="${ADMIN_2FA_REQUIRED:-true}"
TURNSTILE_ENABLED="${TURNSTILE_ENABLED:-false}"

APP_DIR="$HOME/sylhet"
VENV_DIR="$HOME/venv"

say "start $(date -Is)"
say "python: $(python --version 2>&1 || true)"

mkdir -p "$UPLOAD_ROOT" "$BACKUP_ROOT"

if [ -d "$APP_DIR/.git" ]; then
    say "pulling existing clone"
    git -C "$APP_DIR" pull --ff-only
else
    say "cloning repository"
    git clone https://github.com/mdalexanderr/DYD-AI-SYLHET.git "$APP_DIR"
fi

say "creating virtualenv at $VENV_DIR"
python -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
say "installing requirements"
"$VENV_DIR/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

cd "$APP_DIR"

say "writing .env"
umask 077
cat > "$APP_DIR/.env" <<EOF
APP_ENV=production
SECRET_KEY=$SECRET_KEY
DATABASE_URL=$DATABASE_URL
ALLOWED_HOSTS=$ALLOWED_HOSTS
APP_URL=$APP_URL
ADMIN_URL_PREFIX=$ADMIN_URL_PREFIX
TRUST_PROXY_HEADERS=true
UPLOAD_ROOT=$UPLOAD_ROOT
BACKUP_ROOT=$BACKUP_ROOT
MAIL_PROVIDER=$MAIL_PROVIDER
MAIL_DEFAULT_SENDER=$MAIL_DEFAULT_SENDER
ADMIN_2FA_REQUIRED=$ADMIN_2FA_REQUIRED
TURNSTILE_ENABLED=$TURNSTILE_ENABLED
EOF
chmod 600 "$APP_DIR/.env"

say "check-config"
"$VENV_DIR/bin/python" -m flask check-config || true

say "db upgrade"
"$VENV_DIR/bin/python" -m flask db upgrade

say "check-db"
"$VENV_DIR/bin/python" -m flask check-db || true

say "seed"
"$VENV_DIR/bin/python" -m flask seed

say "publish-pages"
"$VENV_DIR/bin/python" -m flask publish-pages

say "seed-programme"
"$VENV_DIR/bin/python" -m flask seed-programme --yes || true

say "BOOTSTRAP_OK $(date -Is)"
