"""Media library — route 28. plan.md §11.1, §13.1, §13.2.

THE UPLOAD PIPELINE IS IN THE SERVICE, NOT HERE
    Extension allow list, magic-byte sniffing, Pillow re-encode, random name, storage
    outside the webroot: all of it is `media_service.store_upload`, because that is a
    security boundary and a security boundary belongs in one place with its own tests.
    This module validates nothing about a file and decides nothing about a path.

ALT TEXT IS REQUIRED TO BE PRESENT, NOT MEANINGFUL
    §13.2 requires alt text on every image, and the service falls back to the original
    filename so nothing is ever empty. That is a floor, not a standard: the screen asks
    for a description and shows the fallback so an operator can see it is a filename
    and replace it.

USAGE COUNTS ARE COMPUTED, NOT STORED
    `MediaItem.used_count` exists, but a stored count is a number that goes stale the
    first time a section is deleted without touching it. The count here is derived by
    asking the sections that reference media, so it cannot lie.
"""

from __future__ import annotations

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.constants import AuditAction, MediaKind
from app.extensions import db
from app.models import MediaItem, PageSection
from app.routes.admin import admin_bp
from app.routes.admin._helpers import commit_with_audit, text
from app.security import audit
from app.services import media_service


def _usage_counts() -> dict[int, int]:
    """How many page sections point at each media item.

    Walks the section payloads rather than trusting `used_count`, because a stored
    count is wrong the moment a section is deleted, and a screen that says "in use"
    for an unused file is a screen that stops an operator from deleting a 4 MB
    mistake.

    WHICH KEYS COUNT IS ASKED OF THE SCHEMA, not guessed from the value's type. A
    list of integers is a list of media ids in `gallery_strip` and a list of FAQ ids
    in `faq_list`, and counting by type alone would make an unused photograph
    undeletable because some FAQ happened to share its number.
    """
    from app.sections.registry import get_schema

    counts: dict[int, int] = {}
    for section in db.session.execute(db.select(PageSection)).scalars():
        content = section.content or {}
        schema = get_schema(section.type) or {}

        for key, rule in schema.items():
            if not isinstance(rule, dict) or rule.get("model") != "MediaItem":
                continue

            value = content.get(key)
            if rule.get("type") == "ref":
                candidates = [value]
            else:
                candidates = value if isinstance(value, list) else []

            for candidate in candidates:
                if isinstance(candidate, int) and not isinstance(candidate, bool):
                    counts[candidate] = counts.get(candidate, 0) + 1
    return counts


@admin_bp.get("/media")
@login_required
def media_library():
    items = list(
        db.session.execute(db.select(MediaItem).order_by(MediaItem.id.desc()).limit(200)).scalars()
    )
    return render_template(
        "admin/media.html",
        items=items,
        usage=_usage_counts(),
        signed=media_service.signed_url,
        max_mb=int(current_app.config.get("MAX_CONTENT_LENGTH_MB") or 6),
    )


@admin_bp.post("/media")
@login_required
def media_upload():
    """One or more files at once. Each is validated on its own, so one bad file does
    not lose the good ones in the same submission."""
    uploads = [item for item in request.files.getlist("files") if item and item.filename]
    if not uploads:
        flash("No file was selected.", "error")
        return redirect(url_for("admin.media_library"))

    alt_bn = text(request.form, "alt_bn")
    caption_bn = text(request.form, "caption_bn") or None

    stored = 0
    for upload in uploads:
        try:
            item = media_service.store_upload(upload, alt_bn=alt_bn, caption_bn=caption_bn)
        except media_service.UploadRejected as error:
            # The rejection carries its own Bangla reason, which is the message the
            # operator needs — "file is too large" beats "upload failed".
            flash(str(error), "error")
            continue

        # This screen stores IMAGES. A video is a link (§10.5), added through the
        # section editor rather than uploaded here, so the kind is asserted at the
        # one place a row is created instead of being left to a default.
        item.kind = MediaKind.IMAGE

        commit_with_audit(AuditAction.CREATE, entity=item)
        stored += 1

    if stored:
        flash(f"{stored} image(s) added.", "success")
    return redirect(url_for("admin.media_library"))


@admin_bp.post("/media/<int:media_id>")
@login_required
def media_update(media_id: int):
    """Alt text, caption and tags. The file itself is never edited in place."""
    item = db.session.get(MediaItem, media_id)
    if item is None:
        abort(404)

    before = audit.snapshot(item)
    item.alt_bn = text(request.form, "alt_bn") or item.alt_bn
    item.caption_bn = text(request.form, "caption_bn") or None

    # `tags` is a JSON list on the model, not a string. A comma-separated box is the
    # right input for it, and splitting here is what keeps the column holding a list
    # instead of one long string that happens to contain commas.
    raw_tags = text(request.form, "tags")
    item.tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()] or None

    commit_with_audit(AuditAction.UPDATE, entity=item, before=before)
    flash("Image details saved.", "success")
    return redirect(url_for("admin.media_library"))


@admin_bp.post("/media/<int:media_id>/delete")
@login_required
def media_delete(media_id: int):
    """Delete the row AND the file.

    Refused while a section still points at it: a deleted media row leaves a section
    rendering a gap, and the editor who deleted it is the only person who can fix that
    — so they are told, by name, which page uses it.
    """
    item = db.session.get(MediaItem, media_id)
    if item is None:
        abort(404)

    in_use = _usage_counts().get(item.id, 0)
    if in_use:
        flash(
            f"This image is used by {in_use} section(s). Remove it from them "
            "first.",
            "error",
        )
        return redirect(url_for("admin.media_library"))

    before = audit.snapshot(item)
    path = item.path

    from pathlib import Path

    db.session.delete(item)
    audit.record(
        AuditAction.DELETE,
        entity_type="MediaItem",
        entity_id=media_id,
        before=before,
        after=None,
    )
    db.session.commit()

    # The row is gone first. A file that cannot be removed leaves a stray byte on
    # disk, which is untidy; a row pointing at a file that is gone is a broken page.
    try:
        (Path(current_app.config["UPLOAD_ROOT"]) / path).unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("media: could not remove %s", path)

    flash("Image deleted.", "info")
    return redirect(url_for("admin.media_library"))


__all__ = ["media_delete", "media_library", "media_update", "media_upload"]
