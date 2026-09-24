"""Application factory. plan.md §9.2, §12.3.

    create_app("production")  ->  a configured Flask app

WHY A FACTORY AND NOT A MODULE-LEVEL ``app``
    The test suite builds a fresh application per test with ``TestConfig``, and
    ``flask`` CLI commands need one with the real environment. A module-level app
    would make both impossible without monkeypatching globals.

MODELS ARE IMPORTED INSIDE THE FUNCTION, ON PURPOSE
    ``app/models/base.py`` imports ``db`` from ``app.extensions``. Importing the
    models at module scope here would make ``app/__init__.py`` import
    ``app.models`` which imports ``app`` — a cycle that Python resolves by giving
    one side a half-built module, and the resulting ``AttributeError`` is
    notoriously hard to read. Importing inside ``create_app`` is the standard
    Flask pattern for the same reason.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, Response, jsonify, make_response, render_template, request

from app.config import BaseConfig, get_config
from app.filters import register_filters

__all__ = ["create_app"]

#: The 6 blueprints of §9.2, in registration order.
BLUEPRINT_MODULES = (
    ("app.routes.public", "public"),
    ("app.routes.participants", "participants"),
    ("app.routes.auth", "auth"),
    ("app.routes.seo", "seo"),
    ("app.routes.api", "api"),
    ("app.routes.admin", "admin"),
)


def create_app(config_name: str | None = None) -> Flask:
    config_class: type[BaseConfig] = get_config(config_name)

    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_class)

    _configure_logging(app, config_class)
    _configure_hosts(app)
    _configure_paths(app)

    from app.extensions import init_extensions

    init_extensions(app)

    # Registers every model on db.metadata. Must happen before migrations or the
    # first db upgrade creates an empty database.
    from app import models  # noqa: F401

    register_filters(app)
    _inject_template_globals(app)
    _before_request(app, config_class)
    _after_request(app)
    _error_handlers(app)
    _register_blueprints(app)

    from app.cli import register_cli

    register_cli(app)

    app.logger.debug(
        "created %s app: env=%s debug=%s db=%s",
        app.config["APP_NAME"],
        app.config["APP_ENV"],
        app.debug,
        _safe_database_label(app.config["SQLALCHEMY_DATABASE_URI"]),
    )
    return app


# ─────────────────────────────────────────────────────────────────────────────
def _safe_database_label(uri: str) -> str:
    """A database URI without its password, for logs.

    Passwords in log files are found by whoever reads the log, which on a shared
    host is not always the person who set it.
    """
    if "@" not in uri:
        return uri
    scheme, rest = uri.split("://", 1)
    credentials, host = rest.split("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"


def _inject_template_globals(app: Flask) -> None:
    """Globals every template needs. Deliberately NOT from the database.

    The 500 page and the maintenance page extend the same layout as every public
    page, and the most common cause of a 500 on this site is the database being
    unreachable. A context processor that read site settings from a `settings`
    table would therefore raise a second exception while rendering the error page,
    and the reader would get the plain-text fallback instead of the Bangla page.
    So brand identity comes from config with §6.3 defaults, and nothing here
    queries anything.

    HEADER_NAV carries the plan's key `path`; the `site_nav` macro reads `href`.
    The translation happens once, here, rather than by teaching the macro both
    names — two names for one value is two names that will diverge.
    """
    from app.constants import HEADER_NAV

    nav_items = [
        {"slug": item["slug"], "label": item["label"], "href": item["path"]}
        for item in HEADER_NAV
    ]

    def _cfg(key: str, fallback: str | None) -> str | None:
        value = app.config.get(key)
        return value if value not in (None, "") else fallback

    brand = {
        "title_bn": _cfg("SITE_TITLE_BN", "এআই সিলেট"),
        "tagline_bn": _cfg("SITE_TAGLINE_BN", "যুব উন্নয়ন অধিদপ্তর"),
        "hotline": _cfg("SITE_HOTLINE", "+88 02-8091188"),
        "mobile": _cfg("SITE_HOTLINE_MOBILE", "01550-666900"),
        # The ORGANISATION's public contact address from §6.3, not a participant
        # field. The ban check matches the bare token, so the marker is required.
        "email": _cfg("SITE_EMAIL", "info@elaeltd.com"),  # check-bans:ignore org contact
        "address_bn": _cfg("SITE_HQ_ADDRESS_BN", None),
        "facebook_url": _cfg("SITE_FACEBOOK_URL", None),
        "privacy_href": "/privacy",
        # Bangla numerals in a copyright line, because §7.4's rule is that every
        # number a reader sees is in Bangla.
        "copyright_year_bn": "২০২৬",
    }

    @app.context_processor
    def _template_globals() -> dict[str, object]:
        path = request.path
        # Longest match wins, so /batch-1 does not resolve to /"home" simply
        # because home is listed first.
        current_slug = None
        for item in sorted(nav_items, key=lambda i: len(i["href"]), reverse=True):
            if item["href"] == "/":
                continue
            if path == item["href"] or path.startswith(item["href"] + "/"):
                current_slug = item["slug"]
                break
        if current_slug is None and path == "/":
            current_slug = "home"

        return {
            "nav_items": nav_items,
            "current_slug": current_slug,
            "brand": brand,
        }


def _configure_logging(app: Flask, config_class: type[BaseConfig]) -> None:
    """Rotating file log plus stderr, at the configured level (§17.6)."""
    level = getattr(logging, str(app.config["LOG_LEVEL"]).upper(), logging.INFO)

    app.logger.handlers.clear()
    app.logger.setLevel(level)
    app.logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    stream.setLevel(level)
    app.logger.addHandler(stream)

    log_dir = Path(app.config["LOG_DIR"])
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=int(app.config["LOG_MAX_BYTES"]),
            backupCount=int(app.config["LOG_BACKUP_COUNT"]),
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        app.logger.addHandler(file_handler)
    except OSError as exc:
        # A read-only filesystem must not stop the site from booting; the stream
        # handler is still attached.
        app.logger.warning("file logging unavailable (%s); stderr only", exc)

    if not app.debug and not app.testing:
        logging.getLogger("werkzeug").setLevel(logging.WARNING)


def _configure_hosts(app: Flask) -> None:
    """Map ALLOWED_HOSTS onto Flask's TRUSTED_HOSTS (Host-header protection).

    Left empty in development and testing so ``localhost:5000`` and the test
    client's ``localhost`` both work without configuration.
    """
    hosts = app.config.get("ALLOWED_HOSTS") or ()
    if hosts:
        app.config["TRUSTED_HOSTS"] = list(hosts)


def _configure_paths(app: Flask) -> None:
    """Create the runtime directories the app writes to.

    Runtime state lives outside ``app/`` so a deploy that replaces the code
    directory cannot delete it, and so ``.gitignore`` can be blunt about it.
    """
    for key in ("INSTANCE_DIR", "VAR_DIR", "UPLOAD_ROOT"):
        Path(app.config[key]).mkdir(parents=True, exist_ok=True)
    # These three can legitimately be unwritable on a shared host (a read-only
    # var/ during a freeze, for instance). A missing cache directory degrades the
    # site; it must not stop it booting, so the failure is swallowed and the
    # cache falls back to its own behaviour.
    for key in ("CACHE_DIR", "LOG_DIR", "BACKUP_ROOT"):
        try:
            Path(app.config[key]).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def _before_request(app: Flask, config_class: type[BaseConfig]) -> None:
    """Maintenance mode (§9.2), the admin IP allowlist (4.4), and session policy (4.2).

    Registered in that order deliberately. Maintenance answers first so a closed site
    does not also reveal whether an admin is signed in; the allowlist is the cheapest
    refusal and belongs before any session work; the session policy runs last because
    it is the only one of the three that touches state.
    """

    # Imported locally because the handlers below are the only consumers of these in
    # this module, and this module is imported very early in the process.
    import time

    from flask import flash, redirect, session, url_for
    from flask_login import current_user, logout_user

    @app.before_request
    def _maintenance() -> Response | None:
        if not (app.config.get("MAINTENANCE_MODE") or _setting_maintenance()):
            return None
        path = request.path
        # /health must answer even in maintenance, because it is what monitoring
        # watches — a maintenance window that looks like an outage pages someone.
        if path.startswith(("/health", "/static/", "/media/")):
            return None
        prefix = "/" + str(app.config["ADMIN_URL_PREFIX"]).strip("/")
        if path.startswith(prefix):
            return None
        # make_response, not a bare tuple: the handler is annotated `Response | None`
        # and Flask converts the tuple itself, but returning an explicit Response
        # keeps the annotation true and the Retry-After header visible in the code.
        return make_response(
            render_template("errors/maintenance.html"),
            503,
            {"Retry-After": "3600"},
        )

    @app.before_request
    def _admin_ip_allowlist() -> Response | None:
        """Step 4.4 — an optional CIDR allowlist over the admin surface.

        AN EMPTY LIST MEANS OFF, NOT "DENY EVERYTHING". The setting is documented as
        recommended-once-live (§12.1), so an unset value has to leave the site exactly
        as it was. Reading it the other way round would lock the admin out of a
        deployment that had never configured it, with the only fix being a shell on
        the server.

        A MALFORMED ENTRY DENIES RATHER THAN RAISES. A typo in `ADMIN_IP_ALLOWLIST`
        must not 500 every admin request — that turns a configuration mistake into an
        outage of the surface used to fix it. It denies, logs, and `check-config`
        reports it.

        `/login` IS COVERED. Leaving the login form reachable from anywhere while
        protecting the pages behind it protects nothing, since the form is where the
        credentials would be sent.
        """
        allowlist = app.config.get("ADMIN_IP_ALLOWLIST") or []
        if not allowlist:
            return None

        prefix = "/" + str(app.config["ADMIN_URL_PREFIX"]).strip("/")
        if not (request.path.startswith(prefix) or request.path == "/login"):
            return None

        client = _forwarded_client_ip()
        if client and _ip_in_any(client, allowlist):
            return None

        app.logger.warning("admin refused for %s: not in ADMIN_IP_ALLOWLIST", client)
        return make_response(render_template("errors/403.html"), 403)

    @app.before_request
    def _session_policy() -> Response | None:
        """Step 4.2 — 30 minutes idle, 8 hours absolute.

        TWO DIFFERENT LIMITS, AND ONLY ONE OF THEM IS FLASK'S. `PERMANENT_SESSION_LIFETIME`
        is honoured by the cookie's own expiry — but that expiry is recomputed from the
        moment of the last WRITE, and the server writes to the session on every
        authenticated request. Left at that, an admin who clicked something every 7
        hours would never be signed out, and the setting would be a lie.

        So the absolute limit is enforced here, from a timestamp taken once at login
        and never refreshed. The cookie may keep sliding; the decision does not.

        APPPLIED ONLY TO AUTHENTICATED REQUESTS. The public site has no login, and
        stamping a session onto every anonymous visitor would set a cookie — and so
        defeat caching — for readers who will never have a session.
        """
        if not current_user.is_authenticated:
            return None

        now = time.time()
        idle_limit = int(app.config["SESSION_IDLE_SECONDS"])
        absolute_limit = int(app.config["PERMANENT_SESSION_LIFETIME"])

        started_at = session.get("session_started_at")
        if started_at is None:
            # A session that predates this policy. Adopt it rather than expiring it,
            # so deploying this does not sign the admin out mid-task.
            session["session_started_at"] = now
            started_at = now

        last_seen = session.get("last_seen")
        idle_for = now - float(last_seen) if last_seen is not None else 0.0
        alive_for = now - float(started_at)

        if idle_for > idle_limit or alive_for > absolute_limit:
            reason = "নিষ্ক্রিয়তার কারণে" if idle_for > idle_limit else "সর্বোচ্চ সময় পার হওয়ায়"
            logout_user()
            session.clear()
            flash(f"{reason} নিরাপত্তার জন্য সেশন শেষ করা হয়েছে। আবার প্রবেশ করুন।", "info")
            # `make_response`, not a bare `redirect`: `redirect` returns a werkzeug
            # Response, and the handler is annotated `Response | None` with Flask's
            # Response. The same wrap the maintenance handler above uses, for the same
            # reason — keeping the annotation true rather than loosening it.
            return make_response(redirect(url_for("auth.login")))

        session["last_seen"] = now
        return None


def _forwarded_client_ip() -> str | None:
    """The client address, honouring Passenger's forwarding header.

    The same rule as `auth._client_ip` and `audit._current_ip`. Duplicated rather than
    shared because those two live in modules that import this one, so importing them
    from here would be circular.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return request.remote_addr or None


def _ip_in_any(client: str, allowlist: list[str]) -> bool:
    """True when `client` falls inside any CIDR (or bare address) in `allowlist`.

    `strict=False` so that `10.0.0.5` written without a prefix length is accepted as a
    single host instead of raising. An unparseable client address is False, not an
    exception: behind a proxy that sends something unexpected, refusing is the safe
    answer.
    """
    import ipaddress

    try:
        address = ipaddress.ip_address(client)
    except ValueError:
        return False

    for entry in allowlist:
        try:
            if address in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            # See the docstring of _admin_ip_allowlist: a typo denies, it does not 500.
            continue
    return False


def _setting_maintenance() -> bool:
    """The `maintenance_mode` feature flag from the database, if it is readable.

    Wrapped so a database that is down produces a 500 from the real request rather
    than a confusing failure inside a before_request hook.
    """
    try:
        from app.extensions import cache

        flag = cache.get("flag:maintenance_mode")
        if flag is None:
            return False
        return bool(flag)
    except Exception:  # noqa: BLE001 — never let this hook be the reason a page fails
        return False


def _after_request(app: Flask) -> None:
    """Security headers, verbatim from §12.3."""

    @app.after_request
    def _headers(response: Response) -> Response:
        response.headers.setdefault("Content-Security-Policy",
                                    app.config["CONTENT_SECURITY_POLICY"])
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), camera=(), microphone=(), payment=()"
        )
        if not app.debug and request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={app.config['HSTS_MAX_AGE']}; includeSubDomains; preload",
            )
        return response


def _error_handlers(app: Flask) -> None:
    """Bangla error pages, and JSON for the API surface."""

    def wants_json() -> bool:
        return (
            request.path.startswith("/health")
            or request.accept_mimetypes.best == "application/json"
        )

    def handler(code: int, template: str, fallback: str):
        def _handle(exc):
            if wants_json() and code != 500:
                return jsonify({"error": fallback, "status": code}), code
            try:
                return render_template(template), code
            except Exception:  # noqa: BLE001 — a missing template must not mask the error
                return fallback, code, {"Content-Type": "text/plain; charset=utf-8"}

        _handle.__name__ = f"handle_{code}"
        return _handle

    app.register_error_handler(404, handler(404, "errors/404.html", "404"))
    app.register_error_handler(403, handler(403, "errors/403.html", "403"))
    app.register_error_handler(429, handler(429, "errors/429.html", "429"))

    # 419 is NOT a code Werkzeug knows, so `register_error_handler(419, ...)` does
    # not defer the problem to request time — it raises ValueError while the app is
    # still being built, which means the whole site fails to boot. The real
    # exception an expired CSRF token raises is Flask-WTF's CSRFError, and that
    # carries code 400. So the handler is bound to the CLASS, and returns 419
    # explicitly, which is the status §12.3 asks the page to report.
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def _handle_csrf(exc):
        app.logger.info("CSRF rejected on %s: %s", request.path, exc.description)
        if wants_json():
            return jsonify({"error": "csrf_expired", "status": 419}), 419
        try:
            return render_template("errors/419.html"), 419
        except Exception:  # noqa: BLE001 — a missing template must not mask the error
            return "419", 419, {"Content-Type": "text/plain; charset=utf-8"}

    @app.errorhandler(500)
    def _handle_500(exc):
        app.logger.exception("unhandled error on %s", request.path)
        if wants_json():
            return jsonify({"error": "internal_error", "status": 500}), 500
        try:
            return render_template("errors/500.html"), 500
        except Exception:  # noqa: BLE001
            return "500", 500, {"Content-Type": "text/plain; charset=utf-8"}


def _register_blueprints(app: Flask) -> None:
    """Register the 6 blueprints. A missing one is a hard error, not a warning.

    Skipping a blueprint whose import failed would ship a site with no admin and
    no error at boot — discovered by whoever tries to log in.
    """
    from importlib import import_module

    from app.extensions import csrf

    for module_path, name in BLUEPRINT_MODULES:
        module = import_module(module_path)
        blueprint = getattr(module, f"{name}_bp", None) or module.bp
        url_prefix = getattr(module, "URL_PREFIX", None)

        if name == "admin":
            # §12.1: a non-guessable prefix, and /admin stays a 404.
            url_prefix = "/" + str(app.config["ADMIN_URL_PREFIX"]).strip("/")
        elif name == "api":
            url_prefix = None  # /health, /manifest.json live at the root

        app.register_blueprint(blueprint, url_prefix=url_prefix)

        # The admin surface is the only state-changing one that is not a public
        # form; CSRF is global (see extensions), so nothing extra is needed here.
        _ = csrf
