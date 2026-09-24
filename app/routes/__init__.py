"""Route package. Six blueprints, per §9.2.

Each module exposes a ``<name>_bp`` Blueprint and an optional ``URL_PREFIX``.
``app/create_app`` imports them by name so a broken import is a hard boot failure
rather than a site that quietly has no admin.

Phase 2 creates them with the routes they can already implement. Later phases fill
them in; the split matters because a blueprint that does not exist yet cannot be
tested for having the right prefix or the right protection.
"""

from __future__ import annotations

__all__ = ["admin", "api", "auth", "participants", "public", "seo"]
