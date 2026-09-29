"""The content the React half renders. plan.md §11.3, §5.2, §6.4.

WHY THIS EXISTS
    `frontend/src/data/mockData.ts` was a build-time constant, so the CMS could not
    change a word of the React pages: editing a module in the admin changed a database
    row that nothing read. This module is the other end of that wire. It reads the
    tables the admin writes and returns them in the shapes the pages already use, so
    the pages did not have to be redesigned to become manageable.

WHY THE PROJECTIONS ARE BUILT HERE AND NOT IN THE VIEW
    A participant projection is a CONSENT DECISION. `to_card()` is an allowlist of four
    facts (§5.2) and `published_only()` is the publication rule (§5.3); both live in
    `participant_service`, which is the module the Jinja pages already trust. The API
    calls them rather than writing its own `SELECT`, because a second query is a second
    answer to "may this name be public", and the browser is the last place that
    question should be answered.

WHAT IS NOT EXPOSED, AND WHY THAT IS THE POINT
    A participant's `consent_notes`, `consent_source`, `search_blob`, `is_published` and
    every administrative field are absent: they are records ABOUT a person, not facts
    about their training. A participant's photograph does not exist in the database at
    all (§5.1), so `initials` is derived here — the browser needs something to draw, and
    two letters from a name is not personal data.
"""

from __future__ import annotations

from typing import Any


def _text(value: Any) -> str | None:
    """A trimmed string, or None. Empty strings become None so the JSON has one way of
    saying "nothing" rather than two."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _media_url(item: Any) -> str | None:
    """A servable URL for a media row, or None.

    TWO KINDS OF MEDIA EXIST and they need different answers: a row may point at an
    uploaded file (served through a signed URL, because uploads live outside the
    webroot — §13.1) or at an external address. Returning `path` for an external row
    would produce a URL that 404s.
    """
    if item is None:
        return None
    external = getattr(item, "external_url", None)
    if external:
        return str(external)

    path = getattr(item, "path", None)
    if not path:
        return None

    from app.services import media_service

    return media_service.signed_url(str(path))


def initials(name: str | None) -> str:
    """`"রায়হান ইসলাম"` → `"রি"`, `"Rayhan Islam"` → `"RI"`.

    Used where the register shows a person and there is no photograph — which is every
    participant, always, because §5.1 has no column for one. Two characters, taken from
    the first two words, so the register still scans as a list of individuals.
    """
    if not name:
        return "?"
    words = [word for word in str(name).split() if word]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2]
    return (words[0][:1] + words[1][:1]).upper()


# ─────────────────────────────────────────────────────────────────────────────
# Each builder returns the shape the page already consumed from mockData.ts, so
# adopting the API was a data-source change rather than a redesign.
# ─────────────────────────────────────────────────────────────────────────────
def _stats() -> list[dict[str, Any]]:
    """The figures in the React home strip — the `programme` group only.

    The `stats` table is shared: the Jinja pages' stat strips select their rows by id,
    and the React strip shows the programme's four headline figures. Without the group
    filter this endpoint would hand the strip all eleven and the page would grow tiles
    nobody asked for, which is the failure mode of "one table, two readers".
    """
    from app.extensions import db
    from app.models import Stat

    rows = db.session.execute(
        db.select(Stat)
        .where(Stat.group == "programme")
        .order_by(Stat.display_order, Stat.id)
    ).scalars()
    return [
        {
            "key": row.key,
            "number_bn": row.value_bn,
            "label_bn": row.label_bn,
            "context_bn": row.context_bn,
        }
        for row in rows
        if row.value_bn
    ]


def _tools() -> list[dict[str, Any]]:
    from app.extensions import db
    from app.models import TrainingTool

    rows = db.session.execute(
        db.select(TrainingTool)
        .where(TrainingTool.is_active.is_(True))
        .order_by(TrainingTool.sort_order, TrainingTool.id)
    ).scalars()
    return [
        {
            "sl_no_bn": row.sl_no_bn,
            "name": row.name,
            "category_bn": row.category_bn,
            "description_bn": row.description_bn,
        }
        for row in rows
    ]


def _phases() -> list[dict[str, Any]]:
    from app.extensions import db
    from app.models import CoursePhase

    rows = db.session.execute(
        db.select(CoursePhase)
        .where(CoursePhase.is_active.is_(True))
        .order_by(CoursePhase.sort_order, CoursePhase.id)
    ).scalars()
    return [
        {
            "slug": row.slug,
            "phase_number_bn": row.phase_number_bn,
            "title_bn": row.title_bn,
            "title_en": row.title_en,
            "hours_bn": row.hours_bn,
            "days_bn": row.days_bn,
            "objective_bn": row.objective_bn,
            "tools_count_bn": row.tools_count_bn,
        }
        for row in rows
    ]


def _modules() -> list[dict[str, Any]]:
    """The modules that belong to a phase — which is the ones the React page shows.

    THE PHASE IS THE SCOPE, AND THAT IS NOT A HACK. The React course page is organised
    as Phase 1 / 2 / 3 with a filter, so a module with no phase has no place on it: it
    would render as an unlabelled row under no heading. The Jinja course page selects
    its modules through a `module_list` section and is unaffected.

    The practical consequence for an operator: to put a module on the React page,
    assign it a phase in the admin. That is a rule the screen can state, which is why
    it is better than an id range or a hard-coded list.
    """
    from app.extensions import db
    from app.models import CourseModule

    rows = db.session.execute(
        db.select(CourseModule)
        .where(CourseModule.phase_id.is_not(None))
        .order_by(CourseModule.sort_order, CourseModule.id)
    ).scalars()
    return [
        {
            "code": row.code,
            "code_bn": row.code_bn,
            "phase_slug": row.phase.slug if row.phase else None,
            "days_range_bn": row.days_range_bn,
            "title_bn": row.title_bn,
            "title_en": row.title_en,
            "duration_bn": row.duration_bn,
            "weeks_bn": row.weeks_bn,
            "hours_bn": row.hours_bn,
            "hours": row.hours,
            "tools": row.tools or [],
            "summary_bn": row.summary_bn,
            "topics_bn": row.topics_bn or [],
            "learning_outcomes_bn": row.learning_outcomes_bn or [],
            "practical_deliverable_bn": row.practical_deliverable_bn,
        }
        for row in rows
    ]


def _works() -> list[dict[str, Any]]:
    from app.extensions import db
    from app.models import BatchWork

    rows = db.session.execute(
        db.select(BatchWork)
        .where(BatchWork.is_active.is_(True))
        .order_by(BatchWork.sort_order, BatchWork.id)
    ).scalars()
    return [
        {
            "slug": row.slug,
            "kind": str(row.kind),
            "kind_label_bn": row.kind_label_bn,
            "title_bn": row.title_bn,
            "meta_bn": row.meta_bn,
            "duration_or_pages": row.duration_or_pages_bn,
            "description_bn": row.description_bn,
            "team_or_creator_bn": row.team_or_creator_bn,
            "date_bn": row.date_bn,
            "aspect_ratio": row.aspect_ratio,
            "details": row.details or {},
            "image_url": _media_url(row.media),
        }
        for row in rows
    ]


def _trainers() -> list[dict[str, Any]]:
    from app.extensions import db
    from app.models import Instructor

    rows = db.session.execute(
        db.select(Instructor)
        .where(Instructor.is_active.is_(True))
        .order_by(Instructor.sort_order, Instructor.id)
    ).scalars()
    return [
        {
            "slug": row.slug,
            "slide_number_bn": row.slide_number_bn,
            "slide_number_en": row.slide_number_en,
            "status": str(row.status),
            "status_label_bn": row.status_label_bn,
            "tenure_bn": row.tenure_bn,
            "name_bn": row.name_bn,
            "name_en": row.name_en,
            "initials": initials(row.name_bn),
            "designation_bn": row.designation_bn,
            "credentials_bn": row.credentials_bn,
            "academic_bn": row.academic_bn,
            "photo_url": _media_url(row.photo),
            "quote_bn": row.quote_bn,
            "bio_bn": row.bio_bn,
            "specialties_bn": row.specialties_bn or [],
            "contributions_bn": row.contributions_bn or [],
            "stats": {
                "hours_taught_bn": row.hours_taught_bn,
                "batch_bn": row.batch_bn,
                "students_trained_bn": row.students_trained_bn,
            },
        }
        for row in rows
    ]


def _participants() -> list[dict[str, Any]]:
    """Every participant who may be shown, through the consent rule itself.

    `participant_service.list_published` is the only list a public surface may call: it
    applies `published_only` (consent recorded, dated, not withdrawn, published) inside
    the query, so no filter here can widen the result. Each card is then extended with
    the fields the register page shows but `to_card` does not carry.
    """
    from app.extensions import db
    from app.models import Participant
    from app.services import participant_service

    cards = participant_service.list_published(sort="manual")

    # One extra query for the fields the register needs, keyed by slug, rather than a
    # second list built from a second query — the published set stays the ONE source of
    # membership.
    by_slug = {
        row.slug: row
        for row in db.session.execute(
            db.select(Participant).where(
                Participant.slug.in_([card["slug"] for card in cards] or [""])
            )
        ).scalars()
    }

    out: list[dict[str, Any]] = []
    for card in cards:
        row = by_slug.get(card["slug"])
        if row is None:  # pragma: no cover — the two queries cannot disagree
            continue
        out.append(
            {
                "slug": card["slug"],
                "name_bn": card["name_bn"],
                "name_en": card["name_en"],
                "initials": initials(card["name_bn"]),
                # A PORTRAIT ONLY WITH ITS OWN PERMISSION. `to_card` returns None unless
                # `photo_is_publishable`, so the browser cannot render a face whose
                # subject did not agree to one being shown — and the initial plate in
                # the components is what appears instead.
                "photo_url": card.get("photo_url"),
                "education": str(row.education),
                "meta": card["meta"],
                "occupation_before": row.occupation_before,
                "outcome_type": str(row.outcome_type) if row.outcome_type else None,
                "outcome_label": card["outcome_label"],
                "outcome_text": card["outcome_text"],
                # A quote only with its OWN permission (§5.3 rule 5) — the same rule
                # `to_profile` applies, restated here because this payload feeds a page
                # rather than a profile.
                "quote_bn": row.quote_bn if row.quote_consented else None,
                "batch": row.batch,
                "institution_bn": row.institution.name_bn if row.institution_id else None,
                "profile_href": card["href"],
            }
        )
    return out


def _institutions() -> list[dict[str, Any]]:
    from app.extensions import db
    from app.models import Institution

    rows = db.session.execute(
        db.select(Institution)
        .where(Institution.is_active.is_(True))
        .order_by(Institution.name_bn)
    ).scalars()
    return [
        {
            "slug": row.slug,
            "name_bn": row.name_bn,
            "name_en": row.name_en,
            "role_bn": row.role_bn,
            "address_bn": row.address_bn,
            "description_bn": row.description_bn,
        }
        for row in rows
    ]


def _batches(participants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The batch register, DERIVED from the published participants.

    Not a table. A batch exists because people are in it, and a `batches` table would
    be a second list to keep in step with the register — the moment they disagreed, the
    page would advertise a batch with nobody in it. The count here is the count of
    people who consented, which is the only number the site may publish (§5.4).
    """
    from app.extensions import db
    from app.models import Course

    course = db.session.execute(db.select(Course).order_by(Course.id)).scalars().first()

    numbers: dict[int, int] = {}
    for row in participants:
        numbers[row["batch"]] = numbers.get(row["batch"], 0) + 1

    return [
        {
            "number": number,
            "label_bn": f"ব্যাচ {number}",
            "label_en": f"Batch {number}",
            "participant_count": count,
            "start_date": course.start_date.isoformat() if course and course.start_date else None,
            "end_date": course.end_date.isoformat() if course and course.end_date else None,
            "is_current": number == max(numbers),
        }
        for number, count in sorted(numbers.items())
    ]


def build_content() -> dict[str, Any]:
    """Everything the React half renders, in one payload.

    ONE RESPONSE, NOT SEVEN
        The site has eight pages and each needs a different slice, but they are all
        small: the whole dataset is 25 participants and 13 modules. Seven endpoints
        would mean seven loading states, seven error states and seven chances for a
        page to render half-populated. One payload is roughly 30 KB gzipped, fetched
        once and cached for the session.

    ORDER MATTERS AND IS DECIDED HERE, ONCE
        Every list is ordered by `sort_order` and then by id — so two rows the operator
        gave the same number still come out in a stable order, which is what stops a
        page reshuffling itself between requests.
    """
    participants = _participants()
    modules = _modules()
    works = _works()
    trainers = _trainers()
    return {
        "stats": _stats(),
        "tools": _tools(),
        "phases": _phases(),
        "modules": modules,
        "works": works,
        "trainers": trainers,
        "participants": participants,
        "institutions": _institutions(),
        "batches": _batches(participants),
        "counts": {
            "participants": len(participants),
            "modules": len(modules),
            "works": len(works),
            "trainers": len(trainers),
        },
    }


__all__ = ["build_content", "initials"]
