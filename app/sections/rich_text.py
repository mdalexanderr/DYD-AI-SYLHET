"""rich_text — a prose block. plan.md §4.2, §9.3 rule 3.

§9.3 RULE 3, AND WHY IT IS APPLIED TWICE
    "rich_text bodies pass through bleach with a strict allowlist on save AND on
    render." Sanitising on save only would mean every body written before a change to
    the allowlist stays permissive forever; sanitising on render only would store
    whatever an attacker posted. Two calls to the same function is the cheap half of
    defence in depth — and the sanitiser is the same one, so the two can never
    disagree about what is allowed.

    This is also why the field is named `body_bn` and not `body_html`: the `_html`
    suffix is reserved for values the sanitiser has already produced, and `check-bans`
    only permits `|safe` on those.
"""

from __future__ import annotations

from typing import Any

from app.constants import SectionType
from app.sections.base import SectionBase
from app.security.sanitize import sanitize_html


class RichTextSection(SectionBase):
    type = SectionType.RICH_TEXT
    schema = {
        "heading_bn": {"type": "str", "max": 200, "label_bn": "শিরোনাম"},
        "body_bn": {"type": "text", "required": True, "label_bn": "বিষয়বস্তু"},
        "narrow": {"type": "bool", "label_bn": "সংকীর্ণ কলাম"},
    }

    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        return {
            "heading": payload.get("heading_bn"),
            # Sanitised HERE, on the way out, as well as on the way in.
            "body_html": sanitize_html(payload.get("body_bn") or ""),
            "narrow": bool(payload.get("narrow", True)),
        }
