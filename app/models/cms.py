"""CMS tables — pages, page_sections, faqs, stats, settings. plan.md §10.2, §16.2.

RESERVED-WORD COLUMNS
    ``stats.key``, ``settings.key`` and ``settings.group`` are reserved words in
    MySQL. SQLAlchemy quotes them automatically, so the ORM is fine — but any raw
    SQL added later MUST quote them (`` `key` ``). The plan names them; they are
    kept as named rather than silently renamed, because a rename would make the
    schema disagree with the document that describes it.

SECRETS ARE NOT SETTINGS
    ``settings.value`` is TEXT and holds site copy, hotline numbers, feature
    toggles — never a credential. ``is_secret`` marks a row whose *display* is
    write-only and whose real value lives in ``.env`` (§16.2). ``SettingsService``
    refuses to write a value for a secret key, and step 6.10 asserts it.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import SectionType, SettingValueType, StatSource
from app.extensions import Base
from app.models.base import AdminStampMixin, ModelMixin, enum_column, utcnow


class Page(ModelMixin, AdminStampMixin, Base):
    """One public page, composed of ordered sections (§4.3)."""

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(96), nullable=False, unique=True, index=True)
    title_bn: Mapped[str] = mapped_column(String(200), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nav_label_bn: Mapped[str | None] = mapped_column(String(80), nullable=True)

    show_in_nav: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    meta_description_bn: Mapped[str | None] = mapped_column(String(320), nullable=True)
    og_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_items.id", ondelete="SET NULL"), nullable=True
    )

    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)

    sections: Mapped[list[PageSection]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="PageSection.sort_order",
        lazy="selectin",
    )

    #: Slugs are Latin, lowercase, hyphenated and stable forever (§4.3). Bangla
    #: lives in labels only, so a URL survives a copy rewrite.
    __table_args__ = (
        Index("ix_pages_nav_order", "show_in_nav", "sort_order"),
    )

    @property
    def visible_sections(self) -> list[PageSection]:
        """Only what will actually render.

        §9.3 rule 4: ``is_visible = false`` sections are SKIPPED, not hidden with
        CSS. Returning them here would invite a template to render and hide them.

        There is deliberately no soft-delete check. A section is hard-deleted (the
        relationship cascades with `delete-orphan`), so it has no `deleted_at`
        column — an earlier version of this property filtered on one anyway, which
        would have raised AttributeError the first time a page was rendered.
        """
        return [s for s in self.sections if s.is_visible]

    @property
    def can_publish(self) -> tuple[bool, str]:
        """The publish gate (§11.2). Returns (allowed, reason).

        A page cannot publish if it has no visible sections — an empty page is
        worse than a draft, because it looks like the site is broken.
        """
        visible = self.visible_sections
        if not visible:
            return False, "পৃষ্ঠাটি প্রকাশ করা যায় না: কোনো দৃশ্যমান সেকশন নেই।"
        for section in visible:
            ok, reason = section.validate_payload()
            if not ok:
                return False, f"{section.type_label} সেকশনে সমস্যা: {reason}"
        return True, ""

    def publish(self) -> None:
        self.is_published = True
        self.published_at = utcnow()

    def __repr__(self) -> str:
        return f"<Page {self.slug} published={self.is_published}>"


class PageSection(ModelMixin, Base):
    """One block within a page. ``content`` is JSON validated per type (§9.3)."""

    __tablename__ = "page_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_id: Mapped[int] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # VARCHAR(32), not a DB enum: an unknown type must RAISE and be reported, not
    # be silently rejected by the database at insert time (§9.3 rule 1). The set
    # of valid types is enforced by the section registry, which can give a better
    # error than a CHECK constraint can.
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )

    page: Mapped[Page] = relationship(back_populates="sections")

    __table_args__ = (
        Index("ix_page_sections_page_order", "page_id", "sort_order"),
    )

    @property
    def type_label(self) -> str:
        from app.constants import SECTION_TYPE_LABELS

        return SECTION_TYPE_LABELS.get(self.type, self.type)

    def validate_payload(self) -> tuple[bool, str]:
        """Validate ``content`` against the schema for this type (§9.3).

        Imported lazily: the section registry imports the models, so a module-level
        import here would be circular.
        """
        from app.sections.registry import validate_section

        return validate_section(self.type, self.content or {})

    def __repr__(self) -> str:
        return f"<PageSection {self.type} page={self.page_id} order={self.sort_order}>"


class Faq(ModelMixin, Base):
    __tablename__ = "faqs"
    __audit_exclude__ = ()

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    question_bn: Mapped[str] = mapped_column(String(400), nullable=False)
    answer_bn: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    def __repr__(self) -> str:
        return f"<Faq {self.question_bn[:30]!r}>"


class Stat(ModelMixin, Base):
    """A labelled figure used by stat strips and the cohort summary (§5.4).

    ``value_bn`` is the DISPLAY form (Bangla numerals, units as written);
    ``value_num`` is optional and only for computed figures that need arithmetic
    or sorting. Numbers are formatted at render, never stored formatted (§14.1) —
    ``value_bn`` is the exception, and it is explicitly the display string.
    """

    __tablename__ = "stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    label_bn: Mapped[str] = mapped_column(String(160), nullable=False)
    value_bn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    value_num: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit_bn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[StatSource] = enum_column(StatSource, default=StatSource.MANUAL)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)

    def __repr__(self) -> str:
        return f"<Stat {self.key}={self.value_bn!r}>"


class Setting(ModelMixin, Base):
    """Site-wide key/value configuration the admin may edit (§16.2)."""

    __tablename__ = "settings"
    __audit_exclude__ = ()

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(96), nullable=False, unique=True, index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_type: Mapped[SettingValueType] = enum_column(
        SettingValueType, default=SettingValueType.STRING
    )
    group: Mapped[str] = mapped_column(String(48), nullable=False, default="general", index=True)
    label_bn: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("key", name="uq_settings_key"),
    )

    def typed_value(self) -> Any:
        """The value as its declared type, with a safe fallback on junk.

        A malformed value must not take the site down: a setting is admin-editable
        and an admin will eventually paste something wrong.
        """
        raw = self.value
        try:
            if self.value_type == SettingValueType.INT:
                return int(raw) if raw not in (None, "") else 0
            if self.value_type == SettingValueType.BOOL:
                return str(raw).strip().lower() in {"1", "true", "yes", "on"}
            if self.value_type == SettingValueType.JSON:
                return json.loads(raw) if raw else {}
        except (ValueError, TypeError, json.JSONDecodeError):
            return {"string": "", "int": 0, "bool": False, "json": {}}[self.value_type.value]
        return raw or ""

    def __repr__(self) -> str:
        return f"<Setting {self.key}>"


__all__ = ["Faq", "Page", "PageSection", "SectionType", "Setting", "Stat"]
