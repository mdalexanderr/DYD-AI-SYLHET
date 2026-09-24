"""/batch-1 and participant profiles — routes 3, 4, 13. plan.md §6.2, §6.4.

Phase 5 adds the admin CRUD; Phase 7 adds search, filters and pagination. The
blueprint exists now so the URL prefix and the CSRF posture are fixed early.
"""

from __future__ import annotations

from flask import Blueprint

participants_bp = Blueprint("participants", __name__)
URL_PREFIX = None
