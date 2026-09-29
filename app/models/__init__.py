"""Model package — importing it registers every table on ``db.metadata``.

§10 names **17 tables**, and §11.3 adds the four that the React half used to hold as
TypeScript constants: the course phases, the training tools, the cohort's work and the
trainers. ``EXPECTED_TABLES`` below is asserted by ``tests/test_models.py`` so a table
cannot be added or lost without someone deciding to change this number and saying why
in the diff — which is exactly what happened here: 17 became 21 when the front end's
content moved into the database.

Migrations are auto-generated from this metadata, so an unimported model is a
table that silently never gets created — which is why every module is imported
here and the test checks the number rather than the imports.
"""

from __future__ import annotations

from app.models.admin import AdminUser
from app.models.cms import Faq, Page, PageSection, Setting, Stat
from app.models.course import Course, CourseModule, Institution
from app.models.media import MediaItem
from app.models.ops import AuditLog, Backup, ContactMessage, Import, LoginAttempt
from app.models.people import (
    ConsentEvent,
    Participant,
    PublishWithoutConsentError,
    build_search_blob,
    normalise_query,
)
from app.models.programme import BatchWork, CoursePhase, Instructor, TrainingTool

#: Every table, by name. Asserted, not decorative.
EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        # identity (§10.1)
        "admin_users",
        # CMS (§10.2)
        "pages",
        "page_sections",
        "faqs",
        "stats",
        "settings",
        # people (§10.3)
        "participants",
        "consent_events",
        # course and institution (§10.4)
        "courses",
        "course_modules",
        "institutions",
        # media and operations (§10.5)
        "media_items",
        "contact_messages",
        "audit_logs",
        "imports",
        "login_attempts",
        "backups",
        # what the React half renders (§11.3) — these four were constants in
        # `frontend/src/data/mockData.ts` until the front end stopped carrying
        # content of its own.
        "course_phases",
        "training_tools",
        "batch_works",
        "instructors",
    }
)

#: Columns that must NEVER exist on `participants` (§5.2, §13.3). Asserted by test.
#:
#: AMENDED — the four photographic names came out of this set, and ONE of them came back
#: as a permitted pair. §5.1 forbade a participant photograph, and this list was written
#: when no such column existed; the programme office then asked for portraits on the
#: register cards and the profile. That is a decision about PUBLISHING, so the rule was
#: changed deliberately rather than the check being loosened:
#:
#:   * `photo_id` may exist, and `CONSENTED_PARTICIPANT_COLUMNS` below says what has to
#:     sit beside it. The database enforces the pairing with a CHECK constraint, so the
#:     permission is not a convention the admin could forget.
#:   * `photo_path`, `photo`, `image`, `image_id`, `avatar`, `portrait` and their `_id`
#:     forms stay OUT of the schema — there is one way to attach a picture (a media row),
#:     and a second column is how two of them end up disagreeing.
#:   * Everything else on the list stands unchanged: no phone, no email, no NID, no
#:     date of birth, no address, no guardian, no marks.
PROHIBITED_PARTICIPANT_COLUMNS: frozenset[str] = frozenset(
    {
        "photo_path", "photo", "media_id",
        "image", "image_id", "avatar", "avatar_id", "portrait", "portrait_id",
        "phone", "mobile", "telephone",
        "email", "email_address",
        "nid", "national_id", "birth_registration", "birth_registration_number",
        "dob", "date_of_birth",
        "blood_group",
        "address", "full_address", "permanent_address", "present_address",
        "guardian_name", "father_name", "mother_name",
        "signature", "signature_path",
        "roll", "roll_number", "registration_number", "exam_marks", "marks",
    }
)

#: Prohibited columns that ARE allowed, each mapped to the column that authorises it.
#:
#: `flask check-db` fails if the authorising column is missing, so the exception cannot
#: outlive the permission it depends on — a `photo_id` with no `image_consent` beside it
#: is a photograph on a public site with nothing recording that its subject agreed.
CONSENTED_PARTICIPANT_COLUMNS: dict[str, str] = {
    "photo_id": "image_consent",
}

__all__ = [
    "CONSENTED_PARTICIPANT_COLUMNS",
    "EXPECTED_TABLES",
    "AdminUser",
    "AuditLog",
    "Backup",
    "BatchWork",
    "ConsentEvent",
    "ContactMessage",
    "Course",
    "CourseModule",
    "CoursePhase",
    "Faq",
    "Import",
    "Institution",
    "Instructor",
    "LoginAttempt",
    "MediaItem",
    "Page",
    "PageSection",
    "Participant",
    "PublishWithoutConsentError",
    "Setting",
    "Stat",
    "TrainingTool",
    "build_search_blob",
    "normalise_query",
]
