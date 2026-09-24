"""cta_band — a closing call to action. plan.md §4.2.

Its href is stored FLAT (`cta_label` / `cta_href`) rather than as a `cta` mapping,
because that is what the `cta_band` macro takes and what the seed data already uses.
Two shapes for the same value is already a smell, so the RULE that governs the href is
shared with `cta` fields rather than reimplemented — `validate_href` is the one place
that decides what a link may point at.

That matters because a CMS-supplied href is stored XSS waiting for a click and an open
redirect on a government domain.
"""

from __future__ import annotations

from typing import Any

from app.constants import SectionType
from app.sections.base import SectionBase, validate_href


class CtaBandSection(SectionBase):
    type = SectionType.CTA_BAND
    schema = {
        "heading_bn": {"type": "str", "required": True, "max": 200, "label_bn": "শিরোনাম"},
        "body_bn": {"type": "text", "label_bn": "বিষয়বস্তু"},
        "cta_label": {"type": "str", "max": 80, "label_bn": "বাটনের লেখা"},
        "cta_href": {"type": "str", "max": 300, "label_bn": "বাটনের লিংক"},
    }

    def _validate_extra(self, payload: dict[str, Any]) -> tuple[bool, str]:
        """A button is a pair: half of one is either dead or unlabelled.

        The `cta` field type enforces this inside `_check_scalar`; here the label and
        the href are separate fields, so the pairing has to be checked explicitly.
        """
        label = str(payload.get("cta_label") or "").strip()
        href = payload.get("cta_href")

        if label and not href:
            return False, "“বাটনের লেখা” থাকলে “বাটনের লিংক”ও থাকতে হবে।"
        if href:
            if not label:
                return False, "“বাটনের লিংক” থাকলে “বাটনের লেখা”ও থাকতে হবে।"
            return validate_href(href, "বাটনের লিংক")
        return True, ""

    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        return {
            "heading_bn": payload.get("heading_bn"),
            "body_bn": payload.get("body_bn"),
            "cta_label": payload.get("cta_label"),
            "cta_href": payload.get("cta_href"),
        }
