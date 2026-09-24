"""Admin authentication — routes 14 and 15. plan.md §12.1.

Phase 4 adds login, logout, TOTP verification and the lockout. The blueprint is
created now with its non-guessable prefix wired in the factory, because that
prefix is the one setting a wrong default would expose the admin surface.
"""

from __future__ import annotations

from flask import Blueprint

auth_bp = Blueprint("auth", __name__)
URL_PREFIX = None
