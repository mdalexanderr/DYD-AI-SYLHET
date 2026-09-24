"""Operational endpoints — route 11 (/health) and route 12 (PWA manifest).

plan.md §6.2, §17.3, §15.2.

/health IS INFRASTRUCTURE, NOT A COURTESY
    UptimeRobot watches it (§17.6), ``deploy.sh``'s smoke tests assert it, and its
    shape is a contract: ``{"db": "...", "css": "..."}``. It deliberately answers
    during maintenance mode, because a monitoring system that cannot distinguish
    "temporarily closed" from "unreachable" pages a human at 3am.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

api_bp = Blueprint("api", __name__)


@api_bp.get("/health")
def health():
    """Liveness plus the two things that actually go wrong.

    A 200 with ``"db": "fail"`` is intentional: the process is alive, so an
    uptime probe should see it and a human should read the body. Returning 503
    here would look identical to the app being down, which is less useful.
    """
    from app.extensions import db

    db_state = "ok"
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        current_app.logger.exception("health: database check failed")
        db_state = "fail"

    css_path = Path(current_app.config["APP_CSS_PATH"])
    # A missing or truncated stylesheet is the failure mode the deploy pre-flight
    # exists for (§17.3 step 5), so /health reports it too.
    css_state = "ok" if css_path.exists() and css_path.stat().st_size > 1024 else "fail"

    return jsonify(
        {
            "db": db_state,
            "css": css_state,
            "env": current_app.config["APP_ENV"],
            "name": current_app.config["APP_NAME"],
        }
    )


@api_bp.get("/robots.txt")
def robots_unavailable():
    """Placeholder — the real robots.txt is built in seo.py (Phase 3).

    Defined as a 404 rather than omitted so that a request for it during
    development fails visibly instead of landing on the public catch-all.

    The body is real plain text with an explicit `text/plain` content type, not an
    empty string. Flask types an empty body as `text/html` by default, which makes
    this look like a broken HTML page to anything inspecting content type — and a
    404 that says nothing is indistinguishable from a routing bug.

    A 404 for robots.txt is the safe answer: crawlers treat a missing file as
    "no restrictions stated", and nothing is disallowed by accident.
    """
    return (
        "# robots.txt is not served yet; the real file is built in Phase 3 (seo.py).\n",
        404,
        {"Content-Type": "text/plain; charset=utf-8"},
    )
