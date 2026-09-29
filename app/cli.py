"""Flask CLI commands. execution-plan steps 2.5, 2.9, 2.13, 2.15 and §11.1.

``app/__init__.py`` imports ``register_cli`` at the end of ``create_app()``, so
this module is on the import path for every command including ``flask run``. It
must therefore import nothing that only exists at runtime (no app context at
import time) and must not import ``app`` itself — that would be a cycle.

Every command is written to be safe to run twice, and the destructive ones say so
and require an explicit flag. On a live government site the expensive mistake is
not a command that refuses to run; it is one that runs when it was not meant to.
"""

from __future__ import annotations

import json
import sys

import click
from flask import current_app, render_template
from flask.cli import with_appcontext
from sqlalchemy import inspect, text

from app.extensions import db


# ── Output encoding, before anything prints ──────────────────────────────────
# These commands draw with box characters and print Bangla, and on Windows the
# console is cp1252 by default: `flask check-config` crashed with
# UnicodeEncodeError *inside click.echo* before printing a single finding, which
# makes every command here look broken on the machine a developer is sitting at.
#
# `errors="replace"` rather than raising, for the same reason the tools/ scripts
# do it: a mojibake box character is a cosmetic problem, and a command that dies
# halfway through the seeding it was doing is not. Redirected output — a pipe, a
# log file — has no `reconfigure`, hence the guard.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _out(message: str = "") -> None:
    click.echo(message)


def _ok(message: str) -> None:
    click.secho(f"  OK   {message}", fg="green")


def _warn(message: str) -> None:
    click.secho(f"  WARN {message}", fg="yellow")


def _fail(message: str) -> None:
    click.secho(f"  FAIL {message}", fg="red")


def register_cli(app) -> None:
    app.cli.add_command(check_config)
    app.cli.add_command(seed)
    app.cli.add_command(create_admin)
    app.cli.add_command(seed_demo_participants)
    app.cli.add_command(seed_programme)
    app.cli.add_command(clear_people)
    app.cli.add_command(publish_pages)
    app.cli.add_command(admin_reset_2fa)
    app.cli.add_command(check_db)
    app.cli.add_command(css_status)
    app.cli.add_command(render_check)
    app.cli.add_command(backup)


# ─────────────────────────────────────────────────────────────────────────────
@click.command("check-config")
@with_appcontext
def check_config() -> None:
    """Print the effective configuration and fail on anything unsafe.

    Step 2.9. Run this before a deploy: it reports what the app actually resolved,
    not what .env was intended to say, which is the difference that matters when
    Passenger does not load the file you think it loaded.
    """
    cfg = current_app.config
    problems: list[str] = []

    _out()
    _out("  Configuration")
    _out("  " + "─" * 58)
    for key in (
        "APP_ENV", "APP_NAME", "APP_URL", "FLASK_ENV",
        "DEBUG", "TESTING", "SERVER_NAME", "PREFERRED_URL_SCHEME",
    ):
        _out(f"  {key:<28} {cfg.get(key)!r}")

    db_url = str(cfg.get("SQLALCHEMY_DATABASE_URL") or cfg.get("SQLALCHEMY_DATABASE_URI") or "")
    safe_db = db_url
    if "@" in safe_db:
        scheme, _, rest = safe_db.partition("://")
        safe_db = f"{scheme}://***@{rest.rpartition('@')[2]}"
    _out(f"  {'DATABASE_URL':<28} {safe_db or '(unset)'}")

    for key in (
        "ADMIN_URL_PREFIX", "UPLOAD_ROOT", "SESSION_COOKIE_SECURE",
        "SESSION_COOKIE_HTTPONLY", "SESSION_COOKIE_SAMESITE",
        "WTF_CSRF_ENABLED", "RATELIMIT_ENABLED", "RATELIMIT_HEADERS_ENABLED",
        "MAIL_SUPPRESS_SEND", "TWOFA_REQUIRED",
    ):
        _out(f"  {key:<28} {cfg.get(key)!r}")

    hosts = cfg.get("ALLOWED_HOSTS") or []
    _out(f"  {'ALLOWED_HOSTS':<28} {', '.join(hosts) if hosts else '(unset)'}")

    secret = cfg.get("SECRET_KEY") or ""
    _out(f"  {'SECRET_KEY':<28} {'set, ' + str(len(secret)) + ' chars' if secret else '(unset)'}")

    _out()

    # ── The checks that matter. Mirrors ProdConfig.validate() so that a dev or
    # test run can be inspected with the same rules rather than a weaker set.
    if not secret:
        problems.append("SECRET_KEY is empty — sessions and CSRF tokens are forgeable.")
    elif len(secret) < 32:
        problems.append(f"SECRET_KEY is {len(secret)} chars; 32+ is required.")

    if not db_url:
        problems.append("no database URL is configured.")
    elif db_url.startswith("sqlite") and cfg.get("APP_ENV") == "production":
        problems.append("production is pointed at SQLite; MySQL with utf8mb4 is required.")
    elif db_url.startswith("mysql") and "utf8mb4" not in db_url:
        problems.append(
            "MySQL DSN has no utf8mb4 charset — Bangla text will be corrupted or "
            "rejected (§10.1, R7)."
        )
    elif db_url.startswith("mysql") and "charset=utf8mb4" not in db_url:
        problems.append("MySQL DSN sets utf8mb4 but not 'charset=utf8mb4' explicitly.")

    if not hosts and cfg.get("APP_ENV") == "production":
        problems.append("ALLOWED_HOSTS is empty in production — Host header is not validated.")

    app_url = cfg.get("APP_URL") or ""
    if cfg.get("APP_ENV") == "production":
        if app_url.startswith("http://"):
            problems.append("APP_URL is http:// in production.")
        if not app_url:
            problems.append("APP_URL is empty in production.")

    prefix = cfg.get("ADMIN_URL_PREFIX") or ""
    if cfg.get("APP_ENV") == "production" and not prefix.strip("/"):
        problems.append("ADMIN_URL_PREFIX is empty in production.")
    elif prefix.strip("/") in {"admin", "administrator", "login", "panel", "cms"}:
        # A WARNING, NOT A PROBLEM. §12.1 asks for a non-guessable prefix and this
        # deploy has chosen a readable one; the decision is the owner's, and a check
        # that refuses to pass on a configuration somebody deliberately chose is a
        # check that gets bypassed. It still says so, every time.
        _warn(
            f"ADMIN_URL_PREFIX {prefix!r} is guessable (§12.1). The account, the "
            "lockout and the audit trail are what protect the CMS; the path only "
            "hides it."
        )

    # 2FA OFF IS SAID OUT LOUD, IN PRODUCTION, EVERY TIME.
    # `ADMIN_2FA_REQUIRED=false` is the owner's instruction, so it is not a problem to
    # be fixed — but "the password is the only thing in front of participant data" is
    # not something to discover later from a plan document. The password stays out of
    # this message; the state does not.
    if not cfg.get("ADMIN_2FA_REQUIRED", True) and cfg.get("APP_ENV") == "production":
        _warn(
            "ADMIN_2FA_REQUIRED is false in production (§12.1 wants TOTP before "
            "go-live). The admin password is the only credential in front of the "
            "participant data. Re-enable with ADMIN_2FA_REQUIRED=true plus "
            "`flask admin-reset-2fa <email>`."
        )

    if not cfg.get("WTF_CSRF_ENABLED", True) and cfg.get("APP_ENV") == "production":
        problems.append("CSRF protection is disabled in production.")

    if not cfg.get("SESSION_COOKIE_SECURE", False) and cfg.get("APP_ENV") == "production":
        problems.append("SESSION_COOKIE_SECURE is off in production.")

    if problems:
        for problem in problems:
            _fail(problem)
        _out()
        raise SystemExit(1)

    _ok("configuration is safe for this environment")

    # Report the two-way check that the models are all importable, because a
    # missing model is a table that silently never gets created.
    from app.models import EXPECTED_TABLES

    missing = EXPECTED_TABLES - set(db.metadata.tables)
    if missing:
        _fail(f"models not registered: {', '.join(sorted(missing))}")
        raise SystemExit(1)
    _ok(f"all {len(EXPECTED_TABLES)} models are registered")
    _out()


# ─────────────────────────────────────────────────────────────────────────────
@click.command("seed")
@click.option("--admin-email", default=None,
              help="Also create/refresh the admin account (requires --admin-password).")
@click.option("--admin-password", default=None,
              help="Password for --admin-email. Prefer the interactive prompt.")
@click.option("--no-2fa", is_flag=True, default=False,
              help="Skip TOTP enrolment. Only for a throwaway local database.")
@with_appcontext
def seed(admin_email: str | None, admin_password: str | None, no_2fa: bool) -> None:
    """Load §10.6 reference data. Idempotent — running it twice changes nothing.

    Step 2.13. Does NOT create participants: real names enter through the consent
    import with consent recorded per person (§11.4). Seeding invented names onto a
    government site is a consent incident, not a fixture.
    """
    from app.seeds import seed_admin, seed_reference_data

    _out()
    counts = seed_reference_data()
    _ok(f"institutions: {counts['institutions']}")
    _ok(f"courses: {counts['courses']} (+{counts['course_modules']} modules)")
    _ok(f"stats: {counts['stats']}")
    _ok(f"faqs: {counts['faqs']}")
    _ok(f"settings: {counts['settings']}")
    _ok(f"pages: {counts['pages']} (+{counts['page_sections']} sections)")
    _warn("seeded pages are DRAFTS — publish them deliberately in the admin")

    if admin_email:
        if not admin_password:
            admin_password = click.prompt(
                f"Password for {admin_email}", hide_input=True, confirmation_prompt=True
            )
        result = seed_admin(
            admin_email, admin_password,
            enable_2fa=not no_2fa,
            secret_key=current_app.config["SECRET_KEY"],
        )
        _ok(f"admin {admin_email} {'created' if result['created'] else 'updated'}")
        if result["recovery_codes"]:
            _out()
            _out("  Two-factor authentication is ON. Scan this with an authenticator app:")
            _out()
            _out(f"    {result['provisioning_uri']}")
            _out()
            _out("  Recovery codes — shown ONCE, stored hashed, cannot be read back:")
            for code in result["recovery_codes"]:
                _out(f"    {code}")
            _out()
            click.secho(
                "  Write these down now and store them offline.", fg="yellow", bold=True
            )
    _out()


# ─────────────────────────────────────────────────────────────────────────────
@click.command("create-admin")
@click.argument("email")
@click.option("--password", default=None, help="Omit to be prompted (recommended).")
@click.option("--no-2fa", is_flag=True, default=False)
@with_appcontext
def create_admin(email: str, password: str | None, no_2fa: bool) -> None:
    """Create or reset the single admin account (§12.1).

    There is no role argument. §3.3 and S1: exactly one administrator, therefore
    no role column and no permission model to get wrong.
    """
    from app.seeds import seed_admin

    if not password:
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)

    # Deliberately duplicated from ProdConfig.validate() rather than imported:
    # this is the last gate before a weak password is written to a live database.
    if len(password) < 12:
        raise click.BadParameter("password must be at least 12 characters")
    if password.lower() in {"password", "admin", "administrator", "123456789012"}:
        raise click.BadParameter("that password is on every wordlist")

    result = seed_admin(
        email, password,
        enable_2fa=not no_2fa,
        secret_key=current_app.config["SECRET_KEY"],
    )
    _ok(f"admin {email} {'created' if result['created'] else 'updated'}")

    if result["recovery_codes"]:
        _out()
        _out(f"  TOTP secret: {result['totp_secret']}")
        _out(f"  Otpauth URI: {result['provisioning_uri']}")
        _out()
        _out("  Recovery codes — shown ONCE:")
        for code in result["recovery_codes"]:
            _out(f"    {code}")
        _out()
        click.secho("  Store these offline. They cannot be shown again.", fg="yellow", bold=True)
    elif no_2fa:
        _warn("2FA is OFF. §12.1 requires it before go-live.")
    _out()


# ─────────────────────────────────────────────────────────────────────────────
@click.command("admin-reset-2fa")
@click.argument("email")
@with_appcontext
def admin_reset_2fa(email: str) -> None:
    """Re-enrol TOTP for an admin who has lost their authenticator.

    Named by ``app/security/crypto.py``'s SecretDecryptionError message, so the
    error the operator sees and the command that fixes it match.
    """
    import pyotp
    from sqlalchemy import select

    from app.models import AdminUser
    from app.security.crypto import encrypt_secret, generate_recovery_codes, hash_recovery_code

    admin = db.session.execute(
        select(AdminUser).where(AdminUser.email == email)
    ).scalar_one_or_none()
    if admin is None:
        raise click.ClickException(f"no admin with email {email}")

    secret = pyotp.random_base32()
    admin.twofa_secret = encrypt_secret(secret, current_app.config["SECRET_KEY"])
    admin.twofa_enabled = True
    codes = generate_recovery_codes()
    admin.recovery_codes = json.dumps([hash_recovery_code(c) for c in codes])
    db.session.commit()

    _ok(f"2FA re-enrolled for {email}")
    _out()
    _out(f"  Otpauth URI: {pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name='DYD AI Sylhet')}")
    _out()
    _out("  New recovery codes — shown ONCE:")
    for code in codes:
        _out(f"    {code}")
    _out()


# ─────────────────────────────────────────────────────────────────────────────
@click.command("seed-demo-participants")
@click.option("--count", default=120, show_default=True)
@click.option("--consent-rate", default=0.8, show_default=True)
@click.option("--batch", default=1, show_default=True)
@click.option("--yes", is_flag=True, default=False, help="Skip the confirmation prompt.")
@with_appcontext
def seed_demo_participants(count: int, consent_rate: float, batch: int, yes: bool) -> None:
    """WARNING: invented people. Development only.

    Step 2.15. Generates every consent state — consented, not consented,
    withdrawn, consenting with a missing date, a 2-person outcome bucket and
    zero-outcome records — because §8.2's point is that the consent rules cannot
    be verified against happy-path rows only.
    """
    from app.seeds import participant_counts, seed_demo_participants as _seed

    if current_app.config["APP_ENV"] == "production":
        raise click.ClickException(
            "refusing to run in production: these are INVENTED names and a public "
            "government site must never show one (§5.3, R4)"
        )

    if not yes:
        click.confirm(
            f"Insert ~{count} INVENTED participants into "
            f"{current_app.config.get('SQLALCHEMY_DATABASE_URL', '?')}?",
            abort=True,
        )

    created = _seed(count=count, consent_rate=consent_rate, batch=batch)
    _out()
    for key, value in created.items():
        _out(f"  {key:<18} {value}")
    _out()
    _out("  Totals now in the database:")
    for key, value in participant_counts().items():
        _out(f"  {key:<24} {value}")
    _out()


# ─────────────────────────────────────────────────────────────────────────────
@click.command("seed-programme")
@click.option("--yes", is_flag=True, default=False, help="Skip the confirmation prompt.")
@click.option(
    "--with-people",
    is_flag=True,
    default=False,
    help="ALSO load the invented register and trainers. Demo databases only.",
)
@click.option(
    "--unpublished",
    is_flag=True,
    default=False,
    help="With --with-people: load the register without publishing it.",
)
@with_appcontext
def seed_programme(yes: bool, with_people: bool, unpublished: bool) -> None:
    """Load the programme's reference content: phases, tools, modules, works, stats.

    The 13 modules, 3 phases, 11 tools, 5 works and 4 statistics were constants in
    `frontend/src/data/mockData.ts`, which is why the CMS could not reach them. This
    moves them into the tables the admin edits.

    THE PEOPLE ARE SEPARATE, AND OPT-IN
        The same file also holds 25 invented participants and 3 invented trainers.
        They are NOT loaded unless `--with-people` is passed, because the real cohort
        arrives through the consent import (§11.4) and the real trainers are typed into
        the CMS — and a seeder that re-inserted fictional names on every run would put
        them back on a live site the first time somebody refreshed a course module. The
        same flag refuses in production for the same reason (§5.3, R4).
    """
    import json

    from app.seeds.programme import DATA_FILE, seed_programme_content

    if with_people and current_app.config["APP_ENV"] == "production":
        raise click.ClickException(
            "refusing --with-people in production: the register in this file is "
            "INVENTED names, and a public government site must never show one "
            "(§5.3, R4). Content alone is fine: drop the flag."
        )

    if not DATA_FILE.is_file():
        raise click.ClickException(f"{DATA_FILE} is missing")

    if not yes:
        what = "the reference content AND the invented register" if with_people else "the reference content"
        click.confirm(
            f"Load {what} from {DATA_FILE.name} into "
            f"{current_app.config.get('SQLALCHEMY_DATABASE_URI', '?')}?",
            abort=True,
        )

    payload = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    counts = seed_programme_content(payload, people=with_people, publish=not unpublished)

    _out()
    for key, value in counts.items():
        if key in {"participants", "instructors"} and not with_people:
            continue
        _ok(f"{key}: {value}")
    if not with_people:
        _warn(
            "the register and the trainers were NOT loaded — those are invented "
            "people. Import the real cohort, or pass --with-people for a demo."
        )
    elif unpublished:
        _warn("the register was loaded UNPUBLISHED — publish each name deliberately")
    else:
        _warn("the seeded register is published: these are invented people (§5.3, R4)")
    _out()


# ─────────────────────────────────────────────────────────────────────────────
@click.command("clear-people")
@click.option("--yes", is_flag=True, default=False, help="Skip the confirmation prompt.")
@click.option(
    "--keep-media",
    is_flag=True,
    default=False,
    help="Delete the media ROWS but leave the files on disk.",
)
@with_appcontext
def clear_people(yes: bool, keep_media: bool) -> None:
    """Remove every participant, trainer and media item — and NOTHING else.

    WHAT IT IS FOR
        A database that has been seeded with invented people cannot be handed to the
        programme office, and it cannot be topped up with real people either: the two
        would be indistinguishable in the register. Emptying those three tables is the
        step between "demo data" and "the real cohort", and it has to be a command with
        a name rather than four hand-written DELETEs, because the second one is how a
        course module gets deleted by accident.

    WHAT IT DELETES
        participants   — every row, and with it every consent_event (ON DELETE CASCADE)
        instructors    — every row
        media_items    — every row, plus the files themselves under UPLOAD_ROOT

    WHAT IT LEAVES ALONE, DELIBERATELY
        course_phases, training_tools, course_modules, batch_works, stats, pages,
        faqs, settings, institutions, the admin account and the audit log. The syllabus
        is real content that somebody has to type in; the people are the part that is
        being replaced. `--keep-media` narrows the delete to the rows for an operator
        who wants to review the files before they go.

    IT DOES NOT RUN IN PRODUCTION WITHOUT SAYING SO
        There is no `--force`. The confirmation prompt names the database, and on a
        live site the command still stops and asks — deleting the register is a
        deliberate act on every environment, not only the risky one.
    """
    from app.models import Instructor, MediaItem, Participant

    cfg = current_app.config
    counts = {
        "participants": db.session.query(Participant).count(),
        "consent_events": _count_rows("consent_events"),
        "instructors": db.session.query(Instructor).count(),
        "media_items": db.session.query(MediaItem).count(),
    }

    _out()
    _out(f"  Database: {cfg.get('SQLALCHEMY_DATABASE_URI', '?')}")
    _out(f"  Uploads:  {cfg.get('UPLOAD_ROOT', '(unset)')}")
    _out()
    for key, value in counts.items():
        _out(f"  {key:<16} {value:,}")
    _out()

    if not any(counts[k] for k in ("participants", "instructors", "media_items")):
        _ok("nothing to remove — the register, the trainers and the media are empty")
        _out()
        return

    if not yes:
        click.confirm(
            "DELETE all of the above? Course modules, phases, tools, works, stats and "
            "pages are NOT touched.",
            abort=True,
        )

    # ORM deletes rather than a bulk DELETE: the consent events hang off each
    # participant with `delete-orphan`, so the cascade is a Python-level decision here,
    # and the audit trail is written per row.
    for participant in db.session.execute(db.select(Participant)).scalars():
        db.session.delete(participant)
    for trainer in db.session.execute(db.select(Instructor)).scalars():
        db.session.delete(trainer)

    # THE DANGLING IDS ARE CLEARED BY HAND, DELIBERATELY.
    # FOUR COLUMNS POINT AT A MEDIA ROW, and every one of them is cleared by hand
    # rather than left to the database: `Page.og_image_id`, `Institution.logo_id`,
    # `BatchWork.media_id` and `Instructor.photo_id`, all declared
    # ON DELETE SET NULL. MySQL honours that; SQLite only honours it when
    # `PRAGMA foreign_keys` is on, and it is off by default. A suppressed integrity
    # error would be bad; a page that 500s because its share image points at a deleted
    # row is worse, and it would happen only on a developer's machine, which is the
    # worst place for a difference to live.
    from app.models import BatchWork, Institution, Page, Participant

    for model, column in (
        (Page, Page.og_image_id),
        (Institution, Institution.logo_id),
        (BatchWork, BatchWork.media_id),
        (Instructor, Instructor.photo_id),
        # A participant's photograph, from the portrait feature. Clearing the media rows
        # without clearing this would leave a face pointing at a file that is gone.
        (Participant, Participant.photo_id),
    ):
        updated = db.session.execute(
            db.update(model).values({column: None}).where(column.is_not(None))
        ).rowcount
        if updated:
            _ok(f"{model.__tablename__}.{column.key}: {updated} reference(s) cleared")

    media = list(db.session.execute(db.select(MediaItem)).scalars())
    for item in media:
        db.session.delete(item)

    db.session.commit()
    _ok(f"participants: {counts['participants']:,} deleted (with their consent events)")
    _ok(f"instructors: {counts['instructors']:,} deleted")
    _ok(f"media_items: {counts['media_items']:,} deleted")

    if not keep_media and media:
        removed = _remove_media_files(media)
        _ok(f"media files: {removed:,} removed from disk")

    _out()
    _warn(
        "the register is now EMPTY. Add the real participants at /admin/participants "
        "→ Import (CSV, consent per person), and the real trainers at "
        "/admin/instructors."
    )
    _out()


def _count_rows(table: str) -> int:
    """Row count for a table by name — used only for the report before a delete."""
    try:
        return int(db.session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
    except Exception:  # pragma: no cover - a missing table only changes a number
        return 0


def _remove_media_files(items: list) -> int:
    """Delete the files behind media rows, and count what actually went.

    ASSEMBLED FROM THE ROW, NOT FROM THE URL
        `MediaItem.path` is relative to `UPLOAD_ROOT`; `original_name` is the browser's
        filename and is never a path. Both are resolved against the root and checked
        before anything is unlinked, because a delete that trusts a stored string is a
        delete that can be pointed at a file outside the media directory.

        A MISSING FILE IS NOT AN ERROR. The row is the record; a file already removed
        by hand, or lost in a restore, is skipped rather than aborting a half-finished
        clear.
    """
    import os
    from pathlib import Path

    raw_root = current_app.config.get("UPLOAD_ROOT")
    if not raw_root:
        return 0
    root = Path(raw_root).resolve()

    removed = 0
    for item in items:
        stored = getattr(item, "path", None)
        if not stored:
            continue
        try:
            resolved = (root / str(stored)).resolve()
            # Refuse to follow a path that escapes UPLOAD_ROOT, however it got there.
            # `Path.parents` rather than a string prefix: `C:/uploads-evil` starts with
            # the same characters as `C:/uploads` and is not inside it.
            if root != resolved and root not in resolved.parents:
                _warn(f"skipped {stored!r}: outside the upload root")
                continue
            if resolved.is_file():
                os.remove(resolved)
                removed += 1
        except OSError:
            continue
    return removed



# ─────────────────────────────────────────────────────────────────────────────
@click.command("publish-pages")
@click.option("--slug", default=None, help="Publish one page by slug (default: all of them).")
@with_appcontext
def publish_pages(slug: str | None) -> None:
    """Publish seeded pages so the public site can be reviewed (step 3.5).

    THE SEEDER LEAVES EVERY PAGE UNPUBLISHED, ON PURPOSE
        A half-written page going live on the first deploy is what the draft state
        exists to prevent (§11.2), so `seed` writes `is_published = False` and an
        editor publishes deliberately. That default is correct — and it is also why
        this command exists. Reviewing the public site, or running the Phase 3 exit
        gate, needs the pages live, and GETTING them live should be a deliberate act
        with a name rather than a side effect of seeding.

    IT RESPECTS `can_publish`
        That gate refuses a page with no visible sections, or one whose sections fail
        their schema. A command that bypassed it would be a supported way to publish
        exactly the broken page the gate exists to stop, so it is checked per page and
        the run reports which page was refused and why.
    """
    from sqlalchemy import select

    from app.extensions import db
    from app.models import Page

    stmt = select(Page).order_by(Page.sort_order, Page.id)
    if slug:
        stmt = stmt.where(Page.slug == slug)
    pages = list(db.session.execute(stmt).scalars())

    if not pages:
        _out()
        _fail(f"no page matched {slug!r}" if slug else "no pages found — run `flask seed` first")
        _out()
        raise SystemExit(1)

    _out()
    published = 0
    refused = 0
    for page in pages:
        ok, reason = page.can_publish
        if not ok:
            _warn(f"{page.slug:<10} refused — {reason}")
            refused += 1
            continue
        page.publish()
        _ok(f"{page.slug:<10} published")
        published += 1

    db.session.commit()
    _out()
    _out(f"  {published} published, {refused} refused")
    _out()
    if refused:
        _fail("at least one page was refused — fix its sections and run again")
        raise SystemExit(1)


# ─────────────────────────────────────────────────────────────────────────────
@click.command("check-db")
@with_appcontext
def check_db() -> None:
    """Assert the schema is what plan.md describes. Step 2.17.

    This is the command that would have caught a model whose ``__tablename__``
    differs from §10.3, or a prohibited PII column added by hand during a
    migration — everything the static checks cannot see.
    """
    from app.models import EXPECTED_TABLES, PROHIBITED_PARTICIPANT_COLUMNS

    problems: list[str] = []
    _out()

    inspector = inspect(db.engine)
    actual = set(inspector.get_table_names())

    if "alembic_version" not in actual:
        _warn("no alembic_version table — migrations have not been applied")

    missing = EXPECTED_TABLES - actual
    extra = actual - EXPECTED_TABLES - {"alembic_version", "sqlite_sequence"}
    if missing:
        problems.append(f"missing tables: {', '.join(sorted(missing))}")
    else:
        _ok(f"all {len(EXPECTED_TABLES)} expected tables exist")
    if extra:
        _warn(f"tables not in the plan: {', '.join(sorted(extra))}")

    if "participants" in actual:
        from app.models import CONSENTED_PARTICIPANT_COLUMNS

        columns = {c["name"] for c in inspector.get_columns("participants")}
        leaked = columns & PROHIBITED_PARTICIPANT_COLUMNS
        if leaked:
            problems.append(
                "participants contains PROHIBITED columns (§5.3, S2/S3): "
                + ", ".join(sorted(leaked))
            )
        else:
            _ok("participants contains no prohibited PII columns")

        # THE ONE AMENDMENT, CHECKED AS A PAIR. `photo_id` is allowed — the office
        # asked for portraits — and ONLY with the column that records the permission for
        # one. A `photo_id` with no `image_consent` beside it is a face on a public site
        # with nothing saying its subject agreed, so the exception cannot outlive the
        # permission it depends on.
        for column, authority in CONSENTED_PARTICIPANT_COLUMNS.items():
            if column not in columns:
                continue
            if authority not in columns:
                problems.append(
                    f"participants.{column} exists without {authority} — §5.1's amendment "
                    "is only valid while the permission column sits beside it."
                )
            else:
                _ok(f"{column} is paired with {authority}")

        # The publish guard must exist as a real database constraint, not only as
        # Python. §5.3 requires defence in the form, the model AND the database,
        # because the CSV import and a future script bypass the first two.
        ddl = _table_ddl("participants")
        if "ck_participants_publish_requires_consent" not in ddl:
            problems.append(
                "the publish-requires-consent CHECK constraint is MISSING. "
                "is_published=1 with consent_publication=0 is currently insertable."
            )
        else:
            _ok("publish-requires-consent CHECK constraint is present")

        # Prove it, rather than trusting the DDL text. An INSERT that must fail.
        if not _probe_publish_guard():
            problems.append(
                "the CHECK constraint exists but did NOT reject an unconsented "
                "publish. Do not trust the schema until this passes."
            )
        else:
            _ok("CHECK constraint provably rejected an unconsented publish")

        # AND THE SAME PROOF FOR THE PORTRAIT, because this one guards a face rather
        # than a name: a photograph stored without `image_consent` must be refused by
        # the database, not only by the form that usually supplies it.
        if "photo_id" in columns:
            if "ck_participants_photo_requires_consent" not in ddl:
                problems.append(
                    "the photo-requires-consent CHECK constraint is MISSING. "
                    "photo_id with image_consent=0 is currently insertable."
                )
            else:
                _ok("photo-requires-consent CHECK constraint is present")
                probed = _probe_photo_guard()
                if probed is False:
                    problems.append(
                        "the photo CHECK constraint exists but did NOT reject a portrait "
                        "without its permission. Do not trust the schema until this passes."
                    )
                elif probed is None:
                    _warn(
                        "no image has been uploaded yet, so the photo guard could not be "
                        "probed with an INSERT — the constraint is present but unproven"
                    )
                else:
                    _ok("photo-requires-consent CHECK constraint provably rejected a portrait")

    _out()
    if problems:
        for problem in problems:
            _fail(problem)
        _out()
        raise SystemExit(1)
    _ok("database matches plan.md")
    _out()


def _table_ddl(table: str) -> str:
    """The CREATE statement for a table, or '' where the engine cannot supply it."""
    try:
        rows = db.session.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": table},
        ).fetchall()
        if rows:
            return "\n".join(str(r[0]) for r in rows)
    except Exception:  # noqa: BLE001 — not SQLite; fall through to information_schema
        db.session.rollback()

    try:
        row = db.session.execute(
            text("SELECT CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS "
                 "WHERE CONSTRAINT_NAME = :name"),
            {"name": "ck_participants_publish_requires_consent"},
        ).fetchone()
        return str(row[0]) if row else ""
    except Exception:  # noqa: BLE001
        db.session.rollback()
        return ""


def _probe_publish_guard() -> bool:
    """Insert a non-consented published row in a savepoint and require failure.

    Returns True when the database REFUSED it. Rolls back either way, so the probe
    is safe to run against a database with real data in it.
    """
    statements = [
        "INSERT INTO participants "
        "(slug, name_bn, is_published, consent_publication, created_at, updated_at, "
        " search_blob) "
        "VALUES ('__guard_probe__', 'পরীক্ষা', 1, 0, CURRENT_TIMESTAMP, "
        " CURRENT_TIMESTAMP, '')",
    ]
    for statement in statements:
        try:
            with db.session.begin_nested():
                db.session.execute(text(statement))
        except Exception:  # noqa: BLE001 — the refusal is the desired outcome
            db.session.rollback()
            return True
        else:
            db.session.rollback()
            return False
    return False


def _probe_photo_guard() -> bool:
    """Insert a portrait without its permission and require the database to refuse.

    THE PROBE POINTS AT A MEDIA ROW, so it can only run once something has been
    uploaded. It returns None in that case — "not probed" — rather than True, because a
    tick printed for a probe that never ran is worse than no line at all.
    """
    try:
        media_id = db.session.execute(text("SELECT id FROM media_items LIMIT 1")).scalar()
    except Exception:  # noqa: BLE001 — no media table at all means no portrait either
        return True
    if media_id is None:
        # Nothing uploaded yet, so there is no id to point at. Report that honestly
        # rather than printing a tick for a probe that never ran.
        return None

    statement = (
        "INSERT INTO participants "
        "(slug, name_bn, photo_id, image_consent, created_at, updated_at, search_blob) "
        f"VALUES ('__photo_probe__', 'পরীক্ষা', {int(media_id)}, 0, CURRENT_TIMESTAMP, "
        " CURRENT_TIMESTAMP, '')"
    )
    try:
        with db.session.begin_nested():
            db.session.execute(text(statement))
    except Exception:  # noqa: BLE001 — the refusal is the desired outcome
        db.session.rollback()
        return True
    else:
        db.session.rollback()
        return False


# ─────────────────────────────────────────────────────────────────────────────
@click.command("backup")
@click.option("--keep-days", default=30, show_default=True,
              help="How long an archive is kept before the sweep removes it.")
@click.option("--skip-uploads", is_flag=True, default=False,
              help="Database only. For a large uploads directory on a cron run that must be quick.")
@with_appcontext
def backup(keep_days: int, skip_uploads: bool) -> None:
    """Dump the database and the uploads directory, and record both (§17.5).

    WHY THIS IS A COMMAND AND NOT A SHELL SCRIPT
        A shell script would need the database password, which means reading it out
        of `.env` with grep and putting it on a command line where `ps` can see it.
        Here the DSN is already parsed by the application, and the password is handed
        to the dump tool through `MYSQL_PWD` — an environment variable, which is the
        one channel that does not appear in a process list.

    IT RECORDS WHAT IT DID, INCLUDING A FAILURE
        `Backup` rows are what `/admin/backups` shows. A backup that failed silently
        in a cron log is indistinguishable from one that never ran, and the screen
        exists to make that difference visible — so a failure writes a row with its
        error before the command exits non-zero.

    RETENTION LIVES HERE TOO, keyed on `expires_at`. Pruning in the shell script
    would let a file and its row disagree about whether the archive still exists.
    """
    import gzip
    import os
    import shutil
    import subprocess
    from datetime import timedelta
    from pathlib import Path
    from app import _safe_database_label
    from app.constants import BackupKind, BackupStatus
    from app.models import Backup
    from app.models.base import utcnow

    stamp = utcnow().strftime("%Y%m%d-%H%M%S")
    root = Path(current_app.config["BACKUP_ROOT"])
    root.mkdir(parents=True, exist_ok=True)

    uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
    label = _safe_database_label(uri)
    _out()
    _out(f"  Backup    {stamp}")
    _out(f"  Database  {label}")
    _out(f"  Into      {root}")
    _out()

    written: list[Path] = []
    failures: list[str] = []

    # ── 1. The database ──────────────────────────────────────────────────────
    dump_path = root / f"db-{stamp}.sql.gz"
    try:
        if uri.startswith("sqlite"):
            _dump_sqlite(uri, dump_path)
        else:
            _dump_mysql(uri, dump_path)
        size = dump_path.stat().st_size
        written.append(dump_path)
        _ok(f"database: {dump_path.name} ({size / 1024:.0f} KB)")
    except Exception as error:  # noqa: BLE001 — the message is the report
        failures.append(f"database: {error}")
        _fail(f"database: {error}")

    # ── 2. The uploads ───────────────────────────────────────────────────────
    # Not in alwaysdata's own backups, and not reproducible: a replaced photograph is
    # gone for good without this.
    upload_root = Path(current_app.config["UPLOAD_ROOT"])
    archive_base = str(root / f"uploads-{stamp}")
    uploads_path = Path(f"{archive_base}.tar.gz")
    if skip_uploads:
        _warn("uploads skipped (--skip-uploads)")
    elif not upload_root.is_dir():
        _warn(f"no uploads directory at {upload_root}; nothing to archive")
    else:
        try:
            # make_archive appends the `.tar.gz` itself, so the base name is what we
            # pass and the finished path is what we look for afterwards.
            shutil.make_archive(archive_base, "gztar", root_dir=upload_root)
            size = uploads_path.stat().st_size
            written.append(uploads_path)
            _ok(f"uploads: {uploads_path.name} ({size / 1024:.0f} KB)")
        except Exception as error:  # noqa: BLE001
            failures.append(f"uploads: {error}")
            _fail(f"uploads: {error}")

    # ── 3. Off-site ──────────────────────────────────────────────────────────
    # A backup on the same disk is a backup of the disk's last good hour, not of the
    # disaster. The command is the operator's — we only report whether it worked.
    offsite_ok = False
    offsite_cmd = current_app.config.get("BACKUP_OFFSITE_CMD") or ""
    if offsite_cmd and written:
        offsite_ok = True
        for path in written:
            try:
                subprocess.run(
                    offsite_cmd.replace("{src}", str(path)),
                    shell=True, check=True, capture_output=True, timeout=600,
                )
            except subprocess.CalledProcessError as error:
                offsite_ok = False
                failures.append(f"offsite: {error.stderr.decode()[:200]}")
                _fail(f"offsite copy of {path.name} failed")
        if offsite_ok:
            _ok("off-site copy sent")
    elif not offsite_cmd:
        _warn("BACKUP_OFFSITE_CMD is not set — this archive is on the same disk as the site")

    # ── 4. Record it, and sweep what has expired ─────────────────────────────
    # Naive UTC, because `Backup.expires_at` is a plain DATETIME and MySQL has no
    # timezone to store — `utcnow()` is aware, so the marker comes off here and the
    # comparison below is naive-to-naive. (See `models/base.utcnow`.)
    now = utcnow().replace(tzinfo=None)
    expires = now + timedelta(days=keep_days)
    for path in written:
        db.session.add(
            Backup(
                kind=BackupKind.UPLOADS if path.name.startswith("uploads") else BackupKind.DATABASE,
                filename=path.name,
                size_bytes=path.stat().st_size,
                status=BackupStatus.OK,
                offsite_ok=offsite_ok,
                expires_at=expires,
            )
        )

    removed = 0
    for row in list(db.session.execute(db.select(Backup)).scalars()):
        if row.expires_at is not None and row.expires_at < now:
            # The FILE first, then the row: a row pointing at a missing archive is a
            # screen that offers a download which 404s.
            try:
                (root / row.filename).unlink(missing_ok=True)
            except OSError as error:  # pragma: no cover — a locked file on Windows
                _warn(f"could not remove {row.filename}: {error}")
            db.session.delete(row)
            removed += 1
    if removed:
        _ok(f"swept {removed} expired archive(s)")

    if failures:
        db.session.add(
            Backup(
                kind=BackupKind.FULL,
                filename=f"failed-{stamp}",
                status=BackupStatus.FAILED,
                error="; ".join(failures)[:2000],
            )
        )

    db.session.commit()
    _out()
    if failures:
        _fail("the backup did not complete — see /admin/backups")
        raise SystemExit(1)
    _ok("backup complete")
    _out()


def _dump_sqlite(uri: str, destination: Path) -> None:
    """A consistent copy of a SQLite database: `VACUUM INTO`, then compress.

    NOT a file copy. SQLite in WAL mode keeps recent commits in a side file, so
    `cp ai_sylhet.db backup.db` can be missing the last transactions — and the
    backups taken by hand are always the ones taken during the day. `VACUUM INTO`
    writes a transactionally consistent database, in one statement, from inside the
    engine that knows the answer.
    """
    import gzip
    import shutil
    import sqlite3
    import tempfile
    from pathlib import Path

    from sqlalchemy.engine import make_url

    path = make_url(uri).database
    if not path or path == ":memory:":
        # An in-memory database has no file and disappears with the process, so
        # there is nothing a backup could contain. Saying so beats writing an
        # archive that restores to an empty schema.
        raise RuntimeError(
            "the database is in memory, so there is no file to snapshot — "
            "point SQLALCHEMY_DATABASE_URI at a file to back it up"
        )
    if not Path(path).is_file():
        raise RuntimeError(f"no database file at {path}")

    # A SEPARATE sqlite3 connection, not the app's: `VACUUM` refuses to run inside a
    # transaction, and the app's session usually has one open.
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "snapshot.db"
        connection = sqlite3.connect(path)
        try:
            connection.execute("VACUUM INTO ?", (str(snapshot),))
        finally:
            connection.close()
        with open(snapshot, "rb") as source, gzip.open(destination, "wb") as target:
            shutil.copyfileobj(source, target, 1024 * 256)


def _dump_mysql(uri: str, destination: Path) -> None:
    """`mariadb-dump`/`mysqldump` streamed into gzip, password in the environment.

    `--single-transaction` so the dump is consistent without locking the tables — a
    dump that locks `participants` for a minute is a minute the CMS cannot record a
    consent. `--no-tablespaces` because the shared host's database user does not have
    the PROCESS privilege, and the dump aborts without it.

    THE STREAM IS COPIED, NOT COLLECTED: `subprocess.run(..., capture_output=True)`
    would hold the whole database in the web user's 256 MB. The database outlives the
    process doing the copying; it does not need to fit in its memory.
    """
    import gzip
    import os
    import shutil
    import subprocess

    from sqlalchemy.engine import make_url

    parsed = make_url(uri)
    binary = shutil.which("mariadb-dump") or shutil.which("mysqldump")
    if binary is None:
        raise RuntimeError(
            "neither mariadb-dump nor mysqldump is on PATH. On alwaysdata both are "
            "available over SSH; without them, take the database backup from the panel."
        )

    environment = dict(os.environ)
    # The password goes through the ENVIRONMENT, never argv: a command line is world-
    # readable through `ps`, and this one can dump every participant record.
    # `make_url` has ALREADY percent-decoded it, which is why a password with `#` or a
    # space belongs in the DSN as `%23` / `%20` — nothing here unquotes it a second
    # time, or `p%2540` would come out as `p@`.
    if parsed.password:
        environment["MYSQL_PWD"] = parsed.password

    command = [
        binary,
        "--host", parsed.host or "localhost",
        "--user", parsed.username or "",
        "--single-transaction",
        "--quick",
        "--no-tablespaces",
        "--default-character-set=utf8mb4",
        parsed.database or "",
    ]
    with open(destination, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb") as compressed:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment
        )
        assert process.stdout is not None and process.stderr is not None
        shutil.copyfileobj(process.stdout, compressed, 1024 * 256)
        process.stdout.close()
        complaint = process.stderr.read().decode(errors="replace").strip()
        process.stderr.close()
        process.wait()

    if process.returncode != 0:
        # No half-written archive left behind pretending to be a backup.
        destination.unlink(missing_ok=True)
        last_line = complaint.splitlines()[-1] if complaint else "dump failed"
        raise RuntimeError(last_line)


# ─────────────────────────────────────────────────────────────────────────────
@click.command("render-check")
@click.option("--all", "render_all", is_flag=True, default=False,
              help="Also render the API and SEO endpoints, not just content pages.")
@click.option("--strict/--no-strict", default=True, show_default=True,
              help="Use Jinja's StrictUndefined so a missing variable fails loudly.")
@with_appcontext
def render_check(render_all: bool, strict: bool) -> None:
    """Render every route and report the ones that fail. Step 2.16.

    WHY THIS EXISTS RATHER THAN JUST pytest
    A template that references a variable nobody passes does not raise under Flask's
    default Jinja `Undefined`: it renders as an EMPTY STRING. The page returns 200,
    the block is blank, and the only way to find it is for a human to read that page
    after it is live. StrictUndefined turns that into an exception at render time,
    which is what makes this check worth running.

    Run before every deploy. It is the cheapest guard against "the homepage is
    missing its statistics" reaching production.
    """
    from jinja2 import StrictUndefined

    app = current_app
    if strict:
        app.jinja_env.undefined = StrictUndefined
        # Templates are cached after first compile, so the cache must be cleared or
        # the flag only applies to templates not yet loaded. `cache` is Optional on
        # the environment (it is disabled when a custom loader supplies one), hence
        # the guard rather than a bare call.
        if app.jinja_env.cache is not None:
            app.jinja_env.cache.clear()

    # Endpoints whose whole job is to return a machine-readable document, not a
    # page. They are rendered too, but only when asked for: a JSON endpoint that
    # fails is a monitoring problem, a missing 404 page is a reader problem.
    machine_endpoints = {"api.health", "seo.robots", "seo.sitemap", "api.manifest"}

    client = app.test_client()
    rules = sorted(
        (
            rule for rule in app.url_map.iter_rules()
            # rule.methods is Optional — a rule created without methods has none.
            if "GET" in (rule.methods or set())
            and rule.rule != "/static/<path:filename>"
        ),
        key=lambda rule: rule.rule,
    )

    failures: list[str] = []
    rendered = 0
    skipped: list[str] = []

    _out()
    _out("  Render check")
    _out("  " + "─" * 58)

    for rule in rules:
        if rule.endpoint in machine_endpoints and not render_all:
            skipped.append(rule.rule)
            continue
        if rule.arguments:
            # A route with a URL variable needs a real record to render. It is
            # reported rather than silently passed, so the count of routes this
            # check does NOT cover is always visible.
            skipped.append(f"{rule.rule} (needs a record)")
            continue

        try:
            response = client.get(rule.rule)
        except Exception as exc:  # noqa: BLE001 — any failure is the finding
            failures.append(f"{rule.rule}: raised {type(exc).__name__}: {exc}")
            _fail(f"{rule.rule:<32} raised {type(exc).__name__}")
            continue

        body = response.get_data(as_text=True)
        status = response.status_code

        # 4xx is acceptable here: this check renders whatever the route does. A 500
        # never is. An HTML-shaped check catches the plain-text fallback that the
        # error handlers use when a template itself is broken — that fallback
        # returns the right status and contains no HTML, so status alone would
        # report a completely broken page as a pass.
        if status >= 500:
            failures.append(f"{rule.rule}: HTTP {status}")
            _fail(f"{rule.rule:<32} HTTP {status}")
            continue
        # The <html> heuristic applies only to endpoints that are supposed to be
        # pages. With --all the machine endpoints are included deliberately, and a
        # JSON body or a text/plain body legitimately contains no <html> element.
        is_page = rule.endpoint not in machine_endpoints
        if (
            is_page
            and "<html" not in body.lower()
            and "text/html" in (response.content_type or "")
        ):
            failures.append(
                f"{rule.rule}: returned HTML content-type but no <html> element — "
                "the template failed and the plain-text fallback was served"
            )
            _fail(f"{rule.rule:<32} HTML content-type but no <html>")
            continue

        rendered += 1
        _ok(f"{rule.rule:<32} {status}  {len(body):>7,} bytes")

    # ── Error pages, rendered DIRECTLY ────────────────────────────────────────
    # Not through the handler: the handlers catch a render failure and fall back to
    # plain text, so a broken error template is completely invisible from the
    # outside. These are also the six templates nobody visits on purpose, which is
    # exactly why they rot first — and they are the ones shown when something else
    # has already gone wrong.
    _out()
    _out("  Error pages (rendered directly)")
    _out("  " + "─" * 58)
    with app.test_request_context("/__render_check__"):
        for name in ("404", "403", "419", "429", "500", "maintenance"):
            template = f"errors/{name}.html"
            try:
                html = render_template(template)
            except Exception as exc:  # noqa: BLE001 — the failure IS the finding
                failures.append(f"{template}: {type(exc).__name__}: {exc}")
                _fail(f"{template:<32} {type(exc).__name__}: {exc}")
                continue
            if "<html" not in html.lower():
                failures.append(f"{template}: rendered without an <html> element")
                _fail(f"{template:<32} no <html>")
                continue
            _ok(f"{template:<32}          {len(html):>7,} bytes")

    _out()
    if skipped:
        for item in skipped:
            _out(f"  skip  {item}")
        _out()

    if failures:
        for item in failures:
            _fail(item)
        _out()
        raise SystemExit(1)

    _ok(f"{rendered} route(s) rendered clean"
        + (" with StrictUndefined" if strict else ""))
    _out()


# ─────────────────────────────────────────────────────────────────────────────
@click.command("css-status")
@with_appcontext
def css_status() -> None:
    """Report the compiled stylesheet's size and whether it is stale (§17.3).

    The gate that matters is not the CSS checker's opinion but this pair of facts:
    how big the file is, and whether the committed build matches the sources.
    """
    from pathlib import Path

    path = Path(current_app.config["APP_CSS_PATH"])
    _out()
    if not path.exists():
        _fail(f"{path} does not exist — run `npm run css:build`")
        raise SystemExit(1)

    raw = path.stat().st_size
    _out(f"  {'file':<20} {path}")
    _out(f"  {'size':<20} {raw:,} bytes ({raw / 1024:.1f} KB)")

    biggest = max((p.stat().st_mtime for p in (Path.cwd() / "assets" / "tailwind").glob("*.css")), default=0)
    if biggest and biggest > path.stat().st_mtime:
        _warn("source.css is NEWER than app.css — the build is stale")
    else:
        _ok("app.css is newer than its sources")

    if raw < 20 * 1024:
        _warn(f"{raw / 1024:.1f} KB is under §17.3's 20 KB floor — "
              "the build may have produced an empty or truncated sheet")
    _out()
