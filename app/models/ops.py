"""Operational tables — contact_messages, audit_logs, imports, login_attempts, backups.

plan.md §10.5. These five share a property the other twelve do not: nothing in
this file is content. They are records *about* the system, they are never shown to
the public, and each has a retention rule (§12.4, §17.6) except ``audit_logs`` and
``backups``, which are kept longer on purpose.

WHY audit_logs IS APPEND-ONLY
    §12.1 requires "every write with a before/after diff". A log that can be
    updated is a log that can be made to say something else — including by the
    single admin account it exists to hold to account. Nothing in the application
    updates or deletes an audit row except the retention sweep, which deletes by
    age and by age only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import (
    BackupKind,
    BackupStatus,
    ImportKind,
    ImportStatus,
    MessageStatus,
)
from app.extensions import Base
from app.models.base import ModelMixin, enum_column, utcnow


class ContactMessage(ModelMixin, Base):
    """A public contact-form submission. Purged after 12 months (§12.4).

    ``ip`` is stored for abuse investigation and is part of what the retention
    sweep removes — it is personal data with no long-term purpose here.
    """

    __tablename__ = "contact_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)

    status: Mapped[MessageStatus] = enum_column(MessageStatus, default=MessageStatus.NEW, index=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_contact_messages_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ContactMessage {self.id} {self.status}>"


class AuditLog(Base):
    """Append-only. Every admin mutation, with a before/after diff (§12.1).

    Written INSIDE the same transaction as the change it describes, so a rolled
    back change leaves no row. An audit log that records attempts rather than
    outcomes is worse than none, because it implies a precision it does not have.
    """

    __tablename__ = "audit_logs"

    # `with_variant(Integer, "sqlite")` IS NOT COSMETIC — IT IS THE DIFFERENCE
    # BETWEEN THIS TABLE WORKING AND RENDERING THE WHOLE AUDIT LOG UNWRITABLE.
    # SQLite autoincrements only an exactly-`INTEGER PRIMARY KEY`. A `BIGINT`
    # primary key gets no rowid alias, so any insert that omits the id fails with
    # "NOT NULL constraint failed: audit_logs.id". MySQL is perfectly happy with
    # BIGINT, so this is invisible in production and fatal in development and in the
    # entire test suite — the worst possible split, because it makes every audit
    # write look like a test defect rather than a schema bug. It shipped unnoticed
    # through Phase 2 because nothing wrote an audit row until step 4.1 logged a
    # login. BIGINT is kept for MySQL because the audit log is the one table
    # expected to grow without bound.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )

    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
    )

    def diff_keys(self) -> list[str]:
        """Which fields actually changed — for the admin's diff view (step 6.13)."""
        before = self.before_json or {}
        after = self.after_json or {}
        return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.entity_type}:{self.entity_id}>"


class Import(ModelMixin, Base):
    """One CSV import run, dry or committed (§11.4).

    The dry run writes a row too. A dry run that leaves no trace is a dry run
    nobody can prove happened after a mistaken commit.
    """

    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[ImportKind] = enum_column(ImportKind, default=ImportKind.PARTICIPANTS)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[ImportStatus] = enum_column(ImportStatus, default=ImportStatus.DRY_RUN)
    column_map: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )

    __table_args__ = (
        Index("ix_imports_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Import {self.id} {self.status} {self.success_rows}/{self.total_rows}>"


class LoginAttempt(ModelMixin, Base):
    """Every login success and failure (§12.1).

    Kept because "the admin definitely did not log in at 3am" is a question that
    can only be answered with a record of the attempts, not just the successes.
    """

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    was_successful: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[str | None] = mapped_column(String(48), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )

    __table_args__ = (
        Index("ix_login_attempts_ip_created", "ip", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<LoginAttempt {self.email} ok={self.was_successful}>"


class Backup(ModelMixin, Base):
    """A backup artefact. ``expires_at`` drives the retention sweep (§17.6)."""

    __tablename__ = "backups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[BackupKind] = enum_column(BackupKind, default=BackupKind.FULL)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[BackupStatus] = enum_column(BackupStatus, default=BackupStatus.RUNNING)
    offsite_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    def __repr__(self) -> str:
        return f"<Backup {self.filename} {self.status}>"


__all__ = ["AuditLog", "Backup", "ContactMessage", "Import", "LoginAttempt"]
