"""gallery_strip — a row of images. plan.md §4.2, §6.3.

NO PARTICIPANT PHOTOGRAPHS, EVER (§5.3, S2)
    A media item in this gallery is a picture of a classroom, a whiteboard or a
    certificate — never of a trainee. The schema cannot enforce that, so the admin
    upload screen is where it is enforced (Phase 4/6), and §9.1's `gallery_enabled`
    setting lets the whole surface be switched off if the department would rather not
    publish event photography either.

    `media_ids` is a list of references rather than paths on purpose: a path typed
    into a CMS field is a way to serve a file nobody vetted.
"""

from __future__ import annotations

from typing import Any

from app.constants import SectionType
from app.sections.base import SectionBase

MAX_COLUMNS = 4


class GalleryStripSection(SectionBase):
    type = SectionType.GALLERY_STRIP
    schema = {
        "heading_bn": {"type": "str", "max": 200, "label_bn": "শিরোনাম"},
        "media_ids": {
            "type": "list_ref",
            "required": True,
            "min_items": 1,
            "max_items": 12,
            "label_bn": "ছবি",
            "item": {"type": "ref", "model": "MediaItem", "required": True},
        },
        "columns": {"type": "int", "min": 1, "max": MAX_COLUMNS, "label_bn": "কলাম সংখ্যা"},
    }

    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        columns = payload.get("columns") or 3
        return {
            "heading": payload.get("heading_bn"),
            # A reference to a deleted media row is dropped rather than rendered as a
            # broken image: the page keeps working, and the gap is visible in the admin.
            "items": self.media_list(payload.get("media_ids")),
            "columns": columns if 1 <= int(columns) <= MAX_COLUMNS else 3,
        }
