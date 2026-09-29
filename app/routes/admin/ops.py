"""Messages, audit and backups — routes 32, 33, 34. plan.md §11.1, §12.1, §17.5.

WHY THESE THREE SHARE A MODULE
    Each of them is a read-only view over an operational table, each is under twenty
    lines of actual work, and none of them owns any content. Splitting them into three
    files would be three docstrings explaining that there is nothing to explain. The
    screens that DO own content — pages, participants, media — are separate modules for
    the opposite reason.

MESSAGES ARE READ, MARKED AND ANNOTATED, NEVER DELETED
    A contact-form message is somebody outside the organisation who wrote in. §11.1
    lists the screen as "contact-form submissions"; the status moves forward through
    new → read → replied → closed and nothing removes a row, because the retention
    rule in §16.4 is what deletes, on a schedule, and a manual delete would leave the
    message count and the retention report disagreeing.

THE AUDIT SCREEN SHOWS THE DIFF, INCLUDING THE PARTS THAT ARE UNCOMFORTABLE
    §12.1: "every write with a before/after diff". Secrets never reach it — each
    model's `__audit_exclude__` strips them on the way in (models/base.py) — so what is
    shown is exactly what was changed, which is the point of having it.
"""

from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.constants import AuditAction, MessageStatus
from app.extensions import db
from app.models import AuditLog, Backup, ContactMessage
from app.routes.admin import admin_bp
from app.routes.admin._helpers import commit_with_audit, page_args, text
from app.routes.admin._labels import enum_label
from app.security import audit

PER_PAGE = 50


# ─────────────────────────────────────────────────────────────────────────────
# 32 — contact-form submissions
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.get("/messages")
@login_required
def messages_list():
    status = text(request.args, "status")
    stmt = db.select(ContactMessage).order_by(ContactMessage.id.desc())

    if status:
        for member in MessageStatus:
            if member.value == status:
                stmt = stmt.where(ContactMessage.status == member)

    rows = list(db.session.execute(stmt.limit(200)).scalars())
    return render_template(
        "admin/messages.html",
        rows=rows,
        status=status,
        # English, derived from the enum value (§11.1). The Bangla map in `constants`
        # is the public site's wording for the same states and is untouched.
        statuses=[(member.value, enum_label(member)) for member in MessageStatus],
    )


@admin_bp.post("/messages/<int:message_id>")
@login_required
def message_update(message_id: int):
    """Move a message along its status, and keep the operator's own note on it."""
    message = db.session.get(ContactMessage, message_id)
    if message is None:
        abort(404)

    before = audit.snapshot(message)
    wanted = text(request.form, "status")
    for member in MessageStatus:
        if member.value == wanted:
            message.status = member
            if member in (MessageStatus.REPLIED, MessageStatus.CLOSED):
                from app.models.base import utcnow

                message.replied_at = message.replied_at or utcnow()

    message.admin_notes = text(request.form, "admin_notes") or None
    commit_with_audit(AuditAction.UPDATE, entity=message, before=before)

    flash("Message updated.", "success")
    return redirect(url_for("admin.messages_list"))


# ─────────────────────────────────────────────────────────────────────────────
# 33 — the audit log
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.get("/audit")
@login_required
def audit_list():
    entity_type = text(request.args, "entity_type")
    action = text(request.args, "action")
    page, offset = page_args(request, PER_PAGE)

    stmt = db.select(AuditLog).order_by(AuditLog.id.desc())
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)

    rows = list(db.session.execute(stmt.limit(PER_PAGE).offset(offset)).scalars())
    total = int(
        db.session.execute(db.select(db.func.count(AuditLog.id))).scalar_one()
    )

    entity_types = [
        row for (row,) in db.session.execute(
            db.select(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type)
        ).all()
        if row
    ]

    return render_template(
        "admin/audit.html",
        rows=rows,
        total=total,
        page=page,
        per_page=PER_PAGE,
        entity_type=entity_type,
        action=action,
        entity_types=entity_types,
        actions=sorted(member.value for member in AuditAction),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 34 — backups
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.get("/backups")
@login_required
def backups_list():
    """What the backup job has produced. Creating one is a shell task (§17.5).

    Deliberately not a button: a backup runs `mysqldump` and then copies files, and a
    web request that shells out to dump a database is a request that can time out
    half way through — leaving either a partial archive or, worse, a complete-looking
    one. The screen reports on the cron job instead.
    """
    rows = list(db.session.execute(db.select(Backup).order_by(Backup.id.desc()).limit(50)).scalars())
    latest = rows[0] if rows else None
    return render_template("admin/backups.html", rows=rows, latest=latest)


__all__ = ["audit_list", "backups_list", "message_update", "messages_list"]
