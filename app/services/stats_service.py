"""Statistics: consent-only aggregates and the `<5` suppression rule.
plan.md §5.4, §6.5, S6; execution-plan step 3.2.

TWO RULES, BOTH ABOUT WHAT A NUMBER IS ALLOWED TO REVEAL

  1. A COUNT NEVER INCLUDES A NON-CONSENTED PARTICIPANT.
     This phase's exit gate says a non-consented participant must be absent from the
     pages, the counts, the statistics AND the sitemap. A total that included them
     would leak their existence into a figure, so every count here derives from the
     consented set. That is why `cohort_total` means "the cohort we may document"
     rather than the raw enrolment — and the distinction is stated here rather than
     left to whoever reads the label `মোট প্রশিক্ষণার্থী`.

  2. A CELL BUILT FROM FEWER THAN FIVE RECORDS RENDERS `—`.
     Not cosmetic. "1 person in this outcome" in a cohort of twenty identifies that
     person, and on a page that lists names it identifies them BY NAME. The rule is
     applied HERE, at the boundary where a figure becomes presentable, so a template
     cannot show a raw number by accident: `stat_strip` renders `—` whenever the value
     it receives is `None`, and this service is what sets it to `None`.

WHY THE THRESHOLD IS CONFIGURATION
    `STATS_SUPPRESS_BELOW` (§16.1) rather than a literal 5, because the department may
    decide that even a larger cohort is still identifying and want it raised.

CACHING (§9.5)
    300 s, invalidated on any participant write by `invalidate()`. `consent_service`
    (Phase 5) must call it inside the same transaction as the write, because a stale
    count surviving a withdrawal is a privacy bug, not a performance detail.

WHY THE COUNTS ARE CACHED UNDER ONE KEY
    Cached separately, a request could serve a consented count from before a withdrawal
    beside a published count from after it. One key means one consistent pair.
"""

from __future__ import annotations

import contextlib
from typing import Any

from sqlalchemy import func, select

from app.constants import FILTERABLE_OUTCOMES, OUTCOME_LABELS, StatSource

#: Computed keys and what each counts. Every entry is consented-only; there is
#: deliberately no entry for a raw participant count, because nothing public shows one.
COMPUTED_KEYS: dict[str, str] = {
    "cohort_total": "consented",
    "cohort_consented": "consented",
    "cohort_published": "published",
}

_CACHE_KEY = "stats:counts"
EM_DASH = "—"


def _threshold() -> int:
    """§5.4's minimum, from config, with a safe default outside an app context."""
    try:
        from flask import current_app

        return int(current_app.config.get("STATS_SUPPRESS_BELOW", 5))
    except Exception:  # noqa: BLE001 — a unit test or a script, with no app
        return 5


def _timeout() -> int:
    try:
        from flask import current_app

        return int(current_app.config.get("STATS_CACHE_TIMEOUT", 300))
    except Exception:  # noqa: BLE001
        return 300


# ─────────────────────────────────────────────────────────────────────────────
# Counts
# ─────────────────────────────────────────────────────────────────────────────
def consented_count() -> int:
    """Participants who may be documented: consented, dated, not withdrawn.

    Note what is NOT required: `is_published`. This is the consented set, which is
    wider than the published set — a participant who agreed but is not yet listed is
    still part of the cohort we may talk about in aggregate.
    """
    from app.extensions import db
    from app.models import Participant

    stmt = select(func.count(Participant.id)).where(
        Participant.consent_publication.is_(True),
        Participant.consent_date.is_not(None),
        Participant.consent_withdrawn_at.is_(None),
    )
    return int(db.session.execute(stmt).scalar_one())


def published_count() -> int:
    from app.services.participant_service import count_published

    return count_published()


def _all_counts() -> dict[str, int]:
    from app.extensions import cache

    try:
        cached = cache.get(_CACHE_KEY)
    except Exception:  # noqa: BLE001 — no app context
        cached = None
    if isinstance(cached, dict):
        return cached

    counts = {"consented": consented_count(), "published": published_count()}
    # The cache is an OPTIMISATION. No app context, a read-only var/, a corrupted file —
    # all of those should cost speed, never a page. Failing a request over a cache would
    # invert the priority, so the failure is suppressed and the freshly computed counts
    # are returned instead.
    with contextlib.suppress(Exception):
        cache.set(_CACHE_KEY, counts, timeout=_timeout())
    return counts


def invalidate() -> None:
    """Drop the cached counts. MUST run in the same transaction as a participant write.

    A withdrawn participant whose count survives in a cache for 300 s is a privacy
    failure that no test would notice and no log would record. That is why the CALLER
    is required to be exact: this clears the cache where it can, and §5.4's 300 s
    timeout bounds the damage if it cannot. A withdrawal must not depend on a cache
    delete succeeding in order to be correct — it must depend on the publish flags and
    the database constraint, which it does.
    """
    from app.extensions import cache

    with contextlib.suppress(Exception):
        cache.delete(_CACHE_KEY)


# ─────────────────────────────────────────────────────────────────────────────
# Presentation
# ─────────────────────────────────────────────────────────────────────────────
def _display(key: str) -> str | None:
    """The value for a computed key, or None when it must be suppressed."""
    from app.filters import bn_num

    which = COMPUTED_KEYS.get(key)
    if which is None:
        return None

    counts = _all_counts()
    count = counts.get(which, 0)
    if count < _threshold():
        return None
    return bn_num(count)


def _to_view(stat) -> dict[str, Any]:
    """One stat in the shape `stat_strip` reads: label, value, unit, note."""
    if stat.source == StatSource.COMPUTED:
        return {
            "key": stat.key,
            "label": stat.label_bn,
            "value": _display(stat.key),
            "unit": stat.unit_bn,
            "note": None,
        }
    return {
        "key": stat.key,
        "label": stat.label_bn,
        # A manual stat's value is stored already in Bangla numerals (§7.4).
        "value": stat.value_bn,
        "unit": stat.unit_bn,
        "note": None,
    }


def strip_for_keys(keys: Any) -> list[dict[str, Any]]:
    """Stats for a `stat_strip`, in the order the section asked for them.

    A key that does not exist is SKIPPED rather than raising: a typo in a section
    payload should leave a gap in a strip, not take the page down. The publish gate is
    where a wrong key is meant to be caught (§11.2).
    """
    if not isinstance(keys, list) or not keys:
        return []

    from app.extensions import db
    from app.models import Stat

    wanted = [key for key in keys if isinstance(key, str)]
    if not wanted:
        return []

    rows = {
        stat.key: stat
        for stat in db.session.execute(select(Stat).where(Stat.key.in_(wanted))).scalars()
    }
    return [_to_view(rows[key]) for key in wanted if key in rows]


def table_by_keys(keys: Any) -> list[list[str]]:
    """Rows for `stat_table`: [label, value] with `—` where suppressed."""
    rows: list[list[str]] = []
    for view in strip_for_keys(keys):
        if view["value"] is None:
            rendered = EM_DASH
        elif view["unit"]:
            rendered = f"{view['value']} {view['unit']}"
        else:
            rendered = view["value"]
        rows.append([view["label"], rendered])
    return rows


def outcome_breakdown() -> tuple[list[str], list[list[str]]]:
    """The outcome table for the statistics page (§6.5). Returns (columns, rows).

    Only the FIVE filterable outcomes are listed. `other` is omitted on purpose: a
    bucket of "everything else" is neither useful to browse nor safe to show when it is
    small, which is exactly when it will be small.
    """
    from app.extensions import db
    from app.models import Participant
    from app.services.participant_service import published_only

    counts: dict[str, int] = {}
    for member in FILTERABLE_OUTCOMES:
        stmt = published_only(select(func.count(Participant.id))).where(
            Participant.outcome_type == member.value
        )
        counts[member.value] = int(db.session.execute(stmt).scalar_one())

    threshold = _threshold()
    rows: list[list[str]] = []
    total = 0
    for member in FILTERABLE_OUTCOMES:
        count = counts[member.value]
        total += count
        rows.append([OUTCOME_LABELS[member], EM_DASH if count < threshold else str(count)])
    rows.append(["মোট", EM_DASH if total < threshold else str(total)])
    return ["ফলাফল", "সংখ্যা"], rows
