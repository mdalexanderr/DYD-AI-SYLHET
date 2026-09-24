"""Application configuration — Base / Dev / Test / Prod.

plan.md §16.1 (every variable), §9.1 (config.py in the layout).

HOW THIS IS ORGANISED
    One ``BaseConfig`` holds every key the application reads, with a safe value.
    Each environment subclass overrides only what genuinely differs. The result is
    that a missing environment variable in production degrades to a *documented*
    default rather than to ``None`` somewhere in a request — except for the three
    that must never have a default, which raise at startup instead (§2.2:
    "APP_ENV=production with a missing SECRET_KEY refuses to boot").

READING THE ENVIRONMENT
    ``python-dotenv`` loads ``.env`` in development ONLY. In production the
    variables come from the Passenger environment, because a committed-adjacent
    file is a file someone eventually commits (§16.2: secrets are never in the
    database and never in git).

TWO SETTINGS WORTH FINDING
    ``RATELIMIT_HEADERS_ENABLED`` — Flask-Limiter v4 defaults this to False, so
    ``X-RateLimit-*`` headers are absent and §12's limits become invisible to
    clients and untestable in the suite. Verified during Phase 1.
    ``SQLALCHEMY_ENGINE_OPTIONS`` — a stale pooled MySQL connection behind
    Passenger is the classic "site 500s every few hours" bug. ``pool_recycle``
    is deliberately under MySQL's default ``wait_timeout``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy.pool import StaticPool

# Project root: the directory containing app/, tools/, plan.md.
BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"
VAR_DIR = BASE_DIR / "var"

# ── .env is loaded HERE, at import time — not inside get_config() ──────────────
# A config class evaluates its attributes exactly once, when this module is
# imported: `SECRET_KEY = _str("SECRET_KEY", "")` reads os.environ at that moment
# and never again. Loading .env later, inside create_app()/get_config(), is
# therefore TOO LATE, and the classes keep their defaults.
#
# That failure is invisible from the CLI, because `flask run` and
# `flask check-config` work: the Flask CLI loads .env itself before it imports the
# app. The paths it does NOT cover are the ones production uses — `python run.py`
# and passenger_wsgi.py calling create_app() — which silently ignored every value
# in the file, including SECRET_KEY.
#
# override=False, and skipped entirely when APP_ENV is already production, so a
# stray .env on the server cannot override the real environment (§17.2).
if (os.environ.get("APP_ENV") or "").strip().lower() != "production":
    load_dotenv(BASE_DIR / ".env", override=False)


def _raw(name: str) -> str | None:
    """The environment value for `name`, with a comment-only value treated as ABSENT.

    WHY THIS EXISTS — A REAL BUG, FOUND IN THE WILD
        python-dotenv strips an inline comment only when a NON-EMPTY value precedes
        it. The two lines below are both documented forms in `.env.example`, and they
        do not behave the same way:

            ADMIN_URL_PREFIX=ops-sylhet    # MUST stay non-guessable  ->  "ops-sylhet"
            ADMIN_IP_ALLOWLIST=            # empty = off              ->  "# empty = off"

        The second resolved to the COMMENT TEXT. `_csv` then split it on the comma,
        and ADMIN_IP_ALLOWLIST became
            ("# CIDR list", "comma-separated; empty = off.")
        — a truthy allowlist containing no valid entry. Every admin request was then
        denied with a 403 and nothing but a log warning to explain it, on a setting
        whose own documentation says "empty = off".

        A security control that silently switches ITSELF ON is the worst possible
        reading of a missing value.

    ONLY A VALUE THAT BEGINS WITH `#` IS TREATED AS A COMMENT. A value that merely
        CONTAINS one is returned untouched, and that distinction is load-bearing:
        SECRET_KEY, database passwords and a Fernet key can all legitimately contain
        `#`, and truncating one of those would be a far worse bug than this one.
    """
    value = os.environ.get(name)
    if value is None:
        return None
    if value.lstrip().startswith("#"):
        return ""
    return value


def _bool(name: str, default: bool = False) -> bool:
    raw = _raw(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = _raw(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


def _csv(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = _raw(name)
    if not raw:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _str(name: str, default: str = "") -> str:
    value = _raw(name)
    return default if value is None else value


def _database_url() -> str:
    """The database URL, with a relative SQLite path made absolute.

    ``sqlite:///instance/ai_sylhet.db`` is a RELATIVE path, and SQLAlchemy resolves
    it against the process's current working directory — not against the project.
    So the identical value works from ``flask db upgrade`` run in the project root
    and then fails with "unable to open database file" from anywhere else, which is
    how it behaves under Passenger: the app directory is not the cwd.

    MySQL URLs are returned untouched; they have no local path component.
    """
    raw = _str(
        "DATABASE_URL", f"sqlite:///{(INSTANCE_DIR / 'ai_sylhet.db').as_posix()}"
    )

    prefix = "sqlite:///"
    if raw.startswith(prefix):
        path = raw[len(prefix):]
        head = path.split("/", 1)[0]
        # A leading slash, or a Windows drive letter, means it is already absolute.
        already_absolute = path.startswith("/") or (
            len(head) == 2 and head[1] == ":"
        )
        if path and not already_absolute:
            return prefix + (BASE_DIR / path).as_posix()
    return raw


class BaseConfig:
    """Every setting the application reads, with a safe value."""

    @classmethod
    def validate(cls) -> None:
        """Reject a configuration that would be unsafe. Overridden by ProdConfig.

        Declared on the base so `cls.validate()` is always a valid call. Dev and
        Test genuinely have nothing to reject — every permission is loosened for
        them on purpose — but the caller should not have to know which subclasses
        happen to implement this. A config that checks nothing says so, here.
        """


    APP_NAME = _str("APP_NAME", "AI Sylhet")
    APP_ENV = _str("APP_ENV", "development")
    APP_URL = _str("APP_URL", "http://localhost:5000")
    APP_TIMEZONE = _str("APP_TIMEZONE", "Asia/Dhaka")
    SITE_DEFAULT_LOCALE = _str("SITE_DEFAULT_LOCALE", "bn")
    SITE_TAGLINE_BN = _str("SITE_TAGLINE_BN", "যুব উন্নয়ন অধিদপ্তর")
    PREFERRED_URL_SCHEME = _str("PREFERRED_URL_SCHEME", "https")

    # ── Database ─────────────────────────────────────────────────────────────
    # mysql+pymysql with charset=utf8mb4 is mandatory in production; a latin1
    # schema mangles every Bangla string silently (§9.4, R5).
    #
    # _database_url() rather than a bare _str() so a relative SQLite path is
    # anchored to the project instead of to the process's working directory.
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Annotated because the values are genuinely mixed — ints here, and a pool class
    # plus connect_args in TestConfig. Without the annotation mypy infers
    # dict[str, int] from this literal and every subclass assignment fails.
    SQLALCHEMY_ENGINE_OPTIONS: dict[str, Any] = {
        "pool_pre_ping": True,
        "pool_size": _int("DB_POOL_SIZE", 5),
        "max_overflow": 5,
        # Under MySQL's default wait_timeout of 28800s. A connection recycled by
        # the server while Passenger holds it open is the usual cause of a site
        # that 500s every few hours and works again after a restart.
        "pool_recycle": _int("DB_POOL_RECYCLE", 280),
    }

    # ── Session and the single admin account (§12.1) ─────────────────────────
    SECRET_KEY = _str("SECRET_KEY", "")
    SESSION_COOKIE_NAME = _str("SESSION_COOKIE_NAME", "sylhet_ai_session")
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", True)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = _str("SESSION_COOKIE_SAMESITE", "Lax")
    PERMANENT_SESSION_LIFETIME = _int("SESSION_LIFETIME_SECONDS", 28800)
    # §12.1's 30-minute IDLE limit, which Flask cannot express on its own: the cookie's
    # expiry is refreshed by every write to the session, so `PERMANENT_SESSION_LIFETIME`
    # alone gives 8 hours of INACTIVITY, not 8 hours absolute. Both numbers are needed
    # and they mean different things — see `_session_policy` in app/__init__.py.
    SESSION_IDLE_SECONDS = _int("SESSION_IDLE_SECONDS", 1800)
    IDLE_TIMEOUT_SECONDS = _int("IDLE_TIMEOUT_SECONDS", 1800)
    ADMIN_URL_PREFIX = _str("ADMIN_URL_PREFIX", "ops-sylhet")
    ADMIN_IP_ALLOWLIST = _csv("ADMIN_IP_ALLOWLIST")
    ADMIN_2FA_REQUIRED = _bool("ADMIN_2FA_REQUIRED", True)
    BCRYPT_LOG_ROUNDS = _int("BCRYPT_LOG_ROUNDS", 12)
    LOGIN_MAX_ATTEMPTS = _int("LOGIN_MAX_ATTEMPTS", 3)
    LOGIN_LOCKOUT_MINUTES = _int("LOGIN_LOCKOUT_MINUTES", 30)
    ALLOWED_HOSTS = _csv("ALLOWED_HOSTS", ("localhost", "127.0.0.1"))

    # ── Uploads (§13.1, §13.2) ───────────────────────────────────────────────
    # Outside the webroot. Serving uploads from the app directory is how an
    # uploaded file becomes an executable one.
    UPLOAD_ROOT = _str("UPLOAD_ROOT", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = _int("MAX_CONTENT_LENGTH_MB", 6) * 1024 * 1024
    MAX_CONTENT_LENGTH_MB = _int("MAX_CONTENT_LENGTH_MB", 6)
    ALLOWED_UPLOAD_EXTENSIONS = _csv("ALLOWED_UPLOAD_EXTENSIONS",
                                     ("jpg", "jpeg", "png", "webp"))
    IMAGE_MAX_DIMENSION = _int("IMAGE_MAX_DIMENSION", 2000)
    BACKUP_ROOT = _str("BACKUP_ROOT", str(VAR_DIR / "backups"))
    BACKUP_OFFSITE_CMD = _str("BACKUP_OFFSITE_CMD", "")

    # ── Contact form (§12.2) ─────────────────────────────────────────────────
    MAIL_PROVIDER = _str("MAIL_PROVIDER", "dryrun")  # smtp | brevo | dryrun
    MAIL_SERVER = _str("MAIL_SERVER", "")
    MAIL_PORT = _int("MAIL_PORT", 587)
    MAIL_USE_TLS = _bool("MAIL_USE_TLS", True)
    MAIL_USERNAME = _str("MAIL_USERNAME", "")
    MAIL_PASSWORD = _str("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = _str("MAIL_DEFAULT_SENDER", "")
    TURNSTILE_ENABLED = _bool("TURNSTILE_ENABLED", False)
    TURNSTILE_SITE_KEY = _str("TURNSTILE_SITE_KEY", "")
    TURNSTILE_SECRET_KEY = _str("TURNSTILE_SECRET_KEY", "")
    CONTACT_MIN_SECONDS = _int("CONTACT_MIN_SECONDS", 3)
    CONTACT_MAX_PER_HOUR = _int("CONTACT_MAX_PER_HOUR", 3)

    # ── Cache and limits (§15.1, §12) ────────────────────────────────────────
    CACHE_TYPE = _str("CACHE_TYPE", "FileSystemCache")
    CACHE_DIR = _str("CACHE_DIR", str(VAR_DIR / "cache"))
    CACHE_DEFAULT_TIMEOUT = _int("CACHE_DEFAULT_TIMEOUT", 300)
    STATS_CACHE_TIMEOUT = _int("STATS_CACHE_TIMEOUT", 300)
    SITEMAP_CACHE_TIMEOUT = _int("SITEMAP_CACHE_TIMEOUT", 3600)

    RATELIMIT_STORAGE_URI = _str("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = _str("RATELIMIT_DEFAULT", "200/hour")
    # Without this Flask-Limiter v4 emits no X-RateLimit-* headers at all, so the
    # §12 limits are invisible to clients and cannot be asserted in a test.
    RATELIMIT_HEADERS_ENABLED = True

    # ── Participants and statistics (§5.4, §6.4) ─────────────────────────────
    PARTICIPANTS_PER_PAGE = _int("PARTICIPANTS_PER_PAGE", 24)
    ADMIN_ROWS_PER_PAGE = _int("ADMIN_ROWS_PER_PAGE", 50)
    STATS_SUPPRESS_BELOW = _int("STATS_SUPPRESS_BELOW", 5)

    # ── Retention (§12.4, §17.6) ─────────────────────────────────────────────
    RETENTION_MONTHS_MESSAGES = _int("RETENTION_MONTHS_MESSAGES", 12)
    RETENTION_MONTHS_AUDIT = _int("RETENTION_MONTHS_AUDIT", 36)

    # ── Logging (§17.6) ──────────────────────────────────────────────────────
    LOG_LEVEL = _str("LOG_LEVEL", "INFO")
    LOG_DIR = _str("LOG_DIR", str(VAR_DIR / "logs"))
    LOG_MAX_BYTES = _int("LOG_MAX_BYTES", 10 * 1024 * 1024)
    LOG_BACKUP_COUNT = _int("LOG_BACKUP_COUNT", 5)
    ADMIN_ALERT_EMAIL = _str("ADMIN_ALERT_EMAIL", "")

    # ── Presentation ─────────────────────────────────────────────────────────
    MAINTENANCE_MODE = _bool("MAINTENANCE_MODE", False)
    SHOW_BANGLA_NUMERALS = _bool("SHOW_BANGLA_NUMERALS", True)

    # ── Security headers (§12.3) ─────────────────────────────────────────────
    # 'unsafe-inline' is required by the section editor's live preview; scripts
    # have no inline exception.
    CONTENT_SECURITY_POLICY = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' https://challenges.cloudflare.com; "
        "frame-src https://challenges.cloudflare.com; font-src 'self'; "
        "connect-src 'self'; form-action 'self'; base-uri 'self'; "
        "frame-ancestors 'none'; object-src 'none'; upgrade-insecure-requests"
    )
    HSTS_MAX_AGE = _int("HSTS_MAX_AGE", 31536000)

    # ── Derived paths ────────────────────────────────────────────────────────
    BASE_DIR = BASE_DIR
    INSTANCE_DIR = INSTANCE_DIR
    VAR_DIR = VAR_DIR
    STATIC_DIR = BASE_DIR / "app" / "static"
    APP_CSS_PATH = BASE_DIR / "app" / "static" / "css" / "app.css"


class DevConfig(BaseConfig):
    """Local development. SQLite, verbose, and nothing that sends real mail."""

    DEBUG = True
    TESTING = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    SESSION_COOKIE_SECURE = False
    TURNSTILE_ENABLED = False
    MAIL_PROVIDER = "dryrun"
    CACHE_TYPE = "FileSystemCache"
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_HEADERS_ENABLED = True
    ALLOWED_HOSTS: tuple[str, ...] = ()
    SHOW_BANGLA_NUMERALS = True
    TEMPLATES_AUTO_RELOAD = True


class TestConfig(BaseConfig):
    """Tests. In-memory SQLite, no CSRF, no rate limiting, no mail."""

    TESTING = True
    DEBUG = False
    # A test-only key. Deliberately obvious and deliberately not a secret: every
    # session in the suite is disposable and lasts one test. It could not reach
    # production anyway — it is far under ProdConfig.validate()'s 32-char minimum,
    # so both validate() and `flask check-config` reject it.
    SECRET_KEY = "test-secret-key-not-used-outside-tests"  # noqa: S105
    SQLALCHEMY_DATABASE_URI = "sqlite://"  # in-memory
    # StaticPool, so the whole test process shares ONE in-memory database. SQLite's
    # default pool hands a new connection its own empty database, which makes a
    # schema created in a fixture invisible to the test that follows — every test
    # then fails with "no such table", which reads as a model bug rather than a
    # pooling one. check_same_thread=False for the same reason: pytest may touch the
    # connection from a different thread than the one that created it.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "poolclass": StaticPool,
        "connect_args": {"check_same_thread": False},
    }
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    TURNSTILE_ENABLED = False
    MAIL_PROVIDER = "dryrun"
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 0
    RATELIMIT_ENABLED = False
    RATELIMIT_HEADERS_ENABLED = True
    ADMIN_2FA_REQUIRED = False
    BCRYPT_LOG_ROUNDS = 4  # deliberately cheap: 12 makes a suite crawl

    # HERMETIC, AND EXPLICITLY SO.
    # The base config reads this from the environment, and `.env` is loaded everywhere
    # except production — so a developer who had set ADMIN_IP_ALLOWLIST for their own
    # machine would see every admin test fail with a 403 that says nothing about the
    # behaviour under test. It did exactly that the first time these tests ran. The
    # allowlist tests in test_session_policy.py set it themselves, deliberately.
    ADMIN_IP_ALLOWLIST = ()
    SESSION_IDLE_SECONDS = 1800
    PERMANENT_SESSION_LIFETIME = 28800
    ALLOWED_HOSTS: tuple[str, ...] = ()
    STATS_CACHE_TIMEOUT = 0


class ProdConfig(BaseConfig):
    """Production on cPanel + Passenger.

    The three settings with no safe default are validated in ``validate()`` and
    called from the app factory, so a misconfigured production boot fails loudly
    and immediately rather than at the first request that needs them.
    """

    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    TURNSTILE_ENABLED = _bool("TURNSTILE_ENABLED", True)

    @classmethod
    def validate(cls) -> None:
        missing: list[str] = []

        if not cls.SECRET_KEY or len(cls.SECRET_KEY) < 32:
            missing.append(
                "SECRET_KEY — must be set and at least 32 characters. "
                "Generate: python -c \"import secrets;print(secrets.token_hex(32))\""
            )

        uri = cls.SQLALCHEMY_DATABASE_URI or ""
        if not uri:
            missing.append("DATABASE_URL — must be set")
        elif uri.startswith("sqlite"):
            missing.append(
                "DATABASE_URL — SQLite is for development. Production is MySQL "
                "with ?charset=utf8mb4 (§9.4)"
            )
        elif "utf8mb4" not in uri:
            # The single most damaging misconfiguration in this project: a latin1
            # schema mangles Bangla silently and is only noticed by a human
            # reading the site (R5).
            missing.append(
                "DATABASE_URL — must contain charset=utf8mb4. Without it every "
                "Bangla string is silently corrupted (§9.4, R5)"
            )

        if not cls.ALLOWED_HOSTS:
            missing.append("ALLOWED_HOSTS — must list the production hostnames")

        if cls.APP_URL.startswith("http://"):
            missing.append(f"APP_URL — must be https in production, got {cls.APP_URL}")

        if cls.ADMIN_URL_PREFIX.strip("/") in {"admin", "administrator", ""}:
            missing.append(
                "ADMIN_URL_PREFIX — must be non-guessable; /admin must stay a 404 (§12.1)"
            )

        if missing:
            raise RuntimeError(
                "production configuration is invalid:\n  - " + "\n  - ".join(missing)
            )


CONFIG_MAP: dict[str, type[BaseConfig]] = {
    "development": DevConfig,
    "testing": TestConfig,
    "production": ProdConfig,
}


def get_config(name: str | None = None) -> type[BaseConfig]:
    """Resolve a config class from an explicit name or ``APP_ENV``.

    Note that ``.env`` has already been loaded by the time this runs — see the
    module-level load above. This call is kept as a belt-and-braces re-read for
    callers that only reach here, and it is idempotent (``override=False``).
    """
    resolved = (name or os.environ.get("APP_ENV") or "development").strip().lower()

    if resolved != "production":
        load_dotenv(BASE_DIR / ".env", override=False)

    if resolved not in CONFIG_MAP:
        raise RuntimeError(
            f"APP_ENV={resolved!r} is not one of {', '.join(sorted(CONFIG_MAP))}"
        )

    cls = CONFIG_MAP[resolved]
    if resolved == "production":
        cls.validate()
    return cls
