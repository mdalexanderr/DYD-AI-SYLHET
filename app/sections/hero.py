"""hero — the opening block. plan.md §4.2, §7.5 element 3.

Contains the Surma contour band (the only two places it appears are here and the
footer), which is why `band` is a field rather than always-on: a second hero below the
fold would repeat the pattern and stop reading as a signature.
"""

from __future__ import annotations

from typing import Any

from app.constants import SectionType
from app.sections.base import SectionBase

#: §7.3's two hero scales. `compact` is for interior pages, which need less air than
#: the homepage.
SIZE_CHOICES = ("default", "compact")


class HeroSection(SectionBase):
    type = SectionType.HERO
    schema = {
        "heading_bn": {"type": "str", "required": True, "max": 160, "label_bn": "শিরোনাম"},
        "subheading_bn": {"type": "str", "max": 320, "label_bn": "উপশিরোনাম"},
        # §4.2 calls this `background_media_id`; the §9.3 example calls it `media_id`.
        # One name is used, and the discrepancy is recorded rather than honoured twice —
        # two keys for one value is two keys that will diverge.
        "media_id": {"type": "ref", "model": "MediaItem", "label_bn": "ছবি"},
        "primary_cta": {"type": "cta", "label_bn": "প্রধান বাটন"},
        "secondary_cta": {"type": "cta", "label_bn": "দ্বিতীয় বাটন"},
        "size": {"type": "enum", "choices": SIZE_CHOICES, "label_bn": "আকার"},
    }

    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        size = payload.get("size") or "default"
        return {
            "heading_bn": payload.get("heading_bn"),
            "subheading_bn": payload.get("subheading_bn"),
            "primary_cta": payload.get("primary_cta"),
            "secondary_cta": payload.get("secondary_cta"),
            "media": self.media(payload.get("media_id")),
            "size": size if size in SIZE_CHOICES else "default",
            "band": True,
        }
