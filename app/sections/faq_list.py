"""faq_list — a category or an explicit set of questions. plan.md §4.2, §15.3.

A CATEGORY OR A LIST, AND WHY BOTH
    A list of ids lets the About page pick five specific questions; a category lets the
    Course page show everything filed under `কোর্স` without the editor maintaining ids.
    The ids form wins when both are given, because choosing five specific questions is
    the more deliberate act.

    Answers stay in the DOM (the `faq_accordion` macro uses `<details>`, not a script),
    which is what makes the FAQPage JSON-LD legitimate — structured data has to
    describe content a reader can actually see (§15.3).
"""

from __future__ import annotations

from typing import Any

from app.constants import SectionType
from app.sections.base import SectionBase


class FaqListSection(SectionBase):
    type = SectionType.FAQ_LIST
    schema = {
        "heading_bn": {"type": "str", "max": 200, "label_bn": "শিরোনাম"},
        "subtext_bn": {"type": "str", "max": 240, "label_bn": "সহায়ক বাক্য"},
        "faq_ids": {
            "type": "list",
            "max_items": 30,
            "label_bn": "নির্দিষ্ট প্রশ্ন",
            "item": {"type": "int", "required": True},
        },
        "category": {"type": "str", "max": 64, "label_bn": "শ্রেণি"},
    }

    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        faq_ids = payload.get("faq_ids")
        category = payload.get("category")
        faqs = self.faqs(
            faq_ids=faq_ids if isinstance(faq_ids, list) and faq_ids else None,
            category=category if isinstance(category, str) and category else None,
        )
        return {
            "heading": payload.get("heading_bn"),
            "subtext": payload.get("subtext_bn"),
            "faqs": faqs,
        }
