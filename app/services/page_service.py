"""Render a page from its sections. plan.md §9.3, step 3.4.

    render_page_by_slug("home", request)  ->  PageRender | None

THIS IS WHERE §9.3's FOUR RULES ARE ACTUALLY ENFORCED

  1. An unknown section `type` RAISES.
     Raised by `get_section`, deliberately not caught here. A row the code cannot
     interpret is a page quietly missing a block, and the only way that stays visible
     is if it is loud.

  2. A section whose payload fails validation is NOT RENDERED, and is FLAGGED.
     Dropped silently, it is a gap nobody sees. So it is dropped and its Bangla reason
     is collected in `PageRender.problems`, which the admin shows (§11.2) and which
     `render-check` can assert on. The rest of the page still renders — one bad section
     must not take down a page that is otherwise fine.

  3. `rich_text` bodies are sanitised. Done in the section module, on the way out as
     well as on the way in, so a body written before a change to the allowlist does not
     stay permissive forever.

  4. Sections render in `sort_order`, and `is_visible = false` is SKIPPED ENTIRELY.
     Not hidden with CSS. A section that is in the HTML but hidden still leaks its
     content to view-source, to a screen reader that ignores `display:none` in some
     modes, and to anyone who reads the response. `visible_sections` filters in Python
     so there is no version of the page that contains it.

WHY `PageRender` CARRIES `problems` RATHER THAN LOGGING THEM
    A log line about a broken section is read by an operator, days later, if at all. A
    list on the render object is read by the admin screen that can fix it and by the
    test that asserts it. Same information, opposite outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from app.sections.registry import render_section, validate_section


@dataclass(frozen=True)
class RenderedSection:
    """One section, ready to render: which template, with which context."""

    type: str
    template: str
    context: dict[str, Any]
    #: The `page_sections` row, for the admin anchor and for debugging.
    row: Any = None


@dataclass
class PageRender:
    """A page and everything that should appear on it."""

    page: Any
    sections: list[RenderedSection] = field(default_factory=list)
    #: Bangla reasons for sections that were dropped, each naming the section and the
    #: field. Empty on a healthy page.
    problems: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when there is nothing to show.

        The route renders an honest empty state for this rather than a bare page
        (step 3.4's "Done when"). A published page with no visible sections is a
        content mistake, and an empty state says so; a blank layout just looks broken.
        """
        return not self.sections


def get_page(slug: str, *, published_only: bool = True):
    """A page by slug, or None.

    Unpublished pages return None rather than raising, so the route can 404 — which is
    also what an unknown slug produces. The two must be indistinguishable from outside
    or the URL becomes an oracle for which drafts exist (§11.3's rule, on the public
    side).
    """
    from app.extensions import db
    from app.models import Page

    if not slug or not isinstance(slug, str):
        return None

    stmt = select(Page).where(Page.slug == slug)
    if published_only:
        stmt = stmt.where(Page.is_published.is_(True))
    return db.session.execute(stmt).scalars().first()


def visible_sections(page) -> list[Any]:
    """A page's sections in render order, with the invisible ones REMOVED.

    Filtered in Python rather than in the template, so that an invisible section is not
    present in the response at all (§9.3 rule 4). `sort_order` second, `id` third, so a
    page whose sections share a `sort_order` — which happens whenever an editor inserts
    one without renumbering — still renders in a stable order instead of whatever the
    database happened to return.
    """
    if page is None:
        return []
    return sorted(
        (row for row in page.sections if row.is_visible),
        key=lambda row: (row.sort_order, row.id or 0),
    )


def render_page(page, request: Any = None) -> PageRender:
    """Build the render payload for a page.

    A section that fails validation is dropped and recorded; an unknown type raises.
    """
    result = PageRender(page=page)
    if page is None:
        return result

    for row in visible_sections(page):
        # Rule 1: this raises for an unknown type, on purpose.
        ok, reason = validate_section(row.type, row.content or {})
        if not ok:
            # Rule 2: dropped, NOT rendered, and flagged with the section type and the
            # reason so an editor is told which block and which field.
            result.problems.append(f"“{row.type}” সেকশনটি দেখানো হয়নি: {reason}")
            continue

        rendered = render_section(row, request)
        result.sections.append(
            RenderedSection(
                type=rendered["type"],
                template=rendered["template"],
                context=rendered["context"],
                row=row,
            )
        )

    return result


def render_page_by_slug(slug: str, request: Any = None) -> PageRender | None:
    """Convenience for a route: fetch a published page and render it.

    Returns None when the page does not exist or is not published, which the route
    turns into a 404. A page that exists but has nothing to show returns a PageRender
    with `is_empty` set, so the route can distinguish "no such page" from "this page is
    empty" — the first is a 404, the second is an empty state.
    """
    page = get_page(slug)
    if page is None:
        return None
    return render_page(page, request)


def nav_pages():
    """Published pages that belong in the header/footer nav, in order (§6.3).

    Falls back to nothing rather than raising when the database is unreachable: the
    navigation is drawn on every page including the error pages, and an error page that
    raises a second exception is the one place a visitor sees nothing at all.
    """
    from app.extensions import db
    from app.models import Page

    try:
        stmt = (
            select(Page)
            .where(Page.is_published.is_(True), Page.show_in_nav.is_(True))
            .order_by(Page.sort_order, Page.id)
        )
        return list(db.session.execute(stmt).scalars())
    except Exception:  # noqa: BLE001 — the DB may be down while rendering a 500 page
        return []
