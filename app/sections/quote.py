"""quote — a pull quote. plan.md §4.2, §5.3 rule 5.

WHY THIS SECTION CANNOT PUBLISH SOMEBODY BY ITSELF
    A `quote` section carries its own text and attribution; it does not reference a
    participant. The reason is §5.3 rule 5: permission to appear in a list and
    permission to be quoted are separate consents, and a section that pulled a quote
    from a participant row would be a way to publish words without the second one.

    A participant's quote reaches a page only through the profile projection in
    `participant_service`, which returns the text solely when `quote_consented` is set.

    The attribution is free text — "ব্যাচ ১-এর একজন প্রশিক্ষণার্থী" is the honest form
    for somebody who agreed to be quoted but not to be named.
"""

from __future__ import annotations

from typing import Any

from app.constants import SectionType
from app.sections.base import SectionBase


class QuoteSection(SectionBase):
    type = SectionType.QUOTE
    schema = {
        # Required, because a quote section with no quote renders an empty block. Whether
        # the quote is PERMITTED is a participant-level rule (§5.3 rule 5), not a
        # section-level one.
        "quote_bn": {"type": "text", "required": True, "label_bn": "উদ্ধৃতি"},
        "attribution_bn": {"type": "str", "max": 160, "label_bn": "উৎস"},
    }

    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        return {
            "quote_bn": payload.get("quote_bn"),
            "attribution_bn": payload.get("attribution_bn"),
        }
