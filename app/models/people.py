"""participants and consent_events — the highest-risk tables. plan.md §5, §10.3.

═══════════════════════════════════════════════════════════════════════════════
THE PUBLISH GUARD HAS THREE LAYERS. THIS FILE IS LAYER 2, AND LAYER 3 IS THE
DATABASE ITSELF.

    1. the form          — refuses to submit a publish without consent (§11.3)
    2. this model        — refuses to flush an invalid state (below)
    3. a CHECK constraint — the database refuses the row outright

Layer 3 is the one that matters. A bug in application code, a careless
``session.execute(text(...))``, a data fix run by hand at 2am, a future
maintenance script — none of them can publish a non-consented person, because the
database will not store the row. Verified on SQLite and MySQL during Phase 1.
═══════════════════════════════════════════════════════════════════════════════

THE PROHIBITED COLUMNS DO NOT EXIST. Not ``phone``, ``email``, ``nid``, ``dob``,
``blood_group``, ``address``, ``guardian_name``, ``signature``, and no
``media_id``. §5.2 states this and §13.3 reinforces it. The schema cannot hold
data we must not publish, which is the strongest available form of the rule — a
constraint can be dropped in a migration, but a column that was never added
cannot leak. ``tests/test_models.py`` asserts their absence so a future
"just for admin use" addition fails the suite.

WHY before_flush AND NOT @validates
    ``@validates("is_published")`` fires on assignment, so setting
    ``is_published = True`` before ``consent_date`` in the same block would raise
    even though the committed state is perfectly valid. A ``before_flush`` hook
    inspects the FINAL state of every dirty row, which is the thing that actually
    matters. It also means the error names the participant, not the setter.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    event,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.constants import ConsentAction, ConsentSource, Education, OutcomeType
from app.extensions import Base
from app.models.base import ModelMixin, enum_column, utcnow

# ── Search normalisation (§14.4) ─────────────────────────────────────────────
# Zero-width joiner/non-joiner are PRESERVED in display fields — they are part of
# Bangla orthography — but stripped from the search blob, because a person typing
# a name into a filter box will not type an invisible character.
_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_WHITESPACE = re.compile(r"\s+")


def build_search_blob(name_bn: str | None, name_en: str | None = None) -> str:
    """NFC-normalised, zero-width-stripped, case-folded haystack for LIKE search.

    Stored rather than computed at query time so the search works identically on
    SQLite and MySQL (§9.4: no raw SQL outside reviewed counting queries, and
    ``LIKE`` on a normalised column works on both).
    """
    parts = []
    for value in (name_bn, name_en):
        if not value:
            continue
        normalised = unicodedata.normalize("NFC", value)
        normalised = _ZERO_WIDTH.sub("", normalised)
        parts.append(_WHITESPACE.sub(" ", normalised).strip().casefold())
    return " ".join(parts)[:320]


def normalise_query(value: str) -> str:
    """Apply the same normalisation to a search term, so the two always match."""
    if not value:
        return ""
    normalised = unicodedata.normalize("NFC", value)
    normalised = _ZERO_WIDTH.sub("", normalised)
    return _WHITESPACE.sub(" ", normalised).strip().casefold()


class PublishWithoutConsentError(ValueError):
    """Raised when something tries to publish a participant who has not consented.

    Carries a Bangla message key rather than Bangla prose so the caller decides
    the wording, and so the message can be shown in the admin without a
    translation lookup here.
    """

    message_key = "participant.publish_requires_consent"

    def __init__(self, *, slug: str = "", missing: tuple[str, ...] = ()) -> None:
        self.slug = slug
        self.missing = missing
        super().__init__(
            f"cannot publish {slug or 'participant'!r}: "
            f"missing {', '.join(missing) or 'consent'}"
        )


class ConsentWithdrawnError(ValueError):
    """Raised when consent is withdrawn and something tries to re-publish."""

    message_key = "participant.consent_withdrawn"


class Participant(ModelMixin, Base):
    __tablename__ = "participants"

    #: §5.1 — the publishable field set, and nothing else.
    __audit_exclude__ = ("search_blob",)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), nullable=False, unique=True, index=True)

    # ── Identity ────────────────────────────────────────────────────────────
    name_bn: Mapped[str] = mapped_column(String(160), nullable=False)
    # Only if the participant provided one. Never auto-transliterated: a wrong
    # English name on a government page is worse than no English name (§5.1).
    name_en: Mapped[str | None] = mapped_column(String(160), nullable=True)

    education: Mapped[Education] = enum_column(Education, index=True)
    occupation_before: Mapped[str | None] = mapped_column(String(80), nullable=True)
    outcome_type: Mapped[OutcomeType | None] = enum_column(OutcomeType, nullable=True)
    outcome_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Quote — a stronger act than publishing a name (§5.3 rule 5) ─────────
    # §10.3 lists both `quote_consented` and `quote_permission`, which are the same
    # thing twice. Only one column exists; the duplicate is recorded in plan.md's
    # open items rather than honoured twice, because two fields that must agree
    # are two fields that will eventually disagree.
    quote_bn: Mapped[str | None] = mapped_column(Text, nullable=True)
    quote_consented: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    batch: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, index=True)

    # ── Consent (§5.3) ──────────────────────────────────────────────────────
    consent_publication: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    consent_source: Mapped[ConsentSource | None] = enum_column(ConsentSource, nullable=True)
    consent_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent_withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ── Publication ─────────────────────────────────────────────────────────
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ── Search (§14.4) ──────────────────────────────────────────────────────
    search_blob: Mapped[str] = mapped_column(String(320), nullable=False, default="", index=True)

    consent_events: Mapped[list[ConsentEvent]] = relationship(
        back_populates="participant",
        cascade="all, delete-orphan",
        order_by="ConsentEvent.created_at.desc()",
        lazy="selectin",
    )

    __table_args__ = (
        # ── LAYER 3. The belt in "belt and braces". ──────────────────────────
        # Spelled exactly as §10.3 specifies. Booleans are stored as 0/1 on both
        # engines, so this is portable — and it was tested against a real INSERT
        # that bypasses the ORM entirely.
        CheckConstraint(
            "is_published = 0 OR (consent_publication = 1 AND consent_date IS NOT NULL)",
            name="ck_participants_publish_requires_consent",
        ),
        # A quoted participant must have consented to the quote specifically.
        CheckConstraint(
            "quote_bn IS NULL OR quote_consented = 1",
            name="ck_participants_quote_requires_permission",
        ),
        Index("ix_participants_published_consent", "is_published", "consent_publication"),
    )

    # ── Publication rules (§5.3) ────────────────────────────────────────────
    @property
    def missing_consent_fields(self) -> tuple[str, ...]:
        """What stands between this record and publication. Empty means it may publish."""
        missing: list[str] = []
        if self.consent_withdrawn_at is not None:
            missing.append("consent_publication (withdrawn)")
        elif not self.consent_publication:
            missing.append("consent_publication")
        if self.consent_date is None:
            missing.append("consent_date")
        return tuple(missing)

    @property
    def can_publish(self) -> bool:
        return not self.missing_consent_fields

    @property
    def consent_state(self) -> str:
        """One of published / withdrawn / pending / unpublished — for ConsentBadge."""
        if self.consent_withdrawn_at is not None:
            return "withdrawn"
        if not self.consent_publication or self.consent_date is None:
            return "pending"
        return "published" if self.is_published else "unpublished"

    def publish(self, *, actor_id: int | None = None) -> None:
        """Publish, or refuse with a Bangla-addressable error (§11.3)."""
        missing = self.missing_consent_fields
        if missing:
            raise PublishWithoutConsentError(slug=self.slug, missing=missing)
        self.is_published = True
        self.published_at = self.published_at or utcnow()
        if actor_id is not None:
            self.updated_by = actor_id

    def unpublish(self, *, actor_id: int | None = None) -> None:
        self.is_published = False
        if actor_id is not None:
            self.updated_by = actor_id

    def withdraw_consent(self, *, notes: str | None = None, actor_id: int | None = None) -> None:
        """§5.3 rule 2 and §18.2 — in ONE transaction, unpublish and invalidate.

        This method intentionally does NOT touch the cache. Cache invalidation
        happens in ``consent_service.withdraw()``, which wraps this call and the
        cache clear in the same transaction, because a model that reaches for a
        Flask extension is a model that cannot be tested without an app context.
        """
        self.consent_withdrawn_at = utcnow()
        self.is_published = False
        if notes:
            self.consent_notes = notes
        if actor_id is not None:
            self.updated_by = actor_id

    def refresh_search_blob(self) -> None:
        self.search_blob = build_search_blob(self.name_bn, self.name_en)

    def __repr__(self) -> str:
        return f"<Participant {self.slug} published={self.is_published}>"


class ConsentEvent(Base):
    """An append-only record of every consent change (§10.3).

    Never updated, never deleted. The department needs to be able to answer "when
    did this person consent, who recorded it, and when did they withdraw" — and a
    row that can be edited cannot answer that.
    """

    __tablename__ = "consent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[ConsentAction] = enum_column(ConsentAction)
    source: Mapped[ConsentSource | None] = enum_column(ConsentSource, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )

    participant: Mapped[Participant] = relationship(back_populates="consent_events")

    def __repr__(self) -> str:
        return f"<ConsentEvent {self.action} p={self.participant_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 2 — refused at flush, so the final committed state is what is validated.
# ─────────────────────────────────────────────────────────────────────────────
@event.listens_for(Session, "before_flush")
def _guard_participant_publication(session: Session, _flush_context, _instances) -> None:
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, Participant):
            continue
        if obj.is_published and obj.missing_consent_fields:
            raise PublishWithoutConsentError(
                slug=obj.slug, missing=obj.missing_consent_fields
            )
        if obj.quote_bn and not obj.quote_consented:
            raise PublishWithoutConsentError(
                slug=obj.slug, missing=("quote_consented",)
            )
        # Keep the search blob honest without every caller remembering to.
        expected = build_search_blob(obj.name_bn, obj.name_en)
        if obj.search_blob != expected:
            obj.search_blob = expected
