"""fact_list — labelled facts about the course. plan.md §4.2.

The pairs are structured data (`label_bn` + `value_bn`), not free Markdown, so the
`Course` page's fact block can be read by a screen reader as a description list and
can feed JSON-LD later without parsing prose.
"""

from __future__ import annotations

from typing import Any

from app.constants import SectionType
from app.sections.base import SectionBase

LAYOUT_CHOICES = ("stack", "split")


class FactListSection(SectionBase):
    type = SectionType.FACT_LIST
    schema = {
        "heading_bn": {"type": "str", "max": 200, "label_bn": "শিরোনাম"},
        "items": {
            "type": "list",
            "required": True,
            "min_items": 1,
            "max_items": 24,
            "label_bn": "তথ্য",
            "item": {"type": "pair", "required": True, "label_bn": "লেবেল ও মান"},
        },
        "layout": {"type": "enum", "choices": LAYOUT_CHOICES, "label_bn": "বিন্যাস"},
    }

    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        layout = payload.get("layout") or "stack"
        # Stored as `label_bn` / `value_bn`, like every other payload key, so the CMS
        # form generator needs no special case. Renamed here to the `label` / `value`
        # shape the `fact_list` macro documents, which keeps the macro ignorant of the
        # storage naming. The `isinstance` guard matters because `content` is JSON that
        # a migration could have written by hand.
        items = [
            {"label": item.get("label_bn"), "value": item.get("value_bn")}
            for item in (payload.get("items") or [])
            if isinstance(item, dict)
        ]
        return {
            "heading": payload.get("heading_bn"),
            "items": items,
            "layout": layout if layout in LAYOUT_CHOICES else "stack",
        }
