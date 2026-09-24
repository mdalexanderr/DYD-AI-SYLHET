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

import click
from flask import current_app, render_template
from flask.cli import with_appcontext
from sqlalchemy import inspect, text

from app.extensions import db


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
    app.cli.add_command(publish_pages)
    app.cli.add_command(admin_reset_2fa)
    app.cli.add_command(check_db)
    app.cli.add_command(css_status)
    app.cli.add_command(render_check)


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
    if cfg.get("APP_ENV") == "production" and prefix.strip("/") in {
        "", "admin", "login", "panel", "dashboard", "manage", "cms",
    }:
        problems.append(f"ADMIN_URL_PREFIX {prefix!r} is guessable (§12.1).")

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
        columns = {c["name"] for c in inspector.get_columns("participants")}
        leaked = columns & PROHIBITED_PARTICIPANT_COLUMNS
        if leaked:
            problems.append(
                "participants contains PROHIBITED columns (§5.3, S2/S3): "
                + ", ".join(sorted(leaked))
            )
        else:
            _ok("participants contains no prohibited PII columns")

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
