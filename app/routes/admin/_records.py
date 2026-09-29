"""One screen shape for the six records screens. plan.md §11.1.

WHAT THIS IS FOR
    Institutions, FAQs, stats, settings, the course record and its modules are all the
    same screen: a list, a create form, an edit form, a deactivate. Writing that six
    times would be six places for the audit call to be forgotten, six places for a
    validation message to drift, and six templates that slowly stop matching.

WHAT IT IS NOT
    A framework. There is no field registry, no widget system and no plugin hook. A
    screen declares its FIELDS (name, Bangla label, kind, and whether it is required)
    and this module renders and reads them. Anything that needs more than that — the
    section editor, participants, the media library — is its own module, because it
    genuinely is its own screen.

THE AUDIT ROW IS NOT OPTIONAL HERE
    Every write goes through `commit_with_audit`, so a screen built from this helper
    cannot forget to record one. That is the reason the helper exists at all: the
    fastest way to add a screen must also be the way that logs it.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field as dataclass_field
from typing import Any

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.constants import AuditAction
from app.extensions import db
from app.routes.admin import admin_bp
from app.routes.admin._helpers import commit_with_audit, flag, integer, text
from app.security import audit

TEXT = "text"
TEXTAREA = "textarea"
NUMBER = "number"
CHECKBOX = "checkbox"
SELECT = "select"
STAT = "stat"

#: A FOREIGN KEY picked from the rows of another table — a module's course, and
#: anything else that grows a parent.
#:
#: IT IS NOT A `select` WITH HARD-CODED CHOICES. The parent can be created later, by
#: somebody else, while this screen is open; the choices are therefore read on each
#: request. And it is not a text box: `course_id` is an integer FK, and a free-text
#: version would accept "1 " or "one" and fail at INSERT.
REF = "ref"

#: A TEXTAREA whose non-empty lines become a JSON list of strings.
#:
#: IT EXISTS BECAUSE A TRAINER'S SPECIALTIES ARE A LIST, not a paragraph: the model column
#: is JSON, the public page renders one chip per entry, and a screen that edited the
#: column as free text would write a string into a list column — which reads fine in the
#: form and breaks the page that maps over it. One line, one entry; a blank line is
#: dropped rather than stored as an empty chip.
LINES = "lines"


@dataclass(frozen=True)
class Field:
    """One input on a record screen.

    THE LABEL IS DERIVED, NOT TYPED
        `label` defaults to an English label built from the COLUMN NAME, so
        `Field("title_bn")` is labelled "Title (Bangla)" without anybody writing that
        string. The column name is already the schema; a hand-written label beside it
        is a second copy that goes stale when the field is renamed, and the failure is
        silent — a form still asking for "Heading" after the column became `standfirst`.

        Pass `label` explicitly only where the derived one is genuinely worse.
        `slug` is the case that matters: derived it reads "Slug" and the label an
        operator needs is "URL slug".
    """

    name: str
    label: str = ""
    kind: str = TEXT
    required: bool = False
    choices: tuple[tuple[str, str], ...] = ()
    #: A model name whose ROWS are the choices — `"Course"` for a module's parent.
    #: Only used by `kind=REF`; resolved per request by `resolved_fields()`.
    choices_ref: str | None = None
    hint: str = ""
    #: `str` values that arrive as numbers (batches, hours, sort orders).
    minimum: int | None = None
    maximum: int | None = None
    #: Rendered read-only ONCE THE ROW EXISTS — see `_apply_fields`: the value is still
    #: required to create the row, and cannot be changed afterwards. Used for
    #: `Setting.key`, which is the name the code looks up.
    readonly: bool = False
    #: Column width in the list table: "" (normal), "narrow" or "wide".
    width: str = ""
    #: What the list shows if the value is empty. Never blank, so a row is never
    #: a mystery.
    empty: str = "—"

    def __post_init__(self) -> None:
        if not self.label:
            from app.routes.admin._labels import field_label

            object.__setattr__(self, "label", field_label(self.name))


@dataclass
class Screen:
    """One records screen: its model, its fields and its list columns.

    `title` and `intro` are English (§11.1). They are shown as the page heading and
    the one-line explanation under it, and the intro is where the screen says the
    thing an operator would otherwise have to learn by breaking it — for statistics,
    that values below five records are never published.
    """

    endpoint: str
    path: str
    title: str
    model: Any
    fields: tuple[Field, ...]
    #: Fields shown in the list. Defaults to the first three form fields.
    columns: tuple[str, ...] = ()
    order_by: tuple[str, ...] = ()
    slug_field: str | None = None
    #: Soft delete: a row with this boolean is deactivated instead of deleted. The
    #: database keeps the record, which is what §11.1's "delete (soft)" asks for.
    active_field: str | None = "is_active"
    #: The name of a `Field` holding a media row (`photo_id`). Declaring it gives the
    #: screen an image field — library picker, upload, remove. See `media_field` in
    #: `admin/_macros.html`. None means this screen has no image.
    media_field: str | None = None
    intro: str = ""
    label_field: str = "id"
    extras: dict[str, Any] = dataclass_field(default_factory=dict)


def _ref_choices_for(spec: Field) -> tuple[tuple[str, str], ...]:
    """The choices for one REF field, read live. See `_fields._ref_choices`."""
    from app.routes.admin._fields import _ref_choices

    if not spec.choices_ref:
        return spec.choices
    return tuple(
        (str(row["value"]), row["label"]) for row in _ref_choices(spec.choices_ref)
    )


def resolved_fields(screen: Screen) -> list[Field]:
    """The screen's fields, with every `choices_ref` turned into real choices.

    Called by the list, from the same rows the save validates against, so the dropdown
    cannot offer something the validator refuses — or refuse something it offered.
    """
    return [
        dataclasses.replace(spec, choices=_ref_choices_for(spec))
        if spec.choices_ref
        else spec
        for spec in screen.fields
    ]


def _ref_is_valid(spec: Field, raw: str) -> bool:
    """True when `raw` is one of the ids the picker is offering right now."""
    return any(raw == value for value, _ in _ref_choices_for(spec))


def _apply_fields(screen: Screen, row: Any, form: Any) -> list[str]:
    """Write the submitted values onto `row`. Returns the problems found.

    The messages name the field by its LABEL rather than by its column name, because
    "Title (Bangla) is required" tells an operator which box to fill and
    "title_bn is required" tells them which column the code wanted.
    """
    problems: list[str] = []

    for spec in screen.fields:
        # READ-ONLY MEANS "NOT EDITABLE ONCE IT EXISTS", not "never written".
        # `Setting.key` is the case: it is the name the code looks up, so an operator
        # must not be able to rename it after the fact — but the CREATE path still has
        # to supply it, and skipping the field unconditionally left `settings.key` NULL
        # at INSERT, so "Add record" on the settings screen could never work.
        if spec.readonly and getattr(row, "id", None) is not None:
            continue

        if spec.kind == CHECKBOX:
            setattr(row, spec.name, flag(form, spec.name))
            continue

        if spec.kind == NUMBER:
            value = integer(form, spec.name)
            if value is None:
                if spec.required:
                    problems.append(f"{spec.label} is required.")
                continue
            if spec.minimum is not None and value < spec.minimum:
                problems.append(f"{spec.label} must be at least {spec.minimum}.")
            if spec.maximum is not None and value > spec.maximum:
                problems.append(f"{spec.label} cannot be more than {spec.maximum}.")
            setattr(row, spec.name, value)
            continue

        if spec.kind == REF:
            raw = text(form, spec.name)
            if not raw:
                if spec.required:
                    problems.append(f"Choose a {spec.label.lower()}.")
                continue
            if not _ref_is_valid(spec, raw):
                # Refused rather than stored: an id that is not in the list is either a
                # row that was deleted while the form was open, or a hand-edited post.
                problems.append(f"That {spec.label.lower()} no longer exists — choose another.")
                continue
            setattr(row, spec.name, int(raw))
            continue

        if spec.kind == SELECT:
            value = text(form, spec.name)
            allowed = {choice[0] for choice in spec.choices}
            if value not in allowed:
                if spec.required:
                    problems.append(f"Choose a {spec.label.lower()}.")
                continue
            setattr(row, spec.name, value)
            continue

        if spec.kind == LINES:
            raw = text(form, spec.name) or ""
            # `splitlines` rather than `split("\n")`: a value pasted from Windows carries
            # CRLF, and a trailing "\r" would end up inside the stored string.
            items = [line.strip() for line in raw.splitlines() if line.strip()]
            if not items and spec.required:
                problems.append(f"{spec.label} is required.")
                continue
            setattr(row, spec.name, items)
            continue

        if spec.kind == STAT:
            # Numeric(12,2). An empty box clears the figure rather than storing 0,
            # because a zero and "not counted" are different claims on a stat strip.
            raw = text(form, spec.name)
            from decimal import Decimal, InvalidOperation

            if not raw:
                setattr(row, spec.name, None)
                continue
            try:
                setattr(row, spec.name, Decimal(raw))
            except InvalidOperation:
                problems.append(f"{spec.label} must be a number.")
            continue

        value = text(form, spec.name)
        if not value:
            if spec.required:
                problems.append(f"{spec.label} is required.")
            continue
        setattr(row, spec.name, value)

    return problems


def _validate_row(screen: Screen, row: Any, problems: list[str]) -> list[str]:
    """Screen-level rules beyond "is it filled in"."""
    if screen.slug_field:
        slug = getattr(row, screen.slug_field, "") or ""
        if slug and not all(ch.isalnum() or ch in "-_" for ch in slug):
            problems.append(
                "A slug may contain only Latin letters, digits, hyphens and underscores."
            )
    return problems


def _unique_conflict(screen: Screen, row: Any) -> bool:
    """Is this row's key already taken by a different row?"""
    key = getattr(row, "key", None)
    if key is None:
        return False
    existing = db.session.execute(
        db.select(screen.model).where(screen.model.key == key)
    ).scalars().first()
    return existing is not None and existing.id != getattr(row, "id", None)


def register(screen: Screen, *, url_prefix: str = "") -> None:
    """Attach a screen's three routes to the admin blueprint.

    Three routes, always: the list (which carries the create form), the save (which
    creates or updates depending on whether an id was submitted), and the toggle.
    """

    def _rows() -> list[Any]:
        stmt = db.select(screen.model)
        for column in screen.order_by or ("id",):
            stmt = stmt.order_by(getattr(screen.model, column))
        return list(db.session.execute(stmt).scalars())

    def _list():
        edit_id = request.args.get("edit")
        editing = None
        if edit_id and edit_id.isdigit():
            editing = db.session.get(screen.model, int(edit_id))
            if editing is None:
                abort(404)
        return render_template(
            "admin/records/list.html",
            screen=screen,
            rows=_rows(),
            editing=editing,
            # Resolved per request, because a row created a minute ago must be pickable
            # and a row deleted a minute ago must not be.
            form_fields=resolved_fields(screen),
            columns=screen.columns or tuple(spec.name for spec in screen.fields[:3]),
            # Only the screens with an image field pay for the query.
            images=_library() if screen.media_field else [],
            **screen.extras,
        )

    def _library():
        """The images an operator can pick from, newest first.

        Images only: `media_items` also holds video LINKS (§10.5), and a portrait that
        pointed at one would render as a broken image on the card.
        """
        from app.constants import MediaKind
        from app.models import MediaItem

        return list(
            db.session.execute(
                db.select(MediaItem)
                .where(MediaItem.kind == MediaKind.IMAGE)
                .order_by(MediaItem.id.desc())
                .limit(200)
            ).scalars()
        )

    def _attach_media(row) -> None:
        """Apply the image field: remove, upload, or pick. In that order.

        THE ORDER MATTERS. A remove-then-upload is a replace, and an upload-then-remove
        would silently throw the new file away. "Remove" wins over a picker that still
        shows the old image, because an operator who ticked the box meant it.

        A REJECTED UPLOAD IS A FLASH, NOT AN EXCEPTION: `store_upload` raises
        `UploadRejected` with the reason an operator can act on ("the file is too large",
        "that is not an image"), and losing the rest of the record over a bad photograph
        would be the wrong trade.
        """
        from app.services import media_service

        field_name = screen.media_field
        if not field_name:
            return

        if flag(request.form, f"remove_{field_name}"):
            setattr(row, field_name, None)
            return

        upload = request.files.get(f"{field_name}_file")
        if upload is not None and upload.filename:
            try:
                item = media_service.store_upload(
                    upload, alt_bn=text(request.form, "alt_bn") or ""
                )
            except media_service.UploadRejected as error:
                flash(str(error), "error")
            else:
                db.session.add(item)
                db.session.flush()
                setattr(row, field_name, item.id)

    def _save():
        raw_id = text(request.form, "row_id")
        creating = not raw_id.isdigit()
        row = None if creating else db.session.get(screen.model, int(raw_id))
        if not creating and row is None:
            abort(404)

        before = audit.snapshot(row) if row is not None else None
        if row is None:
            row = screen.model()

        problems = _validate_row(screen, row, _apply_fields(screen, row, request.form))

        if not creating and hasattr(row, "key") and _unique_conflict(screen, row):
            problems.append("That key is already used by another row.")

        if problems:
            for problem in problems:
                flash(problem, "error")
            return redirect(url_for(f"admin.{screen.endpoint}", **({"edit": raw_id} if raw_id else {})))

        if creating:
            db.session.add(row)
            # Flushed before the image is attached, because a FK needs an id and an
            # unflushed row has none — the same reason the CSV import flushes before it
            # builds a consent event.
            db.session.flush()

        _attach_media(row)
        commit_with_audit(AuditAction.CREATE if creating else AuditAction.UPDATE, entity=row, before=before)

        flash("Saved.", "success")
        return redirect(url_for(f"admin.{screen.endpoint}"))

    def _toggle():
        raw_id = text(request.form, "row_id")
        if not raw_id.isdigit():
            abort(400)
        row = db.session.get(screen.model, int(raw_id))
        if row is None:
            abort(404)
        if screen.active_field is None:
            abort(400)

        before = audit.snapshot(row)
        setattr(row, screen.active_field, not getattr(row, screen.active_field))
        commit_with_audit(AuditAction.UPDATE, entity=row, before=before)
        flash("Status changed.", "info")
        return redirect(url_for(f"admin.{screen.endpoint}"))

    base = f"{url_prefix}{screen.path}"
    _list.__name__ = f"{screen.endpoint}"
    _save.__name__ = f"{screen.endpoint}_save"
    _toggle.__name__ = f"{screen.endpoint}_toggle"

    admin_bp.add_url_rule(base, endpoint=screen.endpoint, view_func=login_required(_list), methods=["GET"])
    admin_bp.add_url_rule(base, endpoint=f"{screen.endpoint}_save", view_func=login_required(_save), methods=["POST"])
    if screen.active_field:
        admin_bp.add_url_rule(
            f"{base}/toggle",
            endpoint=f"{screen.endpoint}_toggle",
            view_func=login_required(_toggle),
            methods=["POST"],
        )


__all__ = ["CHECKBOX", "Field", "NUMBER", "SELECT", "STAT", "Screen", "TEXT", "TEXTAREA", "register"]
