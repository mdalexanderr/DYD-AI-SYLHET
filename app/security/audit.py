"""Audit writing. plan.md §12.1 ("every write with a before/after diff").

THE ONE RULE: THIS MODULE NEVER COMMITS.
    The audit row must be written in the SAME transaction as the change it
    describes, so that a rolled-back change leaves no row. If this helper
    committed, the audit log would record attempts rather than outcomes — it would
    claim changes that never happened, which is worse than having no log at all,
    because it implies a precision it does not have.

    Step 4.7 asserts exactly this: a rolled-back change leaves no audit row.

WHAT IS RECORDED
    Actor, action, entity type and id, before/after snapshots, and the IP. Secrets
    are excluded by each model's ``__audit_exclude__`` (models/base.py) — the audit
    log is displayed in the admin UI (step 6.13), so a password hash or a TOTP seed
    surviving into it would be readable by anyone who reached the admin.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from flask import has_request_context, request
from flask_login import current_user

from app.extensions import db
from app.models.ops import AuditLog


def _current_actor_id() -> int | None:
    """The logged-in admin's id, or None for a CLI or unauthenticated write.

    ``current_user`` raises outside a request context, and a seed run legitimately
    writes without an actor. Returning None rather than raising keeps the audit
    helper usable from the CLI, where "who did this" genuinely has no answer yet —
    ``flask seed`` runs before the admin account exists.
    """
    if not has_request_context():
        return None
    with suppress(Exception):
        if getattr(current_user, "is_authenticated", False):
            return int(current_user.get_id())
    return None


def _current_ip() -> str | None:
    if not has_request_context():
        return None
    # X-Forwarded-For is only meaningful behind a proxy that sets it. Passenger
    # does, and the app is not reachable directly. The left-most entry is the
    # client; the rest are proxies.
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return (request.remote_addr or None)


def snapshot(obj: Any) -> dict[str, Any] | None:
    """A dict of a model instance, minus its excluded secrets."""
    if obj is None:
        return None
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        # Pinned to an annotated local: `to_dict` is reached through getattr, so its
        # result is `Any`, and `Any` returned from a function that declares a
        # concrete type silently disables checking at every call site.
        result: dict[str, Any] = to_dict()
        return result
    return None


def record(
    action: str,
    *,
    entity: Any = None,
    entity_type: str | None = None,
    entity_id: Any = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    actor_id: int | None = None,
    ip: str | None = None,
    extra: dict[str, Any] | None = None,
) -> AuditLog:
    """Add an audit row to the session. Does NOT commit — see the module docstring.

    Call it immediately before the caller's ``db.session.commit()``:

        before = audit.snapshot(page)
        page.title_bn = form.title_bn.data
        audit.record(AuditAction.UPDATE, entity=page, before=before,
                     after=audit.snapshot(page))
        db.session.commit()          # one transaction, one outcome
    """
    if entity is not None:
        entity_type = entity_type or type(entity).__name__
        entity_id = entity_id if entity_id is not None else getattr(entity, "id", None)

    resolved_after = after
    if resolved_after is None and entity is not None:
        resolved_after = snapshot(entity)

    if extra:
        resolved_after = {**(resolved_after or {}), "_extra": extra}

    row = AuditLog(
        actor_id=actor_id if actor_id is not None else _current_actor_id(),
        action=str(action),
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        before_json=before,
        after_json=resolved_after,
        ip=ip or _current_ip(),
    )
    db.session.add(row)
    return row


def record_login(*, email: str, successful: bool, reason: str | None = None,
                 ip: str | None = None) -> AuditLog:
    """A login success or failure. No entity — the subject is the account itself."""
    return record(
        "login_ok" if successful else "login_fail",
        entity_type="AdminUser",
        entity_id=email,
        before=None,
        after={"email": email, "successful": successful, "reason": reason},
        ip=ip,
    )


__all__ = ["record", "record_login", "snapshot"]
