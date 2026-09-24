"""participant_grid — the list of trainees. plan.md §4.2, §6.4.

THE ONE SECTION WHERE A MISTAKE PUBLISHES SOMEBODY WHO NEVER AGREED
    Every public list of people goes through `participant_service.list_published`, which
    applies the four consent conditions. This class never queries the model itself — not
    out of tidiness, but because a second query path would be a second place the
    publication rule is expressed, and the second place is the one that drifts.
"""

from __future__ import annotations

from typing import Any

from app.constants import FILTERABLE_OUTCOMES, SectionType
from app.filters import bn_num
from app.sections.base import SectionBase

SORT_CHOICES = ("name", "recent", "manual")

#: The five filterable outcomes. `other` is excluded on purpose (§6.4): a bucket of
#: "everything else" is not useful to browse, and its size is identifying when small.
OUTCOME_CHOICES = tuple(member.value for member in FILTERABLE_OUTCOMES)

#: §6.6 caps a grid at 48 so a page cannot accidentally load the whole cohort.
MAX_LIMIT = 48


class ParticipantGridSection(SectionBase):
    type = SectionType.PARTICIPANT_GRID
    schema = {
        "heading_bn": {"type": "str", "max": 200, "label_bn": "শিরোনাম"},
        "subtext_bn": {"type": "str", "max": 240, "label_bn": "সহায়ক বাক্য"},
        "limit": {"type": "int", "min": 1, "max": MAX_LIMIT, "label_bn": "সর্বোচ্চ সংখ্যা"},
        "sort": {"type": "enum", "choices": SORT_CHOICES, "label_bn": "সাজানোর নিয়ম"},
        "outcome": {"type": "enum", "choices": OUTCOME_CHOICES, "label_bn": "ফলাফল ফিল্টার"},
    }

    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        """Resolve the grid, honouring the visitor's filter choices.

        `request.args` beats the stored payload, because a filter the READER set has to
        win over a default an EDITOR saved — otherwise the filter bar is broken in the
        only way that matters: it accepts input and ignores it.

        Reading the request here rather than in the route keeps `/batch-1` an ordinary
        CMS page. The route does not need to know that one of its sections is
        filterable, and adding a second filterable section would not touch it.
        """
        from app.services import participant_service

        args = getattr(request, "args", None) or {}

        def _arg(name: str) -> str | None:
            """A trimmed query parameter, or None when absent or blank.

            Blank counts as absent so that `?outcome=` — which is what an empty
            <select> submits — falls back to the stored default instead of being read
            as "filter on the empty string".
            """
            value = args.get(name)
            if not isinstance(value, str):
                return None
            value = value.strip()
            return value or None

        limit = payload.get("limit") or 6
        sort = _arg("sort") or payload.get("sort") or "manual"
        outcome = _arg("outcome") or payload.get("outcome")
        query = _arg("q")

        # Coerced after reading, so a hand-written URL cannot put a junk value into the
        # ORDER BY or the WHERE clause.
        sort = sort if sort in SORT_CHOICES else "manual"
        outcome = outcome if outcome in OUTCOME_CHOICES else None

        participants = self.participants(
            limit=min(int(limit), MAX_LIMIT),
            sort=sort,
            outcome=outcome,
            query=query,
        )
        return {
            "heading": payload.get("heading_bn"),
            "subtext": payload.get("subtext_bn"),
            "participants": participants,
            # Bangla numerals, because every number a reader sees is in Bangla (§7.4).
            "count_bn": bn_num(len(participants)),
            # The filter state, so the bar shows what is actually applied instead of
            # resetting itself on every page load.
            "query": query or "",
            "sort": sort,
            "outcome": outcome or "",
            "has_filters": bool(query or outcome or sort != "manual"),
            "outcomes": participant_service.outcome_choices(),
        }
