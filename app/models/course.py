"""Course and institution tables. plan.md §10.4, §3.2.

ONE INSTITUTION (§3.2). The site documents a single institute — Sylhet BUTTC —
and there is no administrative-geography dimension at all: no division level, no
sub-division level, no multi-centre split. The ``institutions`` table exists as a
table rather than a set of settings so the Course and About pages can reference it
by FK and the admin can edit it as a record, not so a second one can be added.
Adding a second is a scope change (§2.2, S7).

The institution's name and address are Q2 in §22 and MUST be confirmed before the
Course and About pages go live (R11). Seed data carries the supplied value
verbatim and expands nothing.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Base
from app.models.base import AdminStampMixin, ModelMixin


class Course(ModelMixin, AdminStampMixin, Base):
    """The programme as delivered in Sylhet. Exactly one row."""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), nullable=False, unique=True, index=True)
    title_bn: Mapped[str] = mapped_column(String(240), nullable=False)
    summary_bn: Mapped[str | None] = mapped_column(Text, nullable=True)

    duration_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    duration_hours: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    hours_per_day: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    certification_note_bn: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Q1 in §22. Nullable because the real dates may not be known at build time;
    # the CMS makes them editable, and the pages render around a missing date
    # rather than showing a placeholder that looks like a fact.
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    modules: Mapped[list[CourseModule]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="CourseModule.sort_order",
        lazy="selectin",
    )

    @property
    def total_module_hours(self) -> int:
        return sum(m.hours or 0 for m in self.modules)

    def __repr__(self) -> str:
        return f"<Course {self.slug}>"


class CourseModule(ModelMixin, Base):
    """One curriculum unit. Order is meaningful — this is a syllabus."""

    __tablename__ = "course_modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title_bn: Mapped[str] = mapped_column(String(200), nullable=False)
    description_bn: Mapped[str | None] = mapped_column(Text, nullable=True)
    hours: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # A slug into the icon sprite, not a file path: there is one sprite (§7.6.1)
    # and a free-text path would eventually point at a file that does not exist.
    icon_slug: Mapped[str | None] = mapped_column(String(48), nullable=True)

    course: Mapped[Course] = relationship(back_populates="modules")

    __table_args__ = (
        Index("ix_course_modules_course_order", "course_id", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<CourseModule {self.title_bn[:28]!r}>"


class Institution(ModelMixin, AdminStampMixin, Base):
    """Sylhet BUTTC and the partner entity. Expected row count: 1 (§3.2)."""

    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), nullable=False, unique=True, index=True)
    name_bn: Mapped[str] = mapped_column(String(240), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(240), nullable=True)
    role_bn: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address_bn: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    map_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description_bn: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_items.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Institution {self.name_bn}>"


__all__ = ["Course", "CourseModule", "Institution"]
