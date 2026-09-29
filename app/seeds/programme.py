"""Seed the content the React half used to hold as TypeScript constants. plan.md §11.3.

    .\\.venv\\Scripts\\python.exe -m flask seed-programme --yes

WHY THERE IS A JSON FILE IN THIS PACKAGE
    `app/seeds/data/frontend_content.json` is the front end's own `mockData.ts`,
    compiled and dumped — 25 participants, 13 modules, 11 tools, 3 phases, 5 works,
    3 trainers and 4 statistics, with every Bangla string byte-for-byte as the site
    rendered it. It exists so that seeding a fresh checkout needs nothing but Python:
    re-deriving it needs Node and `frontend/`, and a seed step that only works on a
    developer's machine is a seed step that fails at the first deploy.

    It was produced with esbuild, not by hand:

        node -e "require('esbuild').buildSync({entryPoints:['src/data/mockData.ts'], \\
                 bundle:true, format:'esm', platform:'node', outfile:'_mock.mjs'})"
        node --input-type=module -e "…"

    and is checked in because a transcription of 94 KB of Bangla by hand would contain
    mistakes, and the mistakes would be in people's names.

WHAT THIS DELIBERATELY DOES NOT COPY FROM THE MOCK DATA
    * **`avatarUrl` on a participant.** §5.1 forbids photographs and the table has no
      column for one. The 25 Unsplash URLs in the mock were placeholders of real
      strangers, which is worse than no image: an invented face on a named person. The
      register renders initials, and the API serves `initials`, never a URL.
    * **`avatarUrl` on a trainer.** A trainer's photograph is not prohibited (§10.4),
      so the column exists — but it is left EMPTY for the same reason. An operator can
      upload the real photograph at `/admin/trainers`.
    * **`phaseTitleBn` / `phaseTitleEn` on a module.** They duplicate the phase row.
      A module points at its phase by id, so the title cannot go stale in 13 places.
    * **`outcomeTypeBn`, `consentDateBn`, `typeLabelBn` and the `*hoursBn` strings.**
      These are Bangla labels, and the API derives each from the stored value or the
      row it belongs to. Copying them would create a second source that can drift.

IDEMPOTENT BY SLUG OR KEY
    Running it twice updates rather than duplicates, which is what makes it safe to run
    after a `db upgrade` on a database that already has content.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from app.constants import (
    ConsentAction,
    ConsentSource,
    Education,
    InstructorStatus,
    OutcomeType,
    WorkKind,
)
from app.extensions import db
from app.filters import BN_MONTHS
from app.models import (
    BatchWork,
    ConsentEvent,
    Course,
    CourseModule,
    CoursePhase,
    Faq,
    Institution,
    Instructor,
    Participant,
    Stat,
    TrainingTool,
)

#: Where the compiled mock data lives. Relative to this file, so it works from any cwd.
DATA_FILE = Path(__file__).parent / "data" / "frontend_content.json"

#: Bangla digits → ASCII. The control number on every `sl_no_bn`, `code_bn` and
#: `hours_bn` is written in Bangla numerals, and a figure the database stores must be
#: a number (§14.1: formatted numbers are rendered, not stored).
_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

#: The mock data's Bangla education labels → the stored enum (§5.1).
EDUCATION_FROM_BN: dict[str, Education] = {
    "এইচএসসি": Education.HSC,
    "ডিপ্লোমা": Education.DIPLOMA,
    "স্নাতক (পাস)": Education.DEGREE,
    "স্নাতক (সম্মান)": Education.HONOURS,
    "অন্যান্য": Education.OTHER,
}

#: How consent was given, as the register's Bangla wording. §5.3 wants a source per
#: record, and `লিখিত সম্মতিপত্র` is the written form the programme collects.
CONSENT_SOURCE_FROM_BN: dict[str, ConsentSource] = {
    "লিখিত সম্মতিপত্র": ConsentSource.WRITTEN_FORM,
    "মৌখিক": ConsentSource.VERBAL_WITNESSED,
    "এসএমএস": ConsentSource.SMS,
    "ইমেইল": ConsentSource.EMAIL,
    "কর্মসূচির শর্তাবলি": ConsentSource.PROGRAMME_TERMS,
}


def to_ascii_digits(value: Any) -> str:
    """`১২৩` → `"123"`. Leaves anything that is not a digit alone."""
    return str(value or "").translate(_BN_DIGITS)


def first_int(value: Any, default: int | None = None) -> int | None:
    """The first number in a string.

    `"ব্যাচ - ১"` → 1, `"৩০ ঘণ্টা"` → 30, `"৫ দিন"` → 5. The mock data writes every
    quantity as display copy, and the stored column is a number, so this is the one
    place that converts. It returns `default` rather than raising: a field the operator
    has not filled in yet is not a seed failure.
    """
    match = re.search(r"\d+", to_ascii_digits(value))
    return int(match.group()) if match else default


def parse_bangla_date(value: Any) -> date | None:
    """`"১৫ জানুয়ারি ২০২৫"` → `date(2025, 1, 15)`.

    Built from `app.filters.BN_MONTHS` rather than a second list of month names: the
    site already knows how to write a Bangla month, and a copy of that list here is a
    copy that will disagree with it.

    A date that cannot be read returns None, which is the §5.3 rule-3 state — consented
    with no recorded date — and the dashboard shows it as a bucket that blocks
    publication rather than hiding it.
    """
    text = to_ascii_digits(value).strip()
    match = re.match(r"^(\d{1,2})\s+(\S+)\s+(\d{4})$", text)
    if not match:
        return None
    day, month_name, year = match.groups()
    try:
        month = BN_MONTHS.index(month_name) + 1
        return date(int(year), month, int(day))
    except (ValueError, IndexError):
        return None


def seed_programme_content(
    raw: dict[str, Any] | None = None,
    *,
    people: bool = False,
    publish: bool = False,
) -> dict[str, int]:
    """Load the front end's content into the database. Returns what it wrote.

    CONTENT BY DEFAULT, PEOPLE ONLY WHEN ASKED FOR
        `people=False` is the default, and that is the important decision in this
        function. The register in the source file is 25 INVENTED people and 3 INVENTED
        trainers; the real cohort and the real trainers arrive by import and by hand.
        A seeder that re-created them on every run would put fabricated names back on a
        live database the first time somebody ran it to refresh a course module — which
        is a consent incident, not a bug report.

        So `people=True` is a DEMO switch: it is what `flask seed-programme
        --with-people` passes, it refuses in production, and it publishes what it loads
        only if `publish=True` as well.

    The phases, tools, modules, works, statistics and institutions are real reference
    content — the programme's own syllabus — and they load every time.
    """
    if raw is None:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    counts = {
        "phases": 0,
        "tools": 0,
        "works": 0,
        "instructors": 0,
        "modules": 0,
        "participants": 0,
        "stats": 0,
    }

    # ── The institution the register points at ──────────────────────────────
    # One row, matched by name (§3.2 keeps exactly one). Created only if the reference
    # seeder did not already make one with this name.
    institution_name = "যুব উন্নয়ন অধিদপ্তর, সিলেট"
    institution = db.session.execute(
        db.select(Institution).where(Institution.name_bn == institution_name)
    ).scalars().first()
    if institution is None:
        institution = Institution(
            slug="youth-development-sylhet",
            name_bn=institution_name,
            name_en="Department of Youth Development, Sylhet",
            role_bn="কর্মসূচি বাস্তবায়নকারী প্রতিষ্ঠান",
            is_active=True,
        )
        db.session.add(institution)
        db.session.flush()

    # ── The course the modules hang off ─────────────────────────────────────
    course = db.session.execute(db.select(Course).order_by(Course.id)).scalars().first()
    if course is None:
        course = Course(
            slug="ai-foundation-sylhet",
            title_bn="এআই প্রশিক্ষণ কর্মসূচি — সিলেট",
            duration_days=50,
            duration_hours=300,
            hours_per_day=6,
            is_active=True,
        )
        db.session.add(course)
        db.session.flush()

    # ── Phases ──────────────────────────────────────────────────────────────
    phases: dict[str, CoursePhase] = {}
    for index, row in enumerate(raw.get("COURSE_PHASES_DATA", []), start=1):
        slug = str(row.get("id") or f"phase-{index}")
        phase = db.session.execute(
            db.select(CoursePhase).where(CoursePhase.slug == slug)
        ).scalars().first()
        if phase is None:
            phase = CoursePhase(slug=slug)
            db.session.add(phase)
        phase.phase_number_bn = row.get("phaseNumberBn") or ""
        phase.title_bn = row.get("titleBn") or ""
        phase.title_en = row.get("titleEn") or None
        phase.hours_bn = row.get("hoursBn") or None
        phase.days_bn = row.get("daysBn") or None
        phase.objective_bn = row.get("objectiveBn") or None
        phase.tools_count_bn = row.get("toolsCountBn") or None
        phase.sort_order = index
        phase.is_active = True
        phases[slug] = phase
        counts["phases"] += 1
    db.session.flush()

    # ── Training tools ──────────────────────────────────────────────────────
    for index, row in enumerate(raw.get("TRAINING_TOOLS_LIST", []), start=1):
        name = (row.get("name") or "").strip()
        tool = db.session.execute(
            db.select(TrainingTool).where(TrainingTool.name == name)
        ).scalars().first()
        if tool is None:
            tool = TrainingTool(name=name)
            db.session.add(tool)
        tool.sl_no_bn = row.get("slNo") or to_ascii_digits(index)
        tool.category_bn = row.get("categoryBn") or None
        tool.description_bn = row.get("descriptionBn") or None
        tool.sort_order = index
        tool.is_active = True
        counts["tools"] += 1

    # ── The cohort's work ───────────────────────────────────────────────────
    for index, row in enumerate(raw.get("BATCH_1_WORKS", []), start=1):
        slug = str(row.get("id") or f"work-{index}")
        work = db.session.execute(
            db.select(BatchWork).where(BatchWork.slug == slug)
        ).scalars().first()
        if work is None:
            work = BatchWork(slug=slug)
            db.session.add(work)
        kind = str(row.get("type") or "").strip().lower()
        work.kind = WorkKind(kind) if kind in set(WorkKind) else WorkKind.VIDEO
        work.kind_label_bn = row.get("typeLabelBn") or None
        work.title_bn = row.get("titleBn") or ""
        work.meta_bn = row.get("metaBn") or None
        work.duration_or_pages_bn = row.get("durationOrPages") or None
        work.description_bn = row.get("descriptionBn") or None
        work.team_or_creator_bn = row.get("teamOrCreatorBn") or None
        work.date_bn = row.get("dateBn") or None
        work.aspect_ratio = row.get("aspectRatio") or None
        work.details = row.get("details") or {}
        work.batch = 1
        work.sort_order = index
        work.is_active = True
        counts["works"] += 1

    # ── Trainers ────────────────────────────────────────────────────────────
    # DEMO ONLY. See the docstring: the real trainers are entered at
    # `/admin/instructors`, and re-seeding must never overwrite them.
    for index, row in enumerate((raw.get("INSTRUCTORS", []) if people else []), start=1):
        slug = str(row.get("id") or f"trainer-{index}")
        trainer = db.session.execute(
            db.select(Instructor).where(Instructor.slug == slug)
        ).scalars().first()
        if trainer is None:
            trainer = Instructor(slug=slug)
            db.session.add(trainer)
        status = str(row.get("status") or "current").strip().lower()
        trainer.status = (
            InstructorStatus(status) if status in set(InstructorStatus)
            else InstructorStatus.CURRENT
        )
        trainer.slide_number_bn = row.get("slideNumberBn") or None
        trainer.slide_number_en = row.get("slideNumberEn") or None
        trainer.status_label_bn = row.get("statusLabelBn") or None
        trainer.tenure_bn = row.get("tenureBn") or None
        trainer.name_bn = row.get("nameBn") or ""
        trainer.name_en = row.get("nameEn") or None
        trainer.designation_bn = row.get("designationBn") or None
        trainer.credentials_bn = row.get("credentialsBn") or None
        trainer.academic_bn = row.get("academicBn") or None
        trainer.quote_bn = row.get("quoteBn") or None
        trainer.bio_bn = row.get("bioBn") or None
        trainer.specialties_bn = row.get("specialtiesBn") or []
        trainer.contributions_bn = row.get("keyContributionsBn") or []
        stats = row.get("teachingStats") or {}
        trainer.hours_taught_bn = stats.get("hoursTaughtBn") or None
        trainer.batch_bn = stats.get("batchBn") or None
        trainer.students_trained_bn = stats.get("studentsTrainedBn") or None
        trainer.sort_order = index
        trainer.is_active = True
        # `photo_id` stays None on purpose — see the module docstring.
        counts["instructors"] += 1

    # ── Modules ─────────────────────────────────────────────────────────────
    for index, row in enumerate(raw.get("COURSE_MODULES", []), start=1):
        code = str(row.get("code") or index)
        module = db.session.execute(
            db.select(CourseModule).where(
                CourseModule.course_id == course.id, CourseModule.code == code
            )
        ).scalars().first()
        if module is None:
            module = CourseModule(course_id=course.id, code=code, title_bn="")
            db.session.add(module)
        phase = phases.get(str(row.get("phaseId")))
        module.phase_id = phase.id if phase is not None else None
        module.title_bn = row.get("titleBn") or ""
        module.title_en = row.get("titleEn") or None
        module.code_bn = row.get("codeBn") or None
        module.hours_bn = row.get("hoursBn") or None
        module.duration_bn = row.get("durationBn") or None
        module.weeks_bn = row.get("weeksBn") or None
        module.days_range_bn = row.get("daysRangeBn") or None
        module.tools = row.get("tools") or []
        module.topics_bn = row.get("topicsBn") or []
        module.learning_outcomes_bn = row.get("learningOutcomesBn") or []
        module.summary_bn = row.get("summaryBn") or None
        module.practical_deliverable_bn = row.get("practicalDeliverableBn") or None
        # The stored number is derived from the display string, so the two cannot
        # disagree: "৩০ ঘণ্টা" IS 30.
        module.hours = first_int(row.get("hoursBn"))
        module.sort_order = index
        counts["modules"] += 1

    # ── The register ────────────────────────────────────────────────────────
    # DEMO ONLY, for the same reason as the trainers above. The flag gates the LIST
    # rather than wrapping the loop in an `if`, so the body below keeps one indentation
    # level and the whole decision is visible in one expression.
    for row in (raw.get("PARTICIPANTS_REGISTER", []) if people else []):
        slug = str(row.get("slug") or "").strip()
        if not slug:
            continue

        participant = db.session.execute(
            db.select(Participant).where(Participant.slug == slug)
        ).scalars().first()
        created = participant is None
        if created:
            # `education` and `name_bn` are NOT NULL with no server default, so they are
            # supplied at construction rather than after the flush — an INSERT cannot
            # wait for the field it is missing.
            participant = Participant(
                slug=slug,
                name_bn=row.get("nameBn") or "",
                education=EDUCATION_FROM_BN.get(
                    str(row.get("education") or "").strip(), Education.OTHER
                ),
                is_published=False,
            )
            db.session.add(participant)
            # Flushed before the consent event is built: the event needs the id, and an
            # unflushed row has none.
            db.session.flush()

        participant.name_bn = row.get("nameBn") or ""
        participant.name_en = row.get("nameEn") or None
        participant.education = EDUCATION_FROM_BN.get(
            str(row.get("education") or "").strip(), Education.OTHER
        )
        participant.occupation_before = _trim(row.get("occupationBefore"), 80)
        outcome = str(row.get("outcomeType") or "").strip().lower()
        participant.outcome_type = (
            OutcomeType(outcome) if outcome in set(OutcomeType) else None
        )
        participant.outcome_text = row.get("outcomeText") or None
        participant.quote_bn = row.get("quoteBn") or None
        # A quotation is a stronger act than publishing a name (§5.3 rule 5), so the
        # flag is only set when there IS a quotation to consent to.
        participant.quote_consented = bool(participant.quote_bn)
        participant.batch = first_int(row.get("batch"), 1) or 1
        participant.institution_id = institution.id
        participant.refresh_search_blob()

        consent_date = parse_bangla_date(row.get("consentDateBn"))
        source = CONSENT_SOURCE_FROM_BN.get(str(row.get("consentSource") or "").strip())

        if created or not participant.consent_publication:
            participant.consent_publication = True
            participant.consent_date = consent_date
            participant.consent_source = source or ConsentSource.WRITTEN_FORM
            participant.consent_notes = "Imported from the programme register."
            db.session.add(
                ConsentEvent(
                    participant_id=participant.id,
                    # The ENUM MEMBER, not the string "grant": `ConsentAction` is a
                    # StrEnum whose values are granted/withdrawn/updated, and SQLAlchemy
                    # refuses a value that is not one of them.
                    action=ConsentAction.GRANTED,
                    source=(source or ConsentSource.WRITTEN_FORM),
                    notes="Seeded from the programme register.",
                )
            )

        counts["participants"] += 1

        # Publishing goes through the model's own gate rather than setting the flag:
        # `can_publish` is the one place that decides whether a name may be public
        # (§5.3), and a seeder that set `is_published = True` directly would be a second
        # answer to that question. NOTE it is a BOOL property on Participant — unlike
        # `Page.can_publish`, which returns (allowed, reason).
        if publish and participant.can_publish:
            participant.publish()

    # ── The statistics the strip shows ──────────────────────────────────────
    for index, row in enumerate(raw.get("PROGRAMME_STATS", []), start=1):
        key = str(row.get("key") or f"stat-{index}")
        stat = db.session.execute(
            db.select(Stat).where(Stat.key == key)
        ).scalars().first()
        if stat is None:
            stat = Stat(key=key)
            db.session.add(stat)
        stat.label_bn = row.get("labelBn") or key
        stat.value_bn = row.get("numberBn") or None
        stat.context_bn = row.get("contextBn") or None
        # The React home strip's group. The table is shared with the Jinja pages' stat
        # strips, which select their rows by id, so this is what keeps the two readers
        # from showing each other's figures.
        stat.group = "programme"
        stat.display_order = index
        counts["stats"] += 1

    # A question the seeded FAQ set may not contain, and which the register raises the
    # moment it exists. Added only when absent, so an operator's edit is never undone.
    if not db.session.execute(
        db.select(Faq).where(Faq.question_bn == "নাম প্রকাশের সম্মতি কীভাবে দেওয়া হয়?")
    ).scalars().first():
        db.session.add(
            Faq(
                question_bn="নাম প্রকাশের সম্মতি কীভাবে দেওয়া হয়?",
                answer_bn=(
                    "প্রশিক্ষণার্থী লিখিত সম্মতিপত্রে সই করলে এবং তারিখ উল্লেখ করলে "
                    "নাম, শিক্ষাগত যোগ্যতা, প্রশিক্ষণের আগের পেশা ও প্রশিক্ষণোত্তর "
                    "ফলাফল প্রকাশ করা হয়। সম্মতি ছাড়া কোনো তথ্য প্রকাশিত হয় না, এবং "
                    "যেকোনো সময় সম্মতি প্রত্যাহার করা হলে নাম সঙ্গে সঙ্গে সরিয়ে নেওয়া হয়।"
                ),
                category="সম্মতি",
                sort_order=99,
                is_active=True,
            )
        )

    db.session.commit()
    return counts


def _trim(value: Any, limit: int) -> str | None:
    """A short field, cut to fit. A long value must not make the seed fail."""
    text = str(value or "").strip()
    return text[:limit] or None


__all__ = [
    "DATA_FILE",
    "CONSENT_SOURCE_FROM_BN",
    "EDUCATION_FROM_BN",
    "first_int",
    "parse_bangla_date",
    "seed_programme_content",
    "to_ascii_digits",
]
