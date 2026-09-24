"""admin_users — the single admin account. plan.md §10.1, §12.1.

There is NO role column. There is no second account. Every authorisation check in
this application is "is this the admin, and are they logged in" — so there is
nothing here for a permissions matrix to get wrong.

The password hash and the TOTP seed are both marked ``__audit_exclude__``: an
audit row must never become a place a credential is readable, and the audit log is
shown in the admin UI.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from flask_login import UserMixin
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base
from app.models.base import ModelMixin, utcnow


class AdminUser(UserMixin, ModelMixin, Base):
    __tablename__ = "admin_users"
    __audit_exclude__ = ("password_hash", "twofa_secret", "recovery_codes")

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name_bn: Mapped[str] = mapped_column(String(160), nullable=False, default="")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    twofa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Fernet-encrypted with a key derived from SECRET_KEY. Never plaintext: a
    # database dump would otherwise hand over the second factor (§12.1).
    twofa_secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # JSON list of single-use recovery codes, hashed. Shown once at enrolment.
    recovery_codes: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ── Lockout (§12.1: 3 attempts / 10 min, then a 30-minute lock) ──────────
    @property
    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > utcnow().replace(tzinfo=None)

    def register_failure(self, max_attempts: int, lockout_minutes: int) -> bool:
        """Count a failed login. Returns True if this locked the account."""
        self.failed_attempts = (self.failed_attempts or 0) + 1
        if self.failed_attempts >= max_attempts:
            self.locked_until = utcnow().replace(tzinfo=None) + timedelta(minutes=lockout_minutes)
            return True
        return False

    def register_success(self, ip: str | None = None) -> None:
        self.failed_attempts = 0
        self.locked_until = None
        self.last_login_at = utcnow()
        self.last_login_ip = ip

    @property
    def locked_minutes_remaining(self) -> int:
        if not self.is_locked or self.locked_until is None:
            return 0
        delta = self.locked_until - utcnow().replace(tzinfo=None)
        return max(0, int(delta.total_seconds() // 60) + 1)

    def __repr__(self) -> str:
        return f"<AdminUser {self.email}>"
