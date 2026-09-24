"""module_list — the course syllabus. plan.md §4.2, §3.1.

RENDERS FROM THE COURSE, NOT FROM THE PAYLOAD
    The payload holds a `course_id`, and the six modules come from `course_modules`.
    Duplicating the syllabus into a section payload would give the department two
    places to correct the same list, and the one nobody edits would be the one that
    goes stale.

    This is also why the admin edit screen for this type is a course picker rather
    than a repeatable module editor (§11.2).
"""

from __future__ import annotations

from typing import Any

from app.constants import SectionType
from app.sections.base import SectionBase


class ModuleListSection(SectionBase):
    type = SectionType.MODULE_LIST
    schema = {
        "heading_bn": {"type": "str", "max": 200, "label_bn": "শিরোনাম"},
        "subtext_bn": {"type": "str", "max": 240, "label_bn": "সহায়ক বাক্য"},
        "course_id": {"type": "ref", "model": "Course", "required": True, "label_bn": "কোর্স"},
        "columns": {"type": "int", "min": 1, "max": 3, "label_bn": "কলাম সংখ্যা"},
    }

    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        course = self.course(payload.get("course_id"))
        modules = []
        if course is not None:
            # Sorted here rather than trusting the relationship's `order_by`, because
            # a syllabus whose order depends on relationship configuration is a
            # syllabus that silently reorders when that configuration changes.
            modules = sorted(course.modules, key=lambda m: (m.sort_order, m.id))
        return {
            "heading": payload.get("heading_bn"),
            "subtext": payload.get("subtext_bn"),
            "modules": modules,
            "course": course,
            "columns": _column_class(payload.get("columns")),
        }


def _column_class(value: Any) -> str | None:
    """The grid class for a column count, or None for the macro's own default.

    See stat_strip.py for why this is a lookup and not interpolation: Tailwind cannot
    generate a class it has never read.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return _COLUMN_CLASSES.get(value)


_COLUMN_CLASSES: dict[int, str] = {
    1: "grid-cols-1",
    2: "sm:grid-cols-2",
    3: "sm:grid-cols-2 lg:grid-cols-3",
}
