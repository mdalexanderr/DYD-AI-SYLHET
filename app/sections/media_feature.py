"""media_feature — one image beside body copy. plan.md §4.2.

Like `rich_text`, the body is sanitised on the way out as well as on the way in, and
for the same reason: a body written before a change to the allowlist must not stay
permissive forever.
"""

from __future__ import annotations

from typing import Any

from app.constants import SectionType
from app.sections.base import SectionBase
from app.security.sanitize import sanitize_html

LAYOUT_CHOICES = ("left", "right", "full")


class MediaFeatureSection(SectionBase):
    type = SectionType.MEDIA_FEATURE
    schema = {
        "heading_bn": {"type": "str", "max": 200, "label_bn": "শিরোনাম"},
        "body_bn": {"type": "text", "label_bn": "বিষয়বস্তু"},
        "media_id": {"type": "ref", "model": "MediaItem", "required": True, "label_bn": "ছবি"},
        "layout": {"type": "enum", "choices": LAYOUT_CHOICES, "label_bn": "বিন্যাস"},
    }

    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        layout = payload.get("layout") or "right"
        return {
            "heading": payload.get("heading_bn"),
            "body_html": sanitize_html(payload.get("body_bn") or ""),
            "media": self.media(payload.get("media_id")),
            "layout": layout if layout in LAYOUT_CHOICES else "right",
        }
