"""Public pages — routes 1–8 and the media endpoint. plan.md §6.2.

Phase 2 creates the blueprint with its prefix and nothing else. Phase 3 adds the
routes and their section rendering (step 3.5), which is deliberately a separate
commit: a page that renders before the section renderer exists would have to be
rewritten rather than extended.
"""

from __future__ import annotations

from flask import Blueprint

public_bp = Blueprint("public", __name__)
URL_PREFIX = None
