"""The admin navigation, as data. plan.md §11.1.

WHY THE NAV LIVES HERE AND NOT IN THE TEMPLATE
    Three things read it: the rail in `admin/layout.html`, the dashboard's quick
    actions, and the "which section am I in" test that marks the active entry. A nav
    written out in the template is a nav that cannot be asserted against the route
    table, and `tests/test_admin_cms.py` does exactly that — every entry here must
    resolve to a real endpoint, or the rail is a list of 404s dressed up as a menu.

WHY THE GROUPS ARE NUMBERED
    The order is information. 01 is what a reader sees, 02 is the course the site
    documents, 03 is the people, 04 is what they sent us, 05 is what the system
    keeps. An operator's attention moves through the panel in that order, so the rail
    says so rather than sorting alphabetically and hiding the sequence.

WHY THE COUNTS ARE COMPUTED ON EVERY PAGE AND NOT CACHED IN A COLUMN
    Four `COUNT(*)`s on indexed tables. In exchange, the rail cannot lie: a stored
    count is wrong the moment a row is deleted by a path that forgot to decrement it,
    and a menu that says "3" when there are none is a menu an operator stops
    believing. `_counts()` memoises on `g` so it is four queries per request at most,
    not four per entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NavItem:
    """One entry in the rail.

    `children` are endpoints that belong to this entry without having their own link
    — the page editor under Pages, the participant record under Participants. Without
    them, opening a single record would light up nothing and the rail would look like
    it had lost the operator.
    """

    endpoint: str
    label: str
    icon: str
    count: str | None = None
    children: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NavGroup:
    index: str
    label: str
    items: tuple[NavItem, ...]


#: The rail, top to bottom. Every endpoint here is asserted to exist.
NAV_GROUPS: tuple[NavGroup, ...] = (
    NavGroup(
        index="01",
        label="Overview",
        items=(
            NavItem("admin.index", "Dashboard", "dashboard"),
        ),
    ),
    NavGroup(
        index="02",
        label="The site",
        items=(
            NavItem("admin.pages_list", "Pages", "pages", count="pages",
                    children=("admin.page_editor", "admin.page_preview")),
            NavItem("admin.media_library", "Media library", "media", count="media"),
            NavItem("admin.messages_list", "Messages", "messages", count="messages"),
        ),
    ),
    NavGroup(
        index="03",
        label="Course",
        items=(
            NavItem("admin.admin_course", "Course", "course"),
            NavItem("admin.admin_course_modules", "Modules", "modules"),
            NavItem("admin.admin_institutions", "Institutions", "institution"),
            NavItem("admin.admin_stats", "Statistics", "stats"),
            NavItem("admin.admin_faqs", "Questions", "faq"),
        ),
    ),
    NavGroup(
        index="04",
        label="People",
        items=(
            NavItem("admin.participants_list", "Participants", "people", count="participants",
                    children=("admin.participant_new", "admin.participant_detail")),
            NavItem("admin.participants_consent_dashboard", "Consent", "consent",
                    count="consent_due"),
            NavItem("admin.participants_import", "Import", "import"),
            NavItem("admin.admin_instructors", "Trainers", "trainers"),
        ),
    ),
    NavGroup(
        index="05",
        label="System",
        items=(
            NavItem("admin.admin_settings", "Settings", "settings"),
            NavItem("admin.audit_list", "Audit log", "audit"),
            NavItem("admin.backups_list", "Backups", "backup"),
        ),
    ),
)

#: The dashboard's quick actions, as (endpoint, label).
#:
#: NOT the first few rail entries. A dashboard that offers links the rail already
#: shows two centimetres to the left is a dashboard wasting its own header. These four
#: go somewhere the rail cannot: a new participant, a blank form, an upload, an import.
QUICK_ACTIONS: tuple[tuple[str, str], ...] = (
    ("admin.participant_new", "Add a participant"),
    ("admin.participants_import", "Import a CSV"),
    ("admin.media_library", "Upload images"),
    ("admin.pages_list", "Write a page"),
)


def quick_actions() -> list[dict[str, str]]:
    """The dashboard's action list. Resolved to dicts so the template can iterate."""
    return [{"endpoint": endpoint, "label": label} for endpoint, label in QUICK_ACTIONS]


def _counts() -> dict[str, int]:
    """The live counts the rail shows. Zero is a legitimate answer everywhere."""
    from flask import g

    cached = getattr(g, "_admin_nav_counts", None)
    if cached is not None:
        return cached

    from sqlalchemy import func, select

    from app.constants import MessageStatus
    from app.extensions import db
    from app.models import ContactMessage, MediaItem, Page, Participant

    def total(model: Any, *criteria: Any) -> int:
        stmt = select(func.count(model.id))
        for criterion in criteria:
            stmt = stmt.where(criterion)
        return int(db.session.execute(stmt).scalar_one())

    counts = {
        "pages": total(Page),
        "media": total(MediaItem),
        # "Messages" counts what is still open, not everything ever received: a
        # badge that only ever grows is a badge that gets ignored.
        "messages": total(
            ContactMessage,
            ContactMessage.status.in_((MessageStatus.NEW, MessageStatus.READ)),
        ),
        "participants": total(Participant),
        # The state §5.6 asks to be shown first: consented, but with no date, so
        # nothing publishes and no other number on the panel would mention them.
        "consent_due": total(
            Participant,
            Participant.consent_publication.is_(True),
            Participant.consent_date.is_(None),
            Participant.consent_withdrawn_at.is_(None),
        ),
    }

    g._admin_nav_counts = counts  # noqa: SLF001 — a per-request memo, by design
    return counts


def nav_groups() -> list[dict[str, Any]]:
    """The rail, with its counts resolved. A Jinja global."""
    try:
        counts = _counts()
    except Exception:  # noqa: BLE001
        # A rail is not worth a 500. If the database is unreachable the screens will
        # say so properly; the navigation still renders, without numbers.
        counts = {}

    return [
        {
            "index": group.index,
            "label": group.label,
            "items": [
                {
                    "endpoint": item.endpoint,
                    "label": item.label,
                    "icon": item.icon,
                    "children": item.children,
                    "count": counts.get(item.count, 0) if item.count else None,
                }
                for item in group.items
            ],
        }
        for group in NAV_GROUPS
    ]


__all__ = [
    "NAV_GROUPS",
    "QUICK_ACTIONS",
    "NavGroup",
    "NavItem",
    "nav_groups",
    "quick_actions",
]
