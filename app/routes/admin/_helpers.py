"""Shared helpers for the admin screens. plan.md §11.

WHAT LIVES HERE AND WHY
    Three things every screen needs and none of them should reimplement: reading a
    value out of a submitted form, committing a change WITH its audit row in one
    transaction, and paginating a list. Everything else belongs to the screen that
    owns the data.

WHY `commit_with_audit` EXISTS
    `app/security/audit.py` writes a row into the session and deliberately does NOT
    commit, so that a rolled-back change leaves no audit entry. Every write in the
    admin has the same shape — snapshot, mutate, record, commit — and doing it by
    hand in eleven screens is eleven chances to commit before recording, which would
    log the change without the actor or the change without the log. One helper, one
    order, one place to test.
"""

from __future__ import annotations

from typing import Any, Mapping

from flask import flash
from sqlalchemy import func

from app.extensions import db
from app.security import audit


def text(form: Mapping[str, Any], name: str, default: str = "") -> str:
    """A trimmed string field. `None` and a missing key both become `default`."""
    value = form.get(name)
    return default if value is None else str(value).strip()


def flag(form: Mapping[str, Any], name: str) -> bool:
    """A checkbox: present means true, which is how HTML works."""
    return name in form


def integer(form: Mapping[str, Any], name: str, default: int | None = None) -> int | None:
    """An int, or `default`. A blank box is not a zero."""
    raw = form.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def commit_with_audit(action: str, *, entity: Any = None, before: dict[str, Any] | None = None,
                      extra: dict[str, Any] | None = None) -> None:
    """Record the change and commit it, in that order, in one transaction.

    The audit row is added first: `record()` puts it in the same session, so a
    failure between here and the commit rolls back both the change and its record.

    THE FLUSH IS FOR THE CREATE CASE. `record()` reads `entity.id`, and on a create
    that attribute is still None until the INSERT goes out — so without this, every
    create in the admin would be logged with no entity id, which is the one field
    that makes an audit row findable. Flushing here (not committing) keeps the
    change and its audit row in the same transaction, which is the whole point.
    """
    if entity is not None:
        db.session.flush()
    audit.record(action, entity=entity, before=before, extra=extra)
    db.session.commit()


def flash_ok(message: str) -> None:
    flash(message, "success")


def flash_error(message: str) -> None:
    flash(message, "error")


def count(model: Any, *criteria: Any) -> int:
    """COUNT(*) for a list screen's header. A COUNT over nothing is 0, not an error."""
    stmt = db.select(func.count(model.id))
    for criterion in criteria:
        stmt = stmt.where(criterion)
    return int(db.session.execute(stmt).scalar_one())


def page_args(request: Any, default_size: int) -> tuple[int, int]:
    """(page, offset) from `?page=`, clamped. Junk in the query string is not a 500."""
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)
    return page, (page - 1) * default_size


__all__ = [
    "commit_with_audit",
    "count",
    "flag",
    "flash_error",
    "flash_ok",
    "integer",
    "page_args",
    "text",
]
