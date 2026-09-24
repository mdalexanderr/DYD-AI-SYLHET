"""Model package — importing it registers every table on ``db.metadata``.

§10: **17 tables.** ``EXPECTED_TABLES`` below is asserted by ``tests/test_models.py``
so a table cannot be added or lost without someone deciding to change this number
and saying why in the diff. That is the point: the count is a claim the plan makes,
and an unasserted claim drifts.

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

#: The 17 tables of §10, by table name. Asserted, not decorative.
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
    }
)

#: Columns that must NEVER exist on `participants` (§5.2, §13.3). Asserted by test.
PROHIBITED_PARTICIPANT_COLUMNS: frozenset[str] = frozenset(
    {
        "photo_path", "photo", "photo_id", "media_id", "image", "image_id",
        "avatar", "avatar_id", "portrait", "portrait_id",
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

__all__ = [
    "EXPECTED_TABLES",
    "PROHIBITED_PARTICIPANT_COLUMNS",
    "AdminUser",
    "AuditLog",
    "Backup",
    "ConsentEvent",
    "ContactMessage",
    "Course",
    "CourseModule",
    "Faq",
    "Import",
    "Institution",
    "LoginAttempt",
    "MediaItem",
    "Page",
    "PageSection",
    "Participant",
    "PublishWithoutConsentError",
    "Setting",
    "Stat",
    "build_search_blob",
    "normalise_query",
]
