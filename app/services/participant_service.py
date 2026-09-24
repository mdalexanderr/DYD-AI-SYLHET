"""Participant publication filter and the public projection. plan.md §5, §6.4.

TWO RESPONSIBILITIES, AND BOTH ARE PRIVACY BOUNDARIES

  1. WHICH PARTICIPANTS MAY APPEAR
     `published_only()` is the single query every public surface must go through —
     the grid, the profile page, the counts and the sitemap. §5.3's rule is enforced
     in the model and at the database level, but those stop a row being WRITTEN as
     published. This is what stops an unpublished row being READ by mistake, and it is
     the layer that would catch a future `Participant.query.filter_by(batch=1)` typed
     in a hurry.

  2. WHICH FIELDS MAY LEAVE THE MODEL
     `to_card()` and `to_profile()` are allowlists, not `to_dict()`. A projection that
     copies whatever the model happens to have would leak a new column the day somebody
     adds one. Here, adding a field to `participants` changes nothing on the public
     site until somebody deliberately adds it to a projection below — which is the
     direction the failure has to point for a site publishing real people's names.

The `<5` suppression rule (§5.4, S6) lives in stats_service, not here, because it is
about aggregates rather than individuals.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from app.constants import (
    EDUCATION_LABELS,
    FILTERABLE_OUTCOMES,
    OUTCOME_LABELS,
    Education,
    OutcomeType,
)

#: Sort options a public list may use. `manual` is the seeded order (§6.4).
SORT_CHOICES = ("name", "recent", "manual")


def published_only(stmt):
    """Apply the publication filter to a `select()`.

    Four conditions, and all four are needed:
      is_published          — the flag the admin sets
      consent_publication   — permission was given
      consent_date is not null — and it was recorded, not merely asserted (§5.3 rule 3)
      consent_withdrawn_at is null — and it has not since been withdrawn (§5.3 rule 4)

    The database CHECK constraint covers the middle two for a row that is written as
    published. This is the read-side equivalent, and it also excludes a withdrawal
    that happened after publication.
    """
    from app.models import Participant

    return stmt.where(
        Participant.is_published.is_(True),
        Participant.consent_publication.is_(True),
        Participant.consent_date.is_not(None),
        Participant.consent_withdrawn_at.is_(None),
    )


def _order(stmt, sort: str):
    from app.models import Participant

    if sort == "name":
        return stmt.order_by(Participant.name_bn)
    if sort == "recent":
        return stmt.order_by(Participant.published_at.desc().nullslast(), Participant.id.desc())
    return stmt.order_by(Participant.batch, Participant.id)


def _search(stmt, query: str | None):
    """Filter by what the reader typed into §6.4's search box.

    Matches `search_blob` rather than `name_bn`, because that column is the one the
    model's hook keeps normalised for exactly this (it holds both the Bangla and the
    Latin spelling of a name), so a reader who cannot type Bangla can still find
    somebody.

    `%` and `_` are LIKE wildcards, so they are escaped and the escape character is
    declared. Without that, typing `%` would match the whole cohort — amusing once and
    then a bug report.
    """
    from app.models import Participant

    if not query or not isinstance(query, str):
        return stmt
    needle = query.strip().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    if not needle:
        return stmt
    return stmt.where(Participant.search_blob.like(f"%{needle}%", escape="\\"))


def list_published(
    *,
    limit: int | None = None,
    sort: str = "manual",
    outcome: str | None = None,
    offset: int | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Card views of published participants. The only list a public page may call.

    Returns projections, not model instances. Handing a template a `Participant` would
    give it `consent_notes` and `updated_by` as well, and a template is the one place
    nobody audits for what it could reach.

    `outcome` is applied through the SAME `published_only` statement as the consent
    filter, so a filter can never widen the result set past the publication rule — the
    failure mode being a filter bar that quietly lists people who never consented.
    """
    from app.extensions import db
    from app.models import Participant

    stmt = published_only(select(Participant))
    if outcome in FILTERABLE_OUTCOMES or outcome in {o.value for o in FILTERABLE_OUTCOMES}:
        stmt = stmt.where(Participant.outcome_type == outcome)
    stmt = _search(stmt, query)
    stmt = _order(stmt, sort)
    if offset:
        stmt = stmt.offset(offset)
    if limit:
        stmt = stmt.limit(int(limit))

    return [to_card(row) for row in db.session.execute(stmt).scalars()]


def count_published(outcome: str | None = None, query: str | None = None) -> int:
    """How many participants may be shown. Feeds the result count and the sitemap.

    Takes the same filters as `list_published` so the number a reader sees always
    describes the list they are looking at (§6.4), never the unfiltered cohort — an
    unfiltered total beside a filtered list is the kind of wrong that looks right.
    """
    from app.extensions import db
    from app.models import Participant

    stmt = published_only(select(func.count(Participant.id)))
    if outcome in {o.value for o in FILTERABLE_OUTCOMES}:
        stmt = stmt.where(Participant.outcome_type == outcome)
    stmt = _search(stmt, query)
    return int(db.session.execute(stmt).scalar_one())


def get_published(slug: str):
    """One published participant by slug, or None.

    Returns None for a non-consented slug AND for a slug that does not exist. Those
    two must be indistinguishable from outside, or the profile route becomes an oracle
    for who is in the cohort (§11.3's rule, applied to the public side).
    """
    from app.extensions import db
    from app.models import Participant

    if not slug or not isinstance(slug, str):
        return None
    stmt = published_only(select(Participant)).where(Participant.slug == slug)
    return db.session.execute(stmt).scalars().first()


def neighbours(participant) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(previous, next) published participants by id, for profile navigation (§5.5).

    Neighbours are computed over the PUBLISHED set, so prev/next never leads to a page
    that 404s — which is what would happen if the order came from the whole table.
    """
    from app.extensions import db
    from app.models import Participant

    def _one(direction: str):
        stmt = published_only(select(Participant))
        if direction == "prev":
            stmt = stmt.where(Participant.id < participant.id).order_by(Participant.id.desc())
        else:
            stmt = stmt.where(Participant.id > participant.id).order_by(Participant.id.asc())
        row = db.session.execute(stmt.limit(1)).scalars().first()
        if row is None:
            return None
        return {"slug": row.slug, "name_bn": row.name_bn}

    return _one("prev"), _one("next")


# ─────────────────────────────────────────────────────────────────────────────
# The public projection — an allowlist, deliberately not to_dict()
# ─────────────────────────────────────────────────────────────────────────────
def _meta_line(participant) -> list[str]:
    """The ruled meta line under a name: education, then previous occupation.

    Only these two, and only when set. §5.2 fixes exactly four publishable facts —
    name, education, occupation before, outcome after — and this is two of them.
    """
    parts: list[str] = []
    education = participant.education
    label = EDUCATION_LABELS.get(education)
    if label:
        parts.append(label)
    if participant.occupation_before:
        parts.append(participant.occupation_before)
    return parts


def _outcome_label(participant) -> str | None:
    if not participant.outcome_type:
        return None
    try:
        return OUTCOME_LABELS.get(OutcomeType(participant.outcome_type))
    except ValueError:
        return None


def to_card(participant) -> dict[str, Any]:
    """The shape `participant_card` expects. Four facts, nothing else."""
    return {
        "slug": participant.slug,
        "href": f"/batch-1/{participant.slug}",
        "name_bn": participant.name_bn,
        "name_en": participant.name_en,
        "meta": _meta_line(participant),
        "outcome_text": participant.outcome_text,
        "outcome_label": _outcome_label(participant),
    }


def to_profile(participant, *, prev=None, next_=None) -> dict[str, Any]:
    """The profile-page projection (§5.5).

    Every key here is a deliberate decision about what a member of the public may see
    about a named person. `consent_source`, `consent_notes`, `search_blob`, `batch`
    internals and the whole audit trail are absent on purpose — they are administrative
    records about a person, not facts about their training.
    """
    card = to_card(participant)
    card.update(
        {
            "education_label": EDUCATION_LABELS.get(participant.education),
            "occupation_before": participant.occupation_before,
            "outcome_text": participant.outcome_text,
            "outcome_label": _outcome_label(participant),
            # §5.3 rule 5: a quote appears only if it has its OWN permission. A
            # consented participant who did not consent to being quoted has the text
            # stored but not published.
            "quote_bn": participant.quote_bn if participant.quote_consented else None,
            "published_at": participant.published_at,
            "prev": prev,
            "next": next_,
        }
    )
    return card


def batch_line(participant) -> str:
    """The footer identity line: `ব্যাচ ১ · সিলেট BUTTC` (§5.5).

    Uses the bn_num filter rather than a local digit map, so the one place that knows
    how to render a numeral in Bangla stays the one place.
    """
    from app.filters import bn_num

    return f"ব্যাচ {bn_num(participant.batch or 1)} · সিলেট BUTTC"


#: Every education level, for the filter bar (§6.4). Kept here so the route does not
#: have to know about the enum.
def education_choices() -> list[tuple[str, str]]:
    return [(member.value, EDUCATION_LABELS[member]) for member in Education]


def outcome_choices() -> list[tuple[str, str]]:
    """The FIVE filterable outcomes. `other` is deliberately not offered (§6.4)."""
    return [(member.value, OUTCOME_LABELS[member]) for member in FILTERABLE_OUTCOMES]
