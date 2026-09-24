"""sitemap.xml and robots.txt — routes 9 and 10. plan.md §6.2, §15.3.

Phase 3 builds both from published pages and consented participant profiles only.
The robots rules are a privacy control as much as an SEO one: a non-consented
participant must not be discoverable, and the sitemap must not leak a slug for one.
"""

from __future__ import annotations

from flask import Blueprint

seo_bp = Blueprint("seo", __name__)
URL_PREFIX = None
