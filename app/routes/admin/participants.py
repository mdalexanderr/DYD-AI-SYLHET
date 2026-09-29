"""Participants — routes 20–25. plan.md §11.3, §11.4, §5.3.

THE CONSENT RULES ARE ENFORCED IN THE MODEL AND THE DATABASE, NOT HERE
    `Participant` refuses to publish without consent, and a CHECK constraint behind
    that refuses it again at insert time. The screens in this file therefore do NOT
    re-implement the rule — they call `participant.publish()` and show whatever it
    says. A second copy of the rule here would be a second answer to "may this name be
    public", and the one that drifted would be the one that mattered.

WHY BULK PUBLISH REPORTS WHAT IT SKIPPED
    §11.3: "Bulk publish silently skips any record without consent and reports how
    many were skipped — it never publishes a name because someone selected 'all'."
    The count is the feature. A screen that says "12 published" when 9 of 12 were
    skipped is a screen that teaches an operator to trust a number that is wrong.

WHY THE LIST IS FILTERED IN SQL AND NOT IN PYTHON
    `search_blob` is a maintained lowercase column (§5.1) and the filters are query
    parameters on a plain GET form, so the whole screen works with scripting off and
    a filtered view has a URL an operator can bookmark or send to a colleague.
"""

from __future__ import annotations

from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.constants import (
    AuditAction,
    ConsentAction,
    ConsentSource,
    Education,
    OutcomeType,
)
from app.extensions import db
from app.models import ConsentEvent, Import, MediaItem, Participant
from app.routes.admin import admin_bp
from app.routes.admin._helpers import commit_with_audit, flag, integer, page_args, text
from app.routes.admin._labels import enum_label
from app.security import audit
from app.services import participant_service

#: §11.3 — 50 per page. This screen's density, not a deployment decision.
PER_PAGE = 50


def _participant_or_404(participant_id: int) -> Participant:
    participant = db.session.get(Participant, participant_id)
    if participant is None:
        abort(404)
    return participant


# The panel is English (§11.1), so these lists are built from the enum VALUES rather
# than from the `_LABELS` maps in `constants`, which are Bangla and belong to the
# public site. `enum_label` turns `further_study` into "Further study" and knows that
# HSC, SMS and FAQ are spelled in capitals — deriving the label means a new enum member
# is labelled the day it is added, instead of the day somebody notices.
#
# The VALUE is what is submitted: the stored vocabulary stays stable Latin so a label
# can be reworded without a migration (§2.8 of the execution plan).
def _education_options() -> list[tuple[str, str]]:
    return [(member.value, enum_label(member)) for member in Education]


def _outcome_options() -> list[tuple[str, str]]:
    return [(member.value, enum_label(member)) for member in OutcomeType]


def _consent_source_options() -> list[tuple[str, str]]:
    return [(member.value, enum_label(member)) for member in ConsentSource]


def _consent_block_reason(participant: Participant) -> str:
    """Why this name cannot be published, in one English sentence.

    BUILT FROM `missing_consent_fields` RATHER THAN FROM A SECOND RULE. The model already
    decides which columns are missing; this only turns that list into the sentence an
    operator reads. A copy of the rule here would be a second answer to "may this name be
    public", and the one that drifted would be the one that mattered.

    `Participant.can_publish` is a BOOL property, not the (bool, reason) pair `Page`
    exposes — the two models differ, and treating them the same is what broke this path.
    """
    missing = participant.missing_consent_fields
    if "consent_publication" in missing:
        return "No consent is recorded, so this name cannot be published."
    if "consent_date" in missing:
        return (
            "Consent is recorded without a date, so this name cannot be published until "
            "the date is filled in."
        )
    return "This name cannot be published yet."


def _parse_outcome(raw: str) -> OutcomeType | None:
    """An outcome from a submitted value, or None. A junk value is not a 500."""
    for member in OutcomeType:
        if member.value == raw:
            return member
    return None


def _parse_education(raw: str) -> Education | None:
    for member in Education:
        if member.value == raw:
            return member
    return None


def _parse_consent_source(raw: str) -> ConsentSource:
    for member in ConsentSource:
        if member.value == raw:
            return member
    return ConsentSource.WRITTEN_FORM


def _library() -> list:
    """Images an operator can attach to a person, newest first.

    IMAGES ONLY, and that is a rule rather than a convenience: `media_items` also holds
    video LINKS (§10.5), and a portrait pointing at one is a broken image on every card
    that shows it.
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


def _apply_image(participant: Participant) -> None:
    """Attach, replace or remove this person's photograph, and record the permission.

    THE PERMISSION GATES THE ATTACHMENT, because the DATABASE refuses the pair: an
    upload that set `photo_id` while `image_consent` was false raised
    `CHECK constraint failed: ck_participants_photo_requires_consent` and the whole
    record — name, education, outcome — was lost with it. So the file is stored in the
    library either way (a library row is a file, not a publication), and the RECORD is
    only given the photograph once there is something to justify it. The operator is told
    which of the two happened, and what to do about it.

    REMOVE FIRST, THEN UPLOAD, THEN THE PICKER. An operator who ticked "remove" meant it,
    and an operator who uploaded a file meant that instead — doing the upload first would
    throw the new file away on the next line.

    THE PERMISSION IS WRITTEN WHETHER OR NOT AN IMAGE ARRIVES. `image_consent` is a fact
    about the person ("they signed for this"), so the office can record it the day the
    form is collected and attach the photograph when it is scanned.
    """
    from app.services import media_service

    consent = flag(request.form, "image_consent")
    participant.image_consent = consent

    if flag(request.form, "remove_photo_id"):
        participant.photo_id = None

    upload = request.files.get("photo_id_file")
    if upload is not None and upload.filename:
        # §13.1's pipeline, unchanged: extension allow list, magic-byte sniffing, a
        # Pillow re-encode that strips EXIF, and a name of our choosing.
        try:
            item = media_service.store_upload(upload, alt_bn=participant.name_bn or "")
        except media_service.UploadRejected as error:
            flash(str(error), "error")
        else:
            db.session.add(item)
            db.session.flush()
            if consent:
                participant.photo_id = item.id
            else:
                flash(
                    "The file is in the media library, but the photograph was NOT "
                    "attached: there is no recorded permission for it. Tick the "
                    "permission box, then choose it from the library.",
                    "info",
                )
            return

    # The picker. Validated against the library rather than trusted: an id that is not an
    # image row would either break the card that renders it or point at a video link.
    raw = text(request.form, "photo_id")
    if raw.isdigit():
        chosen = db.session.get(MediaItem, int(raw))
        if chosen is None:
            flash("That image is no longer in the library.", "error")
        elif not consent:
            flash(
                "The photograph was NOT attached: there is no recorded permission for "
                "it. Tick the permission box and choose it again.",
                "info",
            )
        else:
            participant.photo_id = chosen.id


def _filtered_query() -> tuple[list[Participant], dict[str, str]]:
    """The list and its filters. One place — the list and the export share it."""
    filters = {
        "q": text(request.args, "q"),
        "outcome": text(request.args, "outcome"),
        "consent": text(request.args, "consent"),
        "published": text(request.args, "published"),
        "batch": text(request.args, "batch"),
    }

    stmt = db.select(Participant)

    if filters["q"]:
        stmt = stmt.where(Participant.search_blob.ilike(f"%{filters['q'].lower()}%"))
    outcome = _parse_outcome(filters["outcome"])
    if outcome is not None:
        stmt = stmt.where(Participant.outcome_type == outcome)
    if filters["batch"].isdigit():
        stmt = stmt.where(Participant.batch == int(filters["batch"]))
    if filters["published"] == "yes":
        stmt = stmt.where(Participant.is_published.is_(True))
    elif filters["published"] == "no":
        stmt = stmt.where(Participant.is_published.is_(False))

    if filters["consent"] == "given":
        stmt = stmt.where(
            Participant.consent_publication.is_(True),
            Participant.consent_date.is_not(None),
            Participant.consent_withdrawn_at.is_(None),
        )
    elif filters["consent"] == "missing_date":
        # §5.6 — the state that is both invisible and blocking, and the only one no
        # other number on the dashboard would mention.
        stmt = stmt.where(
            Participant.consent_publication.is_(True),
            Participant.consent_date.is_(None),
            Participant.consent_withdrawn_at.is_(None),
        )
    elif filters["consent"] == "none":
        stmt = stmt.where(Participant.consent_publication.is_(False))
    elif filters["consent"] == "withdrawn":
        stmt = stmt.where(Participant.consent_withdrawn_at.is_not(None))

    stmt = stmt.order_by(Participant.batch, Participant.name_bn, Participant.id)
    return list(db.session.execute(stmt).scalars()), filters


# ─────────────────────────────────────────────────────────────────────────────
# 20 — the list
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.get("/participants")
@login_required
def participants_list():
    rows, filters = _filtered_query()
    page, offset = page_args(request, PER_PAGE)

    return render_template(
        "admin/participants/list.html",
        rows=rows[offset:offset + PER_PAGE],
        total=len(rows),
        page=page,
        per_page=PER_PAGE,
        pages=max(1, (len(rows) + PER_PAGE - 1) // PER_PAGE),
        filters=filters,
        outcomes=_outcome_options(),
    )


@admin_bp.post("/participants/bulk")
@login_required
def participants_bulk():
    """§11.3's bulk actions. Publish skips and COUNTS anyone without consent."""
    ids = [int(value) for value in request.form.getlist("ids") if value.isdigit()]
    action = text(request.form, "bulk_action")

    if not ids:
        flash("No participants were selected.", "error")
        return redirect(url_for("admin.participants_list"))

    rows = list(
        db.session.execute(db.select(Participant).where(Participant.id.in_(ids))).scalars()
    )

    published = skipped = 0
    if action == "publish":
        for participant in rows:
            before = audit.snapshot(participant)
            if not participant.can_publish:
                skipped += 1
                continue
            participant.publish()
            audit.record(AuditAction.PUBLISH, entity=participant, before=before)
            published += 1
        db.session.commit()
        # The skip count is stated in the same sentence as the success count, because
        # "12 published" alone is the number that gets trusted and is wrong.
        flash(
            f"{published} published; {skipped} skipped — no consent, or consented "
            "without a date."
            if skipped
            else f"{published} published.",
            "success" if not skipped else "info",
        )

    elif action == "unpublish":
        for participant in rows:
            before = audit.snapshot(participant)
            participant.unpublish()
            audit.record(AuditAction.UNPUBLISH, entity=participant, before=before)
        db.session.commit()
        flash(f"{len(rows)} unpublished.", "info")

    elif action == "outcome":
        outcome = _parse_outcome(text(request.form, "outcome"))
        if outcome is None:
            flash("That outcome is not recognised.", "error")
            return redirect(url_for("admin.participants_list"))
        for participant in rows:
            before = audit.snapshot(participant)
            participant.outcome_type = outcome
            participant.refresh_search_blob()
            audit.record(AuditAction.UPDATE, entity=participant, before=before)
        db.session.commit()
        flash(f"Outcome updated for {len(rows)} records.", "success")

    else:
        flash("That bulk action is not recognised.", "error")

    return redirect(url_for("admin.participants_list"))


@admin_bp.get("/participants/export.csv")
@login_required
def participants_export():
    """§11.3's export. The current FILTERED set, not the whole table."""
    from app.services import export_service

    rows, filters = _filtered_query()
    audit.record(AuditAction.EXPORT, entity_type="Participant", extra={"count": len(rows)})
    db.session.commit()
    return export_service.participants_csv(rows, filters)


# ─────────────────────────────────────────────────────────────────────────────
# 21, 22 — create and detail
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.get("/participants/new")
@login_required
def participant_new():
    return render_template(
        "admin/participants/edit.html",
        participant=None,
        educations=_education_options(),
        outcomes=_outcome_options(),
        consent_sources=_consent_source_options(),
        events=[],
        profile_url=None,
        images=_library(),
    )


@admin_bp.post("/participants/new")
@login_required
def participant_create():
    name_bn = text(request.form, "name_bn")
    education = _parse_education(text(request.form, "education"))

    if not name_bn or education is None:
        flash("A name and an education level are required.", "error")
        return redirect(url_for("admin.participant_new"))

    slug = text(request.form, "slug").lower()
    if not slug:
        slug = participant_service.slugify(name_bn)
    if not slug or db.session.execute(
        db.select(Participant).where(Participant.slug == slug)
    ).scalars().first():
        flash("That slug is empty or already in use. Choose another.", "error")
        return redirect(url_for("admin.participant_new"))

    participant = Participant(
        slug=slug,
        name_bn=name_bn,
        name_en=text(request.form, "name_en") or None,
        education=education,
        occupation_before=text(request.form, "occupation_before") or None,
        outcome_type=_parse_outcome(text(request.form, "outcome_type")),
        outcome_text=text(request.form, "outcome_text") or None,
        quote_bn=text(request.form, "quote_bn") or None,
        quote_consented=flag(request.form, "quote_consented"),
        batch=integer(request.form, "batch", 1) or 1,
        # NEVER published on creation, and never consented on creation: consent is a
        # separate, deliberate act with a date and a source (§5.3 rule 1).
        consent_publication=False,
        is_published=False,
    )
    participant.refresh_search_blob()
    db.session.add(participant)
    # Flushed before the photograph is attached: a media FK needs this row's id, and an
    # unflushed row has none.
    db.session.flush()
    _apply_image(participant)
    commit_with_audit(AuditAction.CREATE, entity=participant)

    flash("Recorded. Now record their consent — nothing publishes before that.", "info")
    return redirect(url_for("admin.participant_detail", participant_id=participant.id))


@admin_bp.get("/participants/<int:participant_id>")
@login_required
def participant_detail(participant_id: int):
    participant = _participant_or_404(participant_id)
    events = list(
        db.session.execute(
            db.select(ConsentEvent)
            .where(ConsentEvent.participant_id == participant.id)
            .order_by(ConsentEvent.id.desc())
        ).scalars()
    )
    return render_template(
        "admin/participants/edit.html",
        participant=participant,
        educations=_education_options(),
        outcomes=_outcome_options(),
        consent_sources=_consent_source_options(),
        events=events,
        images=_library(),
        # Only offered once the name is actually public: a link to a profile that
        # 404s reads as a broken site rather than as an unpublished record.
        profile_url=f"/batch-1/{participant.slug}" if participant.is_published else None,
    )


@admin_bp.post("/participants/<int:participant_id>")
@login_required
def participant_update(participant_id: int):
    participant = _participant_or_404(participant_id)
    before = audit.snapshot(participant)

    participant.name_bn = text(request.form, "name_bn") or participant.name_bn
    participant.name_en = text(request.form, "name_en") or None
    participant.occupation_before = text(request.form, "occupation_before") or None
    participant.outcome_text = text(request.form, "outcome_text") or None
    participant.quote_bn = text(request.form, "quote_bn") or None
    participant.quote_consented = flag(request.form, "quote_consented")
    participant.batch = integer(request.form, "batch", participant.batch) or participant.batch

    education = _parse_education(text(request.form, "education"))
    if education is not None:
        participant.education = education

    participant.outcome_type = _parse_outcome(text(request.form, "outcome_type"))

    # The photograph, its permission and its removal — one call, so the create path and
    # the edit path cannot disagree about the order they happen in.
    _apply_image(participant)

    # The search column is maintained on write, not computed on read (§5.1).
    participant.refresh_search_blob()

    commit_with_audit(AuditAction.UPDATE, entity=participant, before=before)
    flash("Record saved.", "success")
    return redirect(url_for("admin.participant_detail", participant_id=participant.id))


# ─────────────────────────────────────────────────────────────────────────────
# 23 — consent
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.post("/participants/<int:participant_id>/consent")
@login_required
def participant_consent(participant_id: int):
    """Record, withdraw, or correct a consent decision (§5.3).

    EVERY CHANGE APPENDS A `consent_events` ROW. The participant row holds the current
    state; the events hold how it got there, because "when did this person withdraw"
    is a question a government programme gets asked and a boolean cannot answer.
    """
    participant = _participant_or_404(participant_id)
    before = audit.snapshot(participant)
    decision = text(request.form, "decision")
    note = text(request.form, "consent_notes") or None
    source = text(request.form, "consent_source")

    if decision == "grant":
        raw_date = text(request.form, "consent_date")
        try:
            consent_date = date.fromisoformat(raw_date) if raw_date else None
        except ValueError:
            consent_date = None

        if consent_date is None:
            # The §5.3 rule-3 case: consent recorded without a date. It is allowed
            # (the paperwork exists) and it BLOCKS publication until the date is
            # filled in, which the dashboard shows as its own bucket.
            flash(
                "Consent recorded without a date. Nothing publishes until the date "
                "is known.",
                "info",
            )
        else:
            flash("Consent recorded. This name can be published now.", "success")

        participant.consent_publication = True
        participant.consent_date = consent_date
        # `source`, not `source_raw`. The old name was read here and defined nowhere,
        # so every consent GRANT raised NameError — the withdrawal path worked, the
        # grant path 500ed, and no test covered a grant through this screen.
        participant.consent_source = _parse_consent_source(source)
        participant.consent_notes = note
        participant.consent_withdrawn_at = None
        # THE ENUM MEMBER, NOT "grant". `ConsentAction` is a StrEnum whose values are
        # granted/withdrawn/updated, and SQLAlchemy refuses anything else — this path
        # raised `LookupError: 'grant' is not among the defined enum values`.
        event_action = ConsentAction.GRANTED

    elif decision == "withdraw":
        participant.withdraw_consent(notes=note)
        event_action = ConsentAction.WITHDRAWN
        flash("Consent withdrawn. The name is unpublished from this moment.", "info")

    else:
        flash("That consent decision is not recognised.", "error")
        return redirect(url_for("admin.participant_detail", participant_id=participant.id))

    db.session.add(
        ConsentEvent(
            participant_id=participant.id,
            action=event_action,
            # THE ENUM MEMBER, NOT THE SUBMITTED STRING — for the same reason as
            # `action` above. `ConsentEvent.source` is a `ConsentSource` column, and a
            # form field that was left empty means "not recorded", which is NULL rather
            # than `_parse_consent_source`'s written-form default.
            source=_parse_consent_source(source) if source else None,
            notes=note,
        )
    )
    commit_with_audit(
        AuditAction.CONSENT_GRANT if decision == "grant" else AuditAction.CONSENT_WITHDRAW,
        entity=participant,
        before=before,
    )
    return redirect(url_for("admin.participant_detail", participant_id=participant.id))


@admin_bp.post("/participants/<int:participant_id>/publish")
@login_required
def participant_publish(participant_id: int):
    """Publish or unpublish one person, with the model's own refusal as the message."""
    participant = _participant_or_404(participant_id)
    before = audit.snapshot(participant)

    if text(request.form, "action", "publish") == "publish":
        if not participant.can_publish:
            flash(_consent_block_reason(participant), "error")
            return redirect(url_for("admin.participant_detail", participant_id=participant.id))
        participant.publish()
        commit_with_audit(AuditAction.PUBLISH, entity=participant, before=before)
        flash("Name published.", "success")
    else:
        participant.unpublish()
        commit_with_audit(AuditAction.UNPUBLISH, entity=participant, before=before)
        flash("Name unpublished.", "info")

    return redirect(url_for("admin.participant_detail", participant_id=participant.id))


# ─────────────────────────────────────────────────────────────────────────────
# 24 — the consent dashboard
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.get("/participants/consent")
@login_required
def participants_consent_dashboard():
    """§11.1's consent screen: the states, and the two that need action first."""
    breakdown = participant_service.consent_breakdown()

    def _rows(*criteria):
        return list(
            db.session.execute(
                db.select(Participant).where(*criteria).order_by(Participant.name_bn)
            ).scalars()
        )

    return render_template(
        "admin/participants/consent.html",
        breakdown=breakdown,
        total=participant_service.breakdown_totals(breakdown),
        missing_date=_rows(
            Participant.consent_publication.is_(True),
            Participant.consent_date.is_(None),
            Participant.consent_withdrawn_at.is_(None),
        ),
        awaiting=_rows(
            Participant.consent_publication.is_(False),
            Participant.consent_withdrawn_at.is_(None),
        ),
        withdrawn=_rows(Participant.consent_withdrawn_at.is_not(None)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 25 — CSV import (§11.4)
# ─────────────────────────────────────────────────────────────────────────────
def _recent_imports() -> list[Import]:
    """The last few attempts, successful or not. A failed import is the one an
    operator most needs to see, because the report file is how they fix it."""
    return list(
        db.session.execute(db.select(Import).order_by(Import.id.desc()).limit(8)).scalars()
    )


@admin_bp.get("/participants/import")
@login_required
def participants_import():
    return render_template(
        "admin/participants/import.html", recent=_recent_imports(), report=None
    )


@admin_bp.post("/participants/import")
@login_required
def participants_import_run():
    """Upload, dry-run or commit. Nothing is written on a dry run."""
    from app.services import import_service

    upload = request.files.get("file")
    if upload is None or not upload.filename:
        flash("No file was selected.", "error")
        return redirect(url_for("admin.participants_import"))

    commit = text(request.form, "mode", "dry") == "commit"
    try:
        report = import_service.import_participants(
            upload.read(), filename=upload.filename, commit=commit
        )
    except import_service.ImportFileError as error:
        # A file that cannot be read at all is an editor's mistake, not a 500: the
        # encoding, the delimiter and a header row are all things they can fix.
        flash(str(error), "error")
        return redirect(url_for("admin.participants_import"))

    if commit:
        flash(
            f"{report['created']} new, {report['updated']} updated, "
            f"{report['failed']} rejected.",
            "success" if not report["failed"] else "info",
        )
    else:
        flash(
            f"Dry run: {report['valid']} rows are valid, {report['failed']} have problems. "
            "No rows were stored.",
            "info",
        )

    return render_template(
        "admin/participants/import.html", recent=_recent_imports(), report=report
    )


__all__ = [
    "participant_consent",
    "participant_create",
    "participant_detail",
    "participant_new",
    "participant_publish",
    "participant_update",
    "participants_bulk",
    "participants_consent_dashboard",
    "participants_export",
    "participants_import",
    "participants_import_run",
    "participants_list",
]
