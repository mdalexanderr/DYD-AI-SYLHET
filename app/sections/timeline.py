"""timeline — the programme's stages. plan.md §4.2.

Dates are stored as free text (`date_bn`), not as `Date`, because the timeline is a
sequence of stages rather than a schedule: "আবেদন আহ্বান", "নির্বাচন", "প্রশিক্ষণ শুরু".
Q1 in §22 leaves the real dates unconfirmed, and a `Date` column would force a
placeholder into the database that then reads like a fact.
"""

from __future__ import annotations

from typing import Any

from app.constants import SectionType
from app.sections.base import SectionBase


class TimelineSection(SectionBase):
    type = SectionType.TIMELINE
    schema = {
        "heading_bn": {"type": "str", "max": 200, "label_bn": "শিরোনাম"},
        "subtext_bn": {"type": "str", "max": 240, "label_bn": "সহায়ক বাক্য"},
        "items": {
            "type": "list",
            "required": True,
            "min_items": 1,
            "max_items": 12,
            "label_bn": "ঘটনাপ্রবাহ",
            "item": {"type": "timeline_item", "required": True, "label_bn": "ঘটনা"},
        },
    }

    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        return {
            "heading": payload.get("heading_bn"),
            "subtext": payload.get("subtext_bn"),
            "items": payload.get("items") or [],
        }
