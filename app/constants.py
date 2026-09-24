"""Enumerations — the single source of truth for every closed vocabulary.

plan.md §9.1 ("enums: outcome types, education, consent sources, section types")
and §2.8 of the execution plan: *"no enum value is written as a string literal
anywhere else in the codebase."*

WHY StrEnum
    These values are stored in the database and compared in templates. A plain
    ``str`` would let a typo through silently; an ``Enum`` of non-str members
    complicates SQLAlchemy and Jinja. ``StrEnum`` (3.11+) is both — it *is* a
    string at runtime, so ``participant.education == "HSC"`` still works, but a
    misspelling raises immediately instead of writing bad data.

WHY THE _LABELS MAPS EXIST
    The public site and the admin are both Bangla-first (§14.1). The stored value
    must stay stable Latin so a label can be reworded without a migration — which
    is exactly why the label is a separate mapping rather than the enum value.
"""

from __future__ import annotations

from enum import StrEnum


# ── Section types (§4.2) ─────────────────────────────────────────────────────
# The 13. Fixed, not free-form: a generic block builder cannot be validated and
# lets the admin break the design system (§4.2).
class SectionType(StrEnum):
    HERO = "hero"
    RICH_TEXT = "rich_text"
    STAT_STRIP = "stat_strip"
    FACT_LIST = "fact_list"
    MODULE_LIST = "module_list"
    PARTICIPANT_GRID = "participant_grid"
    GALLERY_STRIP = "gallery_strip"
    MEDIA_FEATURE = "media_feature"
    FAQ_LIST = "faq_list"
    QUOTE = "quote"
    CTA_BAND = "cta_band"
    INSTITUTION_CARD = "institution_card"
    TIMELINE = "timeline"


SECTION_TYPE_LABELS: dict[str, str] = {
    SectionType.HERO: "হিরো",
    SectionType.RICH_TEXT: "রিচ টেক্সট",
    SectionType.STAT_STRIP: "পরিসংখ্যান সারি",
    SectionType.FACT_LIST: "তথ্যতালিকা",
    SectionType.MODULE_LIST: "মডিউল তালিকা",
    SectionType.PARTICIPANT_GRID: "প্রশিক্ষণার্থী গ্রিড",
    SectionType.GALLERY_STRIP: "গ্যালারি সারি",
    SectionType.MEDIA_FEATURE: "মিডিয়া ফিচার",
    SectionType.FAQ_LIST: "প্রশ্নোত্তর",
    SectionType.QUOTE: "উদ্ধৃতি",
    SectionType.CTA_BAND: "অ্যাকশন ব্যান্ড",
    SectionType.INSTITUTION_CARD: "প্রতিষ্ঠান কার্ড",
    SectionType.TIMELINE: "সময়রেখা",
}

# One-line description per type, shown in the section picker (§11.2).
SECTION_TYPE_HINTS: dict[str, str] = {
    SectionType.HERO: "পৃষ্ঠার প্রধান শিরোনাম, উপশিরোনাম ও বাটন।",
    SectionType.RICH_TEXT: "স্যানিটাইজড এইচটিএমএল বডি।",
    SectionType.STAT_STRIP: "সংজ্ঞায়িত পরিসংখ্যানের সারি।",
    SectionType.FACT_LIST: "লেবেল-মান জোড়া।",
    SectionType.MODULE_LIST: "কোর্সের মডিউলগুলো।",
    SectionType.PARTICIPANT_GRID: "সম্মতিপ্রাপ্ত প্রশিক্ষণার্থীদের কার্ড।",
    SectionType.GALLERY_STRIP: "ছবি বা ভিডিও লিংকের গ্রিড।",
    SectionType.MEDIA_FEATURE: "ছবি ও টেক্সট পাশাপাশি।",
    SectionType.FAQ_LIST: "প্রশ্নোত্তরের তালিকা।",
    SectionType.QUOTE: "একটি উদ্ধৃতি (সম্মতি আবশ্যক)।",
    SectionType.CTA_BAND: "পৃষ্ঠার শেষে একটি কার্যক্রমের আহ্বান।",
    SectionType.INSTITUTION_CARD: "প্রতিষ্ঠানের তথ্য।",
    SectionType.TIMELINE: "তারিখভিত্তিক ঘটনাপ্রবাহ।",
}


# ── Participants (§5.1, §5.3) ────────────────────────────────────────────────
class Education(StrEnum):
    HSC = "HSC"
    DIPLOMA = "Diploma"
    DEGREE = "Degree"
    HONOURS = "Honours"
    OTHER = "Other"


EDUCATION_LABELS: dict[str, str] = {
    Education.HSC: "এইচএসসি",
    Education.DIPLOMA: "ডিপ্লোমা",
    Education.DEGREE: "স্নাতক",
    Education.HONOURS: "সম্মান",
    Education.OTHER: "অন্যান্য",
}


class OutcomeType(StrEnum):
    EMPLOYMENT = "employment"
    FREELANCING = "freelancing"
    FURTHER_STUDY = "further_study"
    BUSINESS = "business"
    TEACHING = "teaching"
    OTHER = "other"


OUTCOME_LABELS: dict[str, str] = {
    OutcomeType.EMPLOYMENT: "কর্মসংস্থান",
    OutcomeType.FREELANCING: "ফ্রিল্যান্সিং",
    OutcomeType.FURTHER_STUDY: "আরও পড়াশোনা",
    OutcomeType.BUSINESS: "ব্যবসা",
    OutcomeType.TEACHING: "শিক্ষকতা",
    OutcomeType.OTHER: "অন্যান্য",
}

# §6.4 lists the five filterable outcomes. `other` is deliberately NOT a filter:
# a bucket of "everything else" is not a useful thing to browse, and its size can
# itself be identifying when the cohort is small.
FILTERABLE_OUTCOMES: tuple[OutcomeType, ...] = (
    OutcomeType.EMPLOYMENT,
    OutcomeType.FREELANCING,
    OutcomeType.FURTHER_STUDY,
    OutcomeType.BUSINESS,
    OutcomeType.TEACHING,
)


class ConsentSource(StrEnum):
    WRITTEN_FORM = "written_form"
    SMS = "sms"
    EMAIL = "email"
    VERBAL_WITNESSED = "verbal_witnessed"
    PROGRAMME_TERMS = "programme_terms"


CONSENT_SOURCE_LABELS: dict[str, str] = {
    ConsentSource.WRITTEN_FORM: "লিখিত ফর্ম",
    ConsentSource.SMS: "এসএমএস",
    ConsentSource.EMAIL: "ইমেইল",
    ConsentSource.VERBAL_WITNESSED: "মৌখিক (সাক্ষীসহ)",
    ConsentSource.PROGRAMME_TERMS: "কর্মসূচির শর্তাবলি",
}


class ConsentAction(StrEnum):
    GRANTED = "granted"
    WITHDRAWN = "withdrawn"
    UPDATED = "updated"


# ── CMS (§10.2) ──────────────────────────────────────────────────────────────
class SettingValueType(StrEnum):
    STRING = "string"
    INT = "int"
    BOOL = "bool"
    JSON = "json"


class StatSource(StrEnum):
    MANUAL = "manual"
    COMPUTED = "computed"


# ── Media (§10.5, §13.2) ─────────────────────────────────────────────────────
class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO_LINK = "video_link"


ALLOWED_IMAGE_MIME: tuple[str, ...] = ("image/jpeg", "image/png", "image/webp")
ALLOWED_IMAGE_EXTENSIONS: tuple[str, ...] = ("jpg", "jpeg", "png", "webp")

# SVG is deliberately absent. An SVG can carry script, and it would be served
# from the same origin as the admin session (§13.2).
REJECTED_UPLOAD_EXTENSIONS: tuple[str, ...] = ("svg", "svgz")


# ── Operations (§10.5) ───────────────────────────────────────────────────────
class MessageStatus(StrEnum):
    NEW = "new"
    READ = "read"
    REPLIED = "replied"
    CLOSED = "closed"


MESSAGE_STATUS_LABELS: dict[str, str] = {
    MessageStatus.NEW: "নতুন",
    MessageStatus.READ: "পঠিত",
    MessageStatus.REPLIED: "উত্তর দেওয়া হয়েছে",
    MessageStatus.CLOSED: "সমাপ্ত",
}


class ImportKind(StrEnum):
    PARTICIPANTS = "participants"


class ImportStatus(StrEnum):
    DRY_RUN = "dry_run"
    COMMITTED = "committed"
    FAILED = "failed"


class BackupKind(StrEnum):
    DATABASE = "database"
    UPLOADS = "uploads"
    FULL = "full"


class BackupStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"


class AuditAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    PUBLISH = "publish"
    UNPUBLISH = "unpublish"
    CONSENT_GRANT = "consent_grant"
    CONSENT_WITHDRAW = "consent_withdraw"
    LOGIN_OK = "login_ok"
    LOGIN_FAIL = "login_fail"
    LOGIN_LOCKED = "login_locked"
    IMPORT = "import"
    EXPORT = "export"
    SETTING_UPDATE = "setting_update"
    BACKUP = "backup"
    RESTORE = "restore"


# ── Page slugs (§4.3) ────────────────────────────────────────────────────────
# The 8 public pages. Latin, lowercase, hyphenated, stable forever — Bangla lives
# in labels only (§4.3).
class PageSlug(StrEnum):
    HOME = "home"
    COURSE = "course"
    BATCH_ONE = "batch-1"
    PROFILE = "batch-1/<slug>"  # not a page record; generated from a participant
    GALLERY = "gallery"
    ABOUT = "about"
    CONTACT = "contact"
    PRIVACY = "privacy"


# ── Feature flags (§16.3) ────────────────────────────────────────────────────
class FeatureFlag(StrEnum):
    MAINTENANCE_MODE = "maintenance_mode"
    CONTACT_FORM_ENABLED = "contact_form_enabled"
    PARTICIPANT_PAGES_ENABLED = "participant_pages_enabled"
    PARTICIPANT_SEARCH_ENABLED = "participant_search_enabled"
    GALLERY_ENABLED = "gallery_enabled"
    STATS_PUBLISHED = "stats_published"


# ── Nav (§6.3) ───────────────────────────────────────────────────────────────
HEADER_NAV: tuple[dict[str, str], ...] = (
    {"slug": "home", "label": "হোম", "path": "/"},
    {"slug": "course", "label": "কোর্স", "path": "/course"},
    {"slug": "batch-1", "label": "ব্যাচ ১", "path": "/batch-1"},
    {"slug": "gallery", "label": "গ্যালারি", "path": "/gallery"},
    {"slug": "about", "label": "আমাদের সম্পর্কে", "path": "/about"},
    {"slug": "contact", "label": "যোগাযোগ", "path": "/contact"},
)
