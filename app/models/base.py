"""Model base classes and column helpers.

plan.md §10 ("every business table carries created_at / updated_at; admin-written
tables carry created_by / updated_by").

WHY AN enum_column HELPER
    ``db.Enum`` stores the enum *name* by default, not its value. For a StrEnum
    whose name and value differ (``HONOURS = "Honours"``) that would quietly write
    ``HONOURS`` to the database while every comparison in the application used
    ``"Honours"``. ``values_callable`` makes the stored value the one the rest of
    the code sees, and there is one place to get it right.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.extensions import Base, db  # noqa: F401 — Base is re-exported for the models


def utcnow() -> datetime:
    """Timezone-aware UTC now.

    ``datetime.utcnow()`` is deprecated in 3.12 and returns a naive value, which
    silently breaks comparisons against aware datetimes read back from the
    database. Stored naive-UTC for MySQL DATETIME compatibility, so strip on the
    way out of the DB and add the marker on the way in.
    """
    return datetime.now(UTC)


def enum_column(enum_cls: type[Enum], **kwargs: Any):
    """A column that stores an enum's VALUE, not its name."""
    kwargs.setdefault("nullable", False)
    return db.Column(
        db.Enum(
            enum_cls,
            values_callable=lambda e: [member.value for member in e],
            native_enum=True,
            validate_strings=True,
        ),
        **kwargs,
    )


class TimestampMixin:
    """created_at / updated_at on every business table."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AdminStampMixin:
    """created_by / updated_by on admin-written tables.

    FK to admin_users rather than a bare integer: with exactly one admin account
    (§12.1) a stray integer would be hard to notice and impossible to validate.
    ``ondelete="SET NULL"`` because the audit trail must outlive the account.
    """

    @declared_attr
    @classmethod
    def created_by(cls) -> Mapped[int | None]:
        return mapped_column(
            ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True, index=True
        )

    @declared_attr
    @classmethod
    def updated_by(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)


class SoftDeleteMixin:
    """Soft delete for anything a human might delete by mistake.

    §18.2: a withdrawn participant is unpublished, never deleted — the department
    needs the audit trail. The same reasoning applies to pages and sections: the
    row survives so the audit log's before/after diff still resolves.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = utcnow()

    def restore(self) -> None:
        self.deleted_at = None


class ModelMixin(TimestampMixin):
    """Timestamping plus a to_dict for the audit log's before/after diff.

    ``to_dict`` deliberately excludes secrets: an audit row must never become a
    place a password hash or a TOTP seed is readable.
    """

    #: Column names excluded from audit snapshots and from to_dict().
    __audit_exclude__: tuple[str, ...] = ()

    #: Supplied by the declarative base, not by this class: __table__ is created by
    #: SQLAlchemy's metaclass when the subclass is defined. Declared here so a type
    #: checker can resolve it, because `self.__table__` is otherwise an unknown
    #: attribute on a plain mixin.
    __table__: Any

    def to_dict(self, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
        skip = set(self.__audit_exclude__) | set(exclude)
        out: dict[str, Any] = {}
        for column in self.__table__.columns:
            if column.name in skip:
                continue
            value = getattr(self, column.name, None)
            if isinstance(value, datetime):
                value = value.isoformat()
            elif isinstance(value, Enum):
                value = value.value
            out[column.name] = value
        return out


__all__ = [
    "AdminStampMixin",
    "ModelMixin",
    "SoftDeleteMixin",
    "TimestampMixin",
    "db",
    "enum_column",
    "utcnow",
]
