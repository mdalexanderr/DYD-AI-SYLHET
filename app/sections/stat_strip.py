"""stat_strip — the large figures under a hero. plan.md §4.2, §6.5, §5.4.

THE VALUES DO NOT COME FROM THE PAYLOAD
    The payload names stat KEYS; the values are resolved through `stats_service`. That
    ordering is the whole point: a section cannot contain a figure the service would
    have suppressed, because a section never holds a figure at all. §5.4's `<5` rule
    would be unenforceable if a number could be typed into a CMS field and rendered
    straight out.
"""

from __future__ import annotations

from typing import Any

from app.constants import SectionType
from app.sections.base import SectionBase


class StatStripSection(SectionBase):
    type = SectionType.STAT_STRIP
    schema = {
        "heading_bn": {"type": "str", "max": 200, "label_bn": "শিরোনাম"},
        "subtext_bn": {"type": "str", "max": 240, "label_bn": "সহায়ক বাক্য"},
        "stat_keys": {
            "type": "list",
            "required": True,
            "min_items": 1,
            "max_items": 8,
            "label_bn": "পরিসংখ্যান",
            "item": {"type": "str", "required": True, "max": 64},
        },
        "columns": {"type": "int", "min": 1, "max": 4, "label_bn": "কলাম সংখ্যা"},
    }

    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        return {
            "heading": payload.get("heading_bn"),
            "subtext": payload.get("subtext_bn"),
            "stats": self.stats(payload.get("stat_keys")),
            "columns": _column_class(payload.get("columns")),
        }


def _column_class(value: Any) -> str | None:
    """The grid class for a column count, or None for the macro's own default.

    A dict lookup rather than string interpolation, because the payload is untrusted
    JSON and Tailwind cannot see a class it has never read: `lg:grid-cols-{{ n }}`
    renders a class that does not exist in the compiled sheet, so the grid silently
    collapses. This is the same constraint that put `@source inline(...)` in
    source.css.

    A string `"3"` falls back to the default rather than being coerced, so a bad CMS
    value degrades to a sensible grid instead of a broken one.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return _COLUMN_CLASSES.get(value)


_COLUMN_CLASSES: dict[int, str] = {
    1: "grid-cols-1",
    2: "sm:grid-cols-2",
    3: "sm:grid-cols-2 lg:grid-cols-3",
    4: "sm:grid-cols-2 lg:grid-cols-4",
}
