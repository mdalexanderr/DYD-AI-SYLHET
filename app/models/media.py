"""media_items — the shared media library. plan.md §10.5, §13.

NO PARTICIPANT PHOTOGRAPHS. A participant has no media reference and the file has
no `owner_participant_id`. Training-session photographs live here and may appear
in the gallery, but never captioned with a participant's full name (§13.3).

``used_count`` is not a cache — it is a safety mechanism. §13.2 requires that an
image still in use cannot be deleted, because deleting one breaks a published
block on a public page. It is maintained by ``media_service`` on save and remove.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import MediaKind
from app.extensions import Base
from app.models.base import ModelMixin, enum_column


class MediaItem(ModelMixin, Base):
    __tablename__ = "media_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Relative to UPLOAD_ROOT, which is OUTSIDE the webroot. Never an absolute
    # path: the deploy target differs from the development machine.
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime: Mapped[str | None] = mapped_column(String(96), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    kind: Mapped[MediaKind] = enum_column(MediaKind, default=MediaKind.IMAGE)
    # Video is by LINK ONLY, never a hosted file (§13.2).
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Required on save (§13.2). Nullable at the database level because a migration
    # has to be able to backfill; the service refuses a save without it, and the
    # admin form shows it as required.
    alt_bn: Mapped[str | None] = mapped_column(String(300), nullable=True)
    caption_bn: Mapped[str | None] = mapped_column(String(300), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)

    @property
    def aspect_ratio(self) -> str | None:
        """CSS-ready ratio, so a template never has to divide."""
        if not self.width or not self.height:
            return None
        return f"{self.width} / {self.height}"

    @property
    def is_image(self) -> bool:
        return self.kind == MediaKind.IMAGE

    @property
    def extension(self) -> str:
        return (self.path.rsplit(".", 1)[-1] if "." in self.path else "").lower()

    def to_view(self) -> dict[str, Any]:
        """The shape the ``media_figure`` macro expects.

        Building it here keeps the macro ignorant of the storage layout, and gives
        one place to change if the URL scheme changes.
        """
        return {
            "kind": self.kind.value,
            "path": self.path,
            "url": f"/media/{self.path}",
            "external_url": self.external_url,
            "alt_bn": self.alt_bn or "",
            "caption_bn": self.caption_bn,
            "width": self.width,
            "height": self.height,
        }

    def __repr__(self) -> str:
        return f"<MediaItem {self.path}>"


__all__ = ["Boolean", "MediaItem"]
