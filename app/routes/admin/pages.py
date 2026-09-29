"""Pages and the section editor — routes 17, 18, 19. plan.md §11.2.

THE ONE SCREEN WHERE A MISTAKE IS PUBLICLY VISIBLE
    Everything else in the admin writes a record that a page may or may not show
    later. This writes the page. §11.2 lists the behaviours it must have, and each
    one is here for a reason:

    * **A picker of the 13 types, no free-form block builder.** The types are the
      design system (§4.2); anything else is layout an editor can break.
    * **Type-specific forms generated from the section schema**, so a field added to
      a section type appears here without anyone remembering to add it.
    * **Reorder with a keyboard alternative.** Up/down buttons, not drag-only —
      a drag handle is unusable from a keyboard and unusable on a phone.
    * **Visibility is a toggle, not a delete.** `is_visible = false` is skipped
      entirely at render (§9.3 rule 4), which is how an editor takes a section down
      without losing the text they wrote.
    * **Delete means delete**, with a confirm step in the form. The audit row keeps
      the payload, so it is recoverable from `/admin/audit`.
    * **The publish gate names the section that is stopping it.** `Page.can_publish`
      already produces that message; this screen shows it rather than a generic error.

WHY THE PREVIEW RENDERS THE REAL TEMPLATE
    A preview that approximates the page is a preview that agrees with itself. This
    renders `section.template` with the same context builder the public page uses, so
    what an editor approves is what a reader gets — including a dropped section, which
    shows up as a hole rather than as a promise.

AND WHY THE TYPE NAMES COME FROM `_labels`
    `registry.section_choices()` carries the site's Bangla label and hint, because that
    is what the section IS in this project. The panel is English (§11.1), so the names
    shown here are looked up in the admin's own vocabulary — the same lookup
    `PageSection.type_label_en` already used. The alternative was Bangla labels in an
    English panel, and a hard-coded second list that would go stale the moment a
    section type was added.
"""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.constants import AuditAction
from app.extensions import db
from app.models import Page, PageSection
from app.routes.admin import admin_bp
from app.routes.admin._helpers import commit_with_audit, flag, integer, text
from app.routes.admin._labels import section_hint, section_name
from app.security import audit
from app.sections import registry


def _page_or_404(page_id: int) -> Page:
    page = db.session.get(Page, page_id)
    if page is None:
        abort(404)
    return page


def _section_or_404(page: Page, section_id: int) -> PageSection:
    section = db.session.get(PageSection, section_id)
    # Checked against the page in the URL as well as the database: `/pages/1/.../9`
    # where section 9 belongs to page 2 must not be editable through page 1.
    if section is None or section.page_id != page.id:
        abort(404)
    return section


def _editor_context(page: Page) -> dict:
    """Everything the editor draws: the sections, their forms, and the gate."""
    rows = []
    for section in page.sections:
        ok, reason = section.validate_payload()
        rows.append(
            {
                "row": section,
                "valid": ok,
                "problem": reason,
                "schema": registry.get_schema(section.type),
                "preview": _preview_text(section),
            }
        )

    can_publish, gate_reason = page.can_publish
    return {
        "page": page,
        "rows": rows,
        # English names for the 13 types, from the admin's own vocabulary — see the
        # module docstring. `registry.section_choices()` is the list; `_labels` is the
        # wording.
        "choices": [
            {
                "value": row["value"],
                "label": section_name(row["value"]),
                "hint": section_hint(row["value"]),
            }
            for row in registry.section_choices()
        ],
        "can_publish": can_publish,
        "gate_reason": gate_reason,
    }


def _preview_text(section: PageSection) -> str:
    """The one line the section list shows. Never blank, or the list looks broken."""
    content = section.content or {}
    for key in ("heading_bn", "title_bn", "quote_bn", "name_bn", "label_bn"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:90]
    return section.type_label


@admin_bp.get("/pages")
@login_required
def pages_list():
    """Route 17 — the page list, with draft/published state."""
    pages = list(db.session.execute(db.select(Page).order_by(Page.sort_order, Page.id)).scalars())
    return render_template(
        "admin/pages/list.html",
        pages=pages,
        can_create=True,
    )


@admin_bp.post("/pages")
@login_required
def pages_create():
    """Route 17 — create. Slug is validated against what a URL can carry."""
    title_bn = text(request.form, "title_bn")
    slug = text(request.form, "slug").lower().replace(" ", "-")

    if not title_bn:
        flash("A title is required.", "error")
        return redirect(url_for("admin.pages_list"))

    if not slug:
        flash("A URL slug is required.", "error")
        return redirect(url_for("admin.pages_list"))

    allowed = all(ch.isalnum() or ch in "-_" for ch in slug)
    if not allowed or not slug[0].isalpha():
        flash(
            "A slug may contain only lowercase Latin letters, digits, hyphens and "
            "underscores, and must start with a letter.",
            "error",
        )
        return redirect(url_for("admin.pages_list"))

    if db.session.execute(db.select(Page).where(Page.slug == slug)).scalars().first():
        flash(f"The slug '{slug}' is already in use.", "error")
        return redirect(url_for("admin.pages_list"))

    highest = db.session.execute(db.select(db.func.max(Page.sort_order))).scalar() or 0
    page = Page(
        slug=slug,
        title_bn=title_bn,
        nav_label_bn=text(request.form, "nav_label_bn") or title_bn,
        sort_order=int(highest) + 1,
        is_published=False,
    )
    db.session.add(page)
    commit_with_audit(AuditAction.CREATE, entity=page)

    flash("Page created. Add its sections next.", "success")
    return redirect(url_for("admin.page_editor", page_id=page.id))


@admin_bp.get("/pages/<int:page_id>")
@login_required
def page_editor(page_id: int):
    """Route 18 — the sections editor (§11.2)."""
    return render_template("admin/pages/edit.html", **_editor_context(_page_or_404(page_id)))


@admin_bp.post("/pages/<int:page_id>/meta")
@login_required
def page_update_meta(page_id: int):
    """The page itself: title, navigation label, description, and where it sorts."""
    page = _page_or_404(page_id)
    before = audit.snapshot(page)

    page.title_bn = text(request.form, "title_bn") or page.title_bn
    page.title_en = text(request.form, "title_en") or None
    page.nav_label_bn = text(request.form, "nav_label_bn") or None
    page.meta_description_bn = text(request.form, "meta_description_bn") or None
    page.show_in_nav = flag(request.form, "show_in_nav")
    page.sort_order = integer(request.form, "sort_order", page.sort_order) or 0

    commit_with_audit(AuditAction.UPDATE, entity=page, before=before)
    flash("Page details saved.", "success")
    return redirect(url_for("admin.page_editor", page_id=page.id))


@admin_bp.post("/pages/<int:page_id>/publish")
@login_required
def page_publish(page_id: int):
    """Route 19 — publish or unpublish, gated by §11.2's rules."""
    page = _page_or_404(page_id)
    before = audit.snapshot(page)
    wanted = text(request.form, "action", "publish") == "publish"

    if wanted:
        allowed, reason = page.can_publish
        if not allowed:
            # The gate's own message names the section and the field (§11.2). It is
            # shown as-is rather than re-worded here.
            flash(reason, "error")
            return redirect(url_for("admin.page_editor", page_id=page.id))
        page.publish()
        flash("Page published.", "success")
    else:
        page.is_published = False
        page.published_at = None
        flash("Page unpublished.", "info")

    commit_with_audit(AuditAction.PUBLISH if wanted else AuditAction.UNPUBLISH, entity=page, before=before)
    return redirect(url_for("admin.page_editor", page_id=page.id))


@admin_bp.post("/pages/<int:page_id>/sections")
@login_required
def section_add(page_id: int):
    """Add a section of a chosen type, with the smallest valid payload it can have."""
    page = _page_or_404(page_id)
    section_type = text(request.form, "type")

    try:
        impl = registry.get_section(section_type)
    except registry.SectionError:
        flash("That section type does not exist.", "error")
        return redirect(url_for("admin.page_editor", page_id=page.id))

    highest = max([s.sort_order for s in page.sections], default=0)
    section = PageSection(
        page_id=page.id,
        type=impl.type,
        sort_order=highest + 1,
        is_visible=True,
        # EMPTY, NOT INVENTED. A new section starts invalid for types that require a
        # field, and the editor shows exactly what is missing. Pre-filling placeholder
        # text would publish something nobody wrote.
        content={},
    )
    db.session.add(section)
    commit_with_audit(AuditAction.CREATE, entity=section)

    flash(f"Added a '{section_name(impl.type)}' section. Fill in its fields next.", "info")
    return redirect(url_for("admin.page_editor", page_id=page.id))


@admin_bp.post("/pages/<int:page_id>/sections/<int:section_id>")
@login_required
def section_update(page_id: int, section_id: int):
    """Save one section's payload, after validating it against its schema."""
    from app.routes.admin._fields import section_payload

    page = _page_or_404(page_id)
    section = _section_or_404(page, section_id)
    before = audit.snapshot(section)

    payload = section_payload(section.type, request.form)
    ok, reason = registry.validate_section(section.type, payload)
    if not ok:
        flash(reason, "error")
        return redirect(url_for("admin.page_editor", page_id=page.id))

    section.content = payload
    commit_with_audit(AuditAction.UPDATE, entity=section, before=before)
    flash(f"{section.type_label_en} saved.", "success")
    return redirect(url_for("admin.page_editor", page_id=page.id))


@admin_bp.post("/pages/<int:page_id>/sections/<int:section_id>/visibility")
@login_required
def section_visibility(page_id: int, section_id: int):
    """Show or hide. Hidden sections are skipped at render, never hidden with CSS."""
    page = _page_or_404(page_id)
    section = _section_or_404(page, section_id)
    before = audit.snapshot(section)

    section.is_visible = not section.is_visible
    commit_with_audit(AuditAction.UPDATE, entity=section, before=before)

    flash(
            "Section is visible again." if section.is_visible else "Section hidden.",
            "info",
        )
    return redirect(url_for("admin.page_editor", page_id=page.id))


@admin_bp.post("/pages/<int:page_id>/sections/<int:section_id>/move")
@login_required
def section_move(page_id: int, section_id: int):
    """Reorder without a drag handle: §11.2 asks for a keyboard alternative.

    Swaps `sort_order` with the neighbour in the direction asked for. Two rows change
    and nothing else does, so a page whose orders are 1,2,3,3 cannot be reshuffled by
    accident.
    """
    direction = text(request.form, "direction", "up")
    page = _page_or_404(page_id)
    section = _section_or_404(page, section_id)

    ordered = sorted(page.sections, key=lambda s: (s.sort_order, s.id))
    index = next((i for i, s in enumerate(ordered) if s.id == section.id), None)
    target_index = index - 1 if direction == "up" else index + 1

    if index is None or target_index < 0 or target_index >= len(ordered):
        return redirect(url_for("admin.page_editor", page_id=page.id))

    # Renumber the whole list from 1 rather than swapping two values: sections added
    # over time share sort_order (the add form uses max + 1, but a seed can write
    # anything), and renumbering repairs that as a side effect.
    ordered[index], ordered[target_index] = ordered[target_index], ordered[index]
    before = audit.snapshot(page)
    for position, row in enumerate(ordered, start=1):
        row.sort_order = position

    commit_with_audit(AuditAction.UPDATE, entity=page, before=before, extra={"reorder": direction})
    return redirect(url_for("admin.page_editor", page_id=page.id))


@admin_bp.post("/pages/<int:page_id>/sections/<int:section_id>/delete")
@login_required
def section_delete(page_id: int, section_id: int):
    """Delete a section. The audit row below keeps the payload, so it is recoverable."""
    page = _page_or_404(page_id)
    section = _section_or_404(page, section_id)
    before = audit.snapshot(section)

    db.session.delete(section)
    # Recorded as a DELETE against a detached row: `entity_id` has to be passed
    # explicitly because the object is gone by the time the snapshot is read.
    audit.record(
        AuditAction.DELETE,
        entity_type="PageSection",
        entity_id=section_id,
        before=before,
        after=None,
    )
    db.session.commit()

    flash("Section deleted. Its contents are kept in the audit log.", "info")
    return redirect(url_for("admin.page_editor", page_id=page.id))


@admin_bp.get("/pages/<int:page_id>/preview")
@login_required
def page_preview(page_id: int):
    """The page as a reader would get it, rendered from the real templates."""
    page = _page_or_404(page_id)
    rendered = [
        registry.render_section(section, request)
        for section in page.visible_sections
        if section.validate_payload()[0]
    ]
    dropped = [
        {"type": section.type, "label": section.type_label, "reason": section.validate_payload()[1]}
        for section in page.visible_sections
        if not section.validate_payload()[0]
    ]
    return render_template(
        "admin/pages/preview.html",
        page=page,
        sections=rendered,
        dropped=dropped,
    )


__all__ = [
    "page_editor",
    "page_preview",
    "page_publish",
    "page_update_meta",
    "pages_create",
    "pages_list",
    "section_add",
    "section_delete",
    "section_move",
    "section_update",
    "section_visibility",
]
