"""institution_card — the training institute. plan.md §4.2, §3.2.

THE INSTITUTION'S NAME AND ADDRESS ARE Q2 IN §22
    They are UNCONFIRMED. The seeder carries the supplied value verbatim and expands
    nothing — "Sylhet BUTTC" is not turned into a guessed full name. Until the
    department confirms them, the Course and About pages are drafts (R11), and this
    section is where an unconfirmed value would first reach a reader.

    The section holds a reference rather than a copy so there is one place to correct.
"""

from __future__ import annotations

from typing import Any

from app.constants import SectionType
from app.sections.base import SectionBase


class InstitutionCardSection(SectionBase):
    type = SectionType.INSTITUTION_CARD
    schema = {
        "heading_bn": {"type": "str", "max": 200, "label_bn": "শিরোনাম"},
        "institution_id": {
            "type": "ref",
            "model": "Institution",
            "required": True,
            "label_bn": "প্রতিষ্ঠান",
        },
    }

    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        return {
            "heading": payload.get("heading_bn"),
            # The model itself, because `institution_card` reads the attributes
            # directly and a projection here would be one more place to keep in step.
            # It is a CMS record about an organisation, not a person — there is no
            # privacy boundary to enforce.
            "inst": self.institution(payload.get("institution_id")),
        }
