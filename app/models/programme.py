"""What the React half of the site renders. plan.md §10.2, §11.3.

WHY THIS FILE EXISTS
    `frontend/src/data/mockData.ts` used to hold all of this — 94 KB of TypeScript
    constants baked into the bundle. That made the front end unmanageable: an operator
    could edit a course module in the CMS and the page would not change, because the
    page was reading a compiled constant. These four tables are those constants, moved
    into the database and given an editor.

WHY FOUR TABLES AND NOT ONE JSON BLOB
    Every one of them is a LIST that an operator reorders, hides, and corrects one row
    at a time. A single JSON document would make "hide this tool" a text edit of a
    larger document, and a malformed comma would take the whole page down. Each table
    is also independently orderable, which is what `sort_order` is for.

WHY THE BANGLA LABELS ARE COLUMNS AND NOT CONSTANTS
    `kind_label_bn`, `status_label_bn`, `hours_bn` and friends are DISPLAY strings —
    "১৪৪ ঘণ্টা", "বর্তমান", "সংগীত". They are columns because the operator has to be
    able to reword them without a deploy, which is the whole point of this module. This
    is the same §14.1 exception `Stat.value_bn` already documents: a formatted figure is
    stored because it is copy, not a measurement.

WHAT IS NOT HERE, AND WHY
    A photograph column for a PARTICIPANT. §5.1 lists photographs as never-published
    and the database has no column for one; the register renders initials instead of a
    face, and no amount of "but the mock data had avatarUrl" changes that (§22 Q4). The
    mock's 28 Unsplash URLs were placeholders of real strangers, which is worse than
    nothing: an invented face attached to a named person.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import InstructorStatus, WorkKind
from app.extensions import Base
from app.models.base import AdminStampMixin, ModelMixin, enum_column


class CoursePhase(ModelMixin, AdminStampMixin, Base):
    """One of the three phases the 13 modules are grouped into. Expected: 3 rows."""

    __tablename__ = "course_phases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(48), nullable=False, unique=True, index=True)
    #: The display number — "ফেজ ০১". Stored, because Bangla numerals are copy.
    phase_number_bn: Mapped[str] = mapped_column(String(32), nullable=False)
    title_bn: Mapped[str] = mapped_column(String(200), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hours_bn: Mapped[str | None] = mapped_column(String(48), nullable=True)
    days_bn: Mapped[str | None] = mapped_column(String(96), nullable=True)
    objective_bn: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools_count_bn: Mapped[str | None] = mapped_column(String(48), nullable=True)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    modules: Mapped[list["CourseModule"]] = relationship(  # noqa: F821
        back_populates="phase",
        order_by="CourseModule.sort_order",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<CoursePhase {self.slug}>"


class TrainingTool(ModelMixin, AdminStampMixin, Base):
    """A tool the programme teaches. Expected: 11 rows.

    The page that lists these groups them by `category_bn`, and the count above the
    grid is the number of ROWS — not a stored figure. A batch is deliberately NOT a
    column here: `Instructor.batch_bn` and `Participant.batch` both carry it, and a
    third copy on a tool would be a third thing to keep in step.
    """

    __tablename__ = "training_tools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: "০১" — the serial number as shown. Copy, so stored.
    sl_no_bn: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(96), nullable=False)
    category_bn: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description_bn: Mapped[str | None] = mapped_column(Text, nullable=True)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<TrainingTool {self.name}>"


class BatchWork(ModelMixin, AdminStampMixin, Base):
    """A piece of work the cohort produced. plan.md §10.3.

    `details` is JSON because its SHAPE depends on the work: a video has a synopsis,
    themes and tools; a music track has an audio duration; a document has excerpts.
    Four nullable columns would be three that are always empty, and a `details` blob
    that the admin edits as named sub-fields is the honest model of "varies by kind".
    """

    __tablename__ = "batch_works"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), nullable=False, unique=True, index=True)
    kind: Mapped[WorkKind] = enum_column(WorkKind, nullable=False, default=WorkKind.VIDEO)
    #: "ভিডিও", "পোস্টার" — the label the card shows. Editable, so a column.
    kind_label_bn: Mapped[str | None] = mapped_column(String(48), nullable=True)

    title_bn: Mapped[str] = mapped_column(String(240), nullable=False)
    meta_bn: Mapped[str | None] = mapped_column(String(240), nullable=True)
    duration_or_pages_bn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description_bn: Mapped[str | None] = mapped_column(Text, nullable=True)
    team_or_creator_bn: Mapped[str | None] = mapped_column(String(240), nullable=True)
    date_bn: Mapped[str | None] = mapped_column(String(96), nullable=True)
    aspect_ratio: Mapped[str | None] = mapped_column(String(24), nullable=True)

    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    #: The still, or the video's poster frame. A work with no image renders as a
    #: typographic card, which is a legitimate state rather than a broken one.
    media_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_items.id", ondelete="SET NULL"), nullable=True
    )
    media: Mapped["MediaItem | None"] = relationship(  # noqa: F821
        "MediaItem", foreign_keys=[media_id], lazy="joined"
    )
    batch: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, index=True)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<BatchWork {self.slug} ({self.kind})>"


class Instructor(ModelMixin, AdminStampMixin, Base):
    """A trainer. plan.md §10.4, §21 Q3.

    A TRAINER'S PHOTOGRAPH IS NOT A PARTICIPANT'S.
    §5.1's prohibition is about the people the programme trained; staff who teach in a
    public programme are named and photographed as part of doing the job. So this table
    HAS a photo reference — and the seed leaves it empty, because the only photographs
    to hand were placeholder URLs of real strangers, and an invented face attached to a
    named trainer is a misrepresentation rather than a placeholder. The page renders
    initials until an operator uploads the real photograph.
    """

    __tablename__ = "instructors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), nullable=False, unique=True, index=True)

    #: "০১" / "01" — the slide number the trainer's card is titled with.
    slide_number_bn: Mapped[str | None] = mapped_column(String(16), nullable=True)
    slide_number_en: Mapped[str | None] = mapped_column(String(16), nullable=True)

    status: Mapped[InstructorStatus] = enum_column(
        InstructorStatus, nullable=False, default=InstructorStatus.CURRENT
    )
    status_label_bn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tenure_bn: Mapped[str | None] = mapped_column(String(120), nullable=True)

    name_bn: Mapped[str] = mapped_column(String(160), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(160), nullable=True)
    designation_bn: Mapped[str | None] = mapped_column(String(200), nullable=True)
    credentials_bn: Mapped[str | None] = mapped_column(String(240), nullable=True)
    academic_bn: Mapped[str | None] = mapped_column(String(240), nullable=True)

    photo_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_items.id", ondelete="SET NULL"), nullable=True
    )
    photo: Mapped["MediaItem | None"] = relationship(  # noqa: F821
        "MediaItem", foreign_keys=[photo_id], lazy="joined"
    )

    quote_bn: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio_bn: Mapped[str | None] = mapped_column(Text, nullable=True)

    specialties_bn: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    contributions_bn: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    #: The three figures on the card. Copy, so stored as typed (§14.1's exception).
    hours_taught_bn: Mapped[str | None] = mapped_column(String(48), nullable=True)
    batch_bn: Mapped[str | None] = mapped_column(String(48), nullable=True)
    students_trained_bn: Mapped[str | None] = mapped_column(String(48), nullable=True)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_instructors_status_order", "status", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<Instructor {self.name_bn}>"


__all__ = ["BatchWork", "CoursePhase", "Instructor", "TrainingTool"]
