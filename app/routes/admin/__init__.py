"""Admin CMS — routes 16–34. plan.md §6.2, §11.

A package rather than a module because it is 19 routes across 10 screens. Each
screen becomes its own module in Phase 4–6 (``pages.py``, ``participants.py``,
``media.py``, …) and they all hang off this blueprint.

The URL prefix is set by the app factory from ``ADMIN_URL_PREFIX`` (§12.1), not
here — a prefix declared in two places is a prefix that will disagree, and the
disagreement would be a guessable admin path.
"""

from __future__ import annotations

from flask import Blueprint

admin_bp = Blueprint("admin", __name__)
URL_PREFIX = None  # set by create_app from ADMIN_URL_PREFIX
