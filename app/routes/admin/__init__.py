"""Admin CMS — routes 16–34. plan.md §6.2, §11.

A package rather than a module because it is 19 routes across 10 screens. Each
screen becomes its own module in Phase 4–6 (``pages.py``, ``participants.py``,
``media.py``, …) and they all hang off this blueprint.

The URL prefix is set by the app factory from ``ADMIN_URL_PREFIX`` (§12.1), not
here — a prefix declared in two places is a prefix that will disagree, and the
disagreement would be a guessable admin path.
"""

from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import login_required

admin_bp = Blueprint("admin", __name__)
URL_PREFIX = None  # set by create_app from ADMIN_URL_PREFIX


@admin_bp.get("/")
@login_required
def index():
    """The authenticated landing page — step 4.1.

    NOT the §4.6 dashboard, and deliberately not dressed up as one. It exists
    because a login flow cannot be tested without a protected route to land on, and
    it shows only what is already true of the session: who you are and when you last
    signed in. Step 4.5 wraps it in the shell and 4.6 replaces the body.

    A richer placeholder would have to be thrown away, and — worse — a half-built
    dashboard reads as a finished one, so nobody looks for the screens that are
    still missing.
    """
    return render_template("admin/index.html")
