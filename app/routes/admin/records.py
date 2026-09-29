"""The six records screens: course, modules, institutions, FAQs, statistics, settings.

plan.md §11.1, routes 26, 27, 29, 30, 31 — each one a declaration, not an
implementation. `_records.py` holds the list/save/toggle shape; this file says WHAT
each screen is made of.

WHY THEY ARE DECLARATIONS
    A screen is its fields. Writing them out six times would mean six chances to forget
    an audit row, six validation messages that drift apart, and six templates that stop
    matching each other. Here each screen is a dozen lines that can be read against the
    plan's own table.

WHY FEW LABELS ARE WRITTEN OUT
    `Field("title_bn")` is labelled "Title (Bangla)" without anybody typing that — the
    label is derived from the column name by `_labels.field_label`, so renaming a
    column cannot leave a form asking for the old thing. A label is passed explicitly
    only where the derived one is genuinely worse, and each of those is commented.

WHAT EACH SCREEN IS FOR
    * **Course** — the record the syllabus hangs off: hours, duration, certification.
    * **Course modules** — the ordered modules. `sort_order` is a number, not a drag
      handle, so reordering works from a keyboard and with scripting off.
    * **Institutions** — the training centre and partners (§10.4, and Q2's unconfirmed
      names — which is exactly why an operator needs to be able to correct them).
    * **FAQs** — grouped question and answer, rendered by the `faq_list` section.
    * **Statistics** — the figures in a stat strip. `value_bn` is the DISPLAY string,
      which is the one place in this project where a formatted number is stored (§14.1's
      exception, named in the model docstring).
    * **Settings** — site copy, hotline, footer, toggles. `is_secret` rows are shown but
      never written: §16.2 keeps credentials in `.env`, and a form that could overwrite
      one would be the way that rule gets broken.
"""

from __future__ import annotations

from app.constants import InstructorStatus, SettingValueType, StatSource
from app.models import Course, CourseModule, Faq, Instructor, Institution, Setting, Stat
from app.routes.admin._labels import enum_label
from app.routes.admin._records import (
    CHECKBOX,
    LINES,
    NUMBER,
    REF,
    SELECT,
    STAT,
    TEXT,
    TEXTAREA,
    Field,
    Screen,
    register,
)

# ── 26 — the course and its modules ──────────────────────────────────────────
COURSE = Screen(
    endpoint="admin_course",
    path="/course",
    title="Course",
    model=Course,
    intro="The course record. Its modules are ordered on a separate screen.",
    label_field="title_bn",
    order_by=("id",),
    slug_field="slug",
    fields=(
        Field("title_bn", required=True),
        Field("slug", label="URL slug", required=True, hint="Lowercase Latin, e.g. ai-foundation"),
        Field("summary_bn", kind=TEXTAREA),
        Field("duration_days", kind=NUMBER, minimum=1, maximum=400),
        Field("duration_hours", kind=NUMBER, minimum=1, maximum=2000),
        Field("hours_per_day", kind=NUMBER, minimum=1, maximum=12),
        Field("certification_note_bn"),
    ),
    columns=("title_bn", "duration_hours", "hours_per_day", "is_active"),
)

COURSE_MODULES = Screen(
    endpoint="admin_course_modules",
    path="/course/modules",
    title="Course modules",
    model=CourseModule,
    intro=(
        "Ordered by the sort number — the smallest first. A module belongs to a course "
        "and, to appear on the course page, to a phase."
    ),
    label_field="title_bn",
    order_by=("sort_order", "id"),
    # A module has no `is_active` column, so this screen must not offer a switch for one.
    # It used to inherit the default and POSTing it raised AttributeError — a 500 behind
    # a button in the row actions.
    active_field=None,
    fields=(
        Field(
            "course_id",
            kind=REF,
            choices_ref="Course",
            required=True,
            label="Course",
            hint="The syllabus this module belongs to. There is usually one.",
        ),
        Field("title_bn", required=True),
        Field("description_bn", kind=TEXTAREA),
        Field("hours", kind=NUMBER, minimum=1, maximum=200, required=True),
        Field("sort_order", kind=NUMBER, minimum=0, maximum=999),
        Field("icon_slug", hint="Thematic name used by the design system. Leave empty if unsure."),
    ),
    columns=("sort_order", "title_bn", "hours"),
)

# ── 27 — institutions ────────────────────────────────────────────────────────
INSTITUTIONS = Screen(
    endpoint="admin_institutions",
    path="/institutions",
    title="Institutions",
    model=Institution,
    intro="The training centre and the partner organisations. Confirm every name and address against the record.",
    label_field="name_bn",
    order_by=("name_bn",),
    slug_field="slug",
    fields=(
        Field("name_bn", required=True),
        Field("name_en"),
        Field("slug", label="URL slug", required=True),
        Field("role_bn", hint="e.g. Training partner"),
        Field("address_bn"),
        Field("contact_phone"),
        Field("contact_email"),
        Field("description_bn", kind=TEXTAREA),
    ),
    columns=("name_bn", "role_bn", "address_bn", "is_active"),
)

# ── 30 — FAQs ────────────────────────────────────────────────────────────────
FAQS = Screen(
    endpoint="admin_faqs",
    path="/faqs",
    title="Questions",
    model=Faq,
    intro="Questions sharing a category are shown together, e.g. all the course questions.",
    label_field="question_bn",
    order_by=("sort_order", "id"),
    fields=(
        Field("question_bn", required=True),
        Field("answer_bn", kind=TEXTAREA, required=True),
        Field("category", hint="Groups the list on the page, e.g. Course · Consent · Payments"),
        Field("sort_order", kind=NUMBER, minimum=0, maximum=999),
    ),
    columns=("category", "question_bn", "is_active"),
)

# ── 29 — statistics ─────────────────────────────────────────────────────────
STATS = Screen(
    endpoint="admin_stats",
    path="/stats",
    title="Statistics",
    model=Stat,
    intro=(
        "The display value is what the strip shows — type it in Bangla numerals. Use the "
        "numeric value for anything counted, because a figure drawn from fewer than five "
        "records is never published."
    ),
    label_field="label_bn",
    order_by=("display_order", "id"),
    # A statistic has no `is_active` column either — see COURSE_MODULES above.
    active_field=None,
    fields=(
        Field("key", required=True, hint="Latin, e.g. course_hours"),
        Field("label_bn", required=True),
        Field("value_bn", label="Display value", hint="e.g. ৩০০ ঘণ্টা"),
        Field("value_num", label="Numeric value", kind=STAT),
        Field("unit_bn", label="Unit"),
        Field(
            "source",
            kind=SELECT,
            choices=tuple((member.value, enum_label(member)) for member in StatSource),
        ),
        Field("display_order", kind=NUMBER, minimum=0, maximum=999),
    ),
    columns=("label_bn", "value_bn", "source", "display_order"),
)

# ── 31 — settings ───────────────────────────────────────────────────────────
SETTINGS = Screen(
    endpoint="admin_settings",
    path="/settings",
    title="Settings",
    model=Setting,
    intro=(
        "Site copy, the hotline, the footer and a few on/off switches. Rows marked as "
        "secret are read-only here: their values live in the server's .env file (§16.2)."
    ),
    label_field="key",
    order_by=("group", "key"),
    slug_field=None,
    # And a setting: deactivating a key/value row is not a thing the site can act on,
    # so there is no switch to offer.
    active_field=None,
    fields=(
        Field("key", required=True, readonly=True),
        Field("label_bn", label="Admin label"),
        Field("value", kind=TEXTAREA),
        Field(
            "value_type",
            label="Type",
            kind=SELECT,
            choices=tuple((member.value, enum_label(member)) for member in SettingValueType),
        ),
        Field("group"),
    ),
    columns=("key", "label_bn", "value_type", "group"),
)

# ── Trainers ────────────────────────────────────────────────────────────────
INSTRUCTORS = Screen(
    endpoint="admin_instructors",
    path="/instructors",
    title="Trainers",
    model=Instructor,
    intro=(
        "The people who teach. Every field here is shown on /trainers; a trainer with "
        "no portrait is drawn with their initial. One entry per line for the lists."
    ),
    label_field="name_bn",
    order_by=("sort_order", "id"),
    slug_field="slug",
    # A trainer's portrait: the library picker, an upload and a remove, rendered by the
    # `media_field` macro because `photo_id` points at `media_items`.
    media_field="photo_id",
    fields=(
        Field("name_bn", label="Name", required=True),
        Field("name_en", label="Name (English)"),
        Field("slug", label="URL slug", required=True, hint="Lowercase Latin, e.g. nazmul-hasan"),
        Field(
            "photo_id",
            kind=REF,
            choices_ref="MediaItem",
            label="Portrait",
            hint=(
                "Shown on the trainer's card. Without one, the card draws their initial "
                "— which is a perfectly good answer, and better than a stock photograph."
            ),
        ),
        Field(
            "status",
            kind=SELECT,
            required=True,
            choices=tuple((member.value, enum_label(member)) for member in InstructorStatus),
        ),
        Field("status_label_bn", hint="What the card shows, e.g. সাবেক প্রশিক্ষক (১ম ব্যাচ)"),
        Field("designation_bn", label="Designation"),
        Field("credentials_bn", label="Experience", hint="Shown as the অভিজ্ঞতা line."),
        Field("tenure_bn", label="Tenure"),
        Field("academic_bn", label="Academic background"),
        Field("bio_bn", kind=TEXTAREA),
        Field("quote_bn", kind=TEXTAREA, label="Quotation"),
        Field("specialties_bn", kind=LINES, label="Specialties", hint="One per line — each becomes a chip."),
        Field("contributions_bn", kind=LINES, label="Contributions", hint="One per line."),
        Field("hours_taught_bn", label="Teaching hours"),
        Field("batch_bn", label="Batch"),
        Field("students_trained_bn", label="Trainees taught"),
        Field("slide_number_bn", label="Slide number"),
        Field("slide_number_en", label="Slide number (English)"),
        Field("sort_order", kind=NUMBER, minimum=0, maximum=999),
        Field("is_active", kind=CHECKBOX, label="Show on the site"),
    ),
    columns=("sort_order", "name_bn", "status", "designation_bn", "is_active"),
)


def register_all() -> None:
    """Attach every screen. Called once, from the admin package.

    A function rather than module-level calls: importing this module twice (which a
    reloader does) must not try to add the same rule twice, and Flask raises rather
    than warning when an endpoint is registered again.
    """
    register(COURSE)
    register(COURSE_MODULES)
    register(INSTITUTIONS)
    register(FAQS)
    register(STATS)
    register(SETTINGS)
    register(INSTRUCTORS)


__all__ = [
    "COURSE",
    "COURSE_MODULES",
    "FAQS",
    "INSTRUCTORS",
    "INSTITUTIONS",
    "SETTINGS",
    "STATS",
    "register_all",
]
