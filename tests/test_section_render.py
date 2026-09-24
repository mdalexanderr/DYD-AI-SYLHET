"""Section rendering rules and per-type round trips.
execution-plan steps 3.2, 3.3, 3.4; plan.md §9.3.

WHAT §9.3's FOUR RULES ARE, AND WHY EACH GETS ITS OWN TEST
    1. An unknown `type` RAISES rather than being skipped.
    2. A section failing validation is NOT RENDERED and is FLAGGED.
    3. `rich_text` bodies are sanitised on the way OUT as well as in.
    4. `sort_order` decides order, and `is_visible = false` is SKIPPED ENTIRELY — not
       hidden with CSS.

    Rule 4 is the one that looks like a style preference and is not. A section that is
    present in the HTML but hidden still leaks its content to view-source, to anyone
    who reads the response, and to assistive technology in some modes. "Not rendered"
    and "not visible" are different promises and only one of them is safe, so the test
    asserts the absence of the text from the rendered output rather than the CSS.
"""

from __future__ import annotations

import pytest

from app.constants import SectionType
from app.sections import registry
from app.services import page_service

# ─────────────────────────────────────────────────────────────────────────────
# A minimal VALID payload per type, and a payload that must be REJECTED.
# Written out rather than generated: a generated valid payload would pass by
# construction and would stop noticing when a schema gained a required field.
# ─────────────────────────────────────────────────────────────────────────────
VALID: dict[str, dict] = {
    SectionType.HERO: {"heading_bn": "সিলেটের যুবকদের জন্য প্রশিক্ষণ"},
    SectionType.RICH_TEXT: {"body_bn": "<p>বিষয়বস্তু</p>"},
    SectionType.STAT_STRIP: {"stat_keys": ["course_hours", "batch_number"]},
    SectionType.FACT_LIST: {"items": [{"label_bn": "মেয়াদ", "value_bn": "৩০০ ঘণ্টা"}]},
    SectionType.MODULE_LIST: {"course_id": 1},
    SectionType.PARTICIPANT_GRID: {},  # every field optional
    SectionType.GALLERY_STRIP: {"media_ids": [1]},
    SectionType.MEDIA_FEATURE: {"media_id": 1},
    SectionType.FAQ_LIST: {},  # every field optional
    SectionType.QUOTE: {"quote_bn": "আমি শিখেছি।"},
    SectionType.CTA_BAND: {"heading_bn": "তালিকা দেখুন"},
    SectionType.INSTITUTION_CARD: {"institution_id": 1},
    SectionType.TIMELINE: {"items": [{"date_bn": "প্রশিক্ষণ শুরু", "title_bn": "ক্লাস"}]},
}

REJECTED: dict[str, dict] = {
    SectionType.HERO: {"heading_bn": "ক" * 500},  # over max
    SectionType.RICH_TEXT: {},  # missing required body_bn
    SectionType.STAT_STRIP: {"stat_keys": []},  # required, min_items 1
    SectionType.FACT_LIST: {"items": [{"label_bn": "শুধু লেবেল"}]},  # pair missing value
    SectionType.MODULE_LIST: {},  # missing required course_id
    SectionType.PARTICIPANT_GRID: {"limit": "many"},  # not an int
    SectionType.GALLERY_STRIP: {"media_ids": []},  # required, min_items 1
    SectionType.MEDIA_FEATURE: {"media_id": "three"},  # ref must be an int
    SectionType.FAQ_LIST: {"faq_ids": "not a list"},
    SectionType.QUOTE: {},  # missing required quote_bn
    SectionType.CTA_BAND: {"heading_bn": "ঠিক আছে", "cta_href": "/x"},  # href with no label
    SectionType.INSTITUTION_CARD: {"institution_id": True},  # bool is not a ref
    SectionType.TIMELINE: {"items": [{"date_bn": "১"}]},  # timeline_item missing title_bn
}


def test_the_matrices_cover_all_thirteen_types():
    """A type added without a payload here would silently stop being tested."""
    assert set(VALID) == set(SectionType)
    assert set(REJECTED) == set(SectionType)


@pytest.mark.parametrize("section_type", list(SectionType))
def test_a_valid_payload_is_accepted(section_type):
    ok, reason = registry.validate_section(section_type, VALID[section_type])
    assert ok, f"{section_type} rejected a valid payload: {reason}"


@pytest.mark.parametrize("section_type", list(SectionType))
def test_an_invalid_payload_is_rejected_with_a_bangla_reason(section_type):
    """Step 3.1: "with the field name and the reason — not a generic error"."""
    ok, reason = registry.validate_section(section_type, REJECTED[section_type])
    assert not ok
    assert reason, f"{section_type} rejected a payload without saying why"
    assert not reason.isascii(), (
        f"{section_type} gave a non-Bangla reason an editor would have to translate: "
        f"{reason!r}"
    )


@pytest.mark.parametrize("section_type", list(SectionType))
def test_the_rejection_reason_names_the_field(section_type):
    """§11.2's publish gate shows this text. 'Something is wrong' is not actionable."""
    ok, reason = registry.validate_section(section_type, REJECTED[section_type])
    assert not ok
    # Every reason is built as “label” …, so a field label must be quoted in it.
    assert "“" in reason and "”" in reason, (
        f"{section_type}'s reason does not name a field: {reason!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# §9.3 rule 1 — an unknown type raises
# ─────────────────────────────────────────────────────────────────────────────
def test_an_unknown_type_raises_rather_than_being_skipped():
    with pytest.raises(registry.SectionError):
        registry.get_section("not_a_real_section_type")


def test_render_section_raises_for_an_unknown_type(app, session):
    """A row the code cannot interpret must be loud, not a blank block."""

    class FakeRow:
        type = "not_a_real_section_type"
        content: dict = {}

    with pytest.raises(registry.SectionError):
        registry.render_section(FakeRow())


# ─────────────────────────────────────────────────────────────────────────────
# §9.3 rules 2 and 4 — page_service
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def make_page(session):
    """Create a published page with the given sections.

    The slug is auto-numbered because `pages.slug` is UNIQUE and the `session` fixture
    is session-scoped: a fixed slug would only work for the first test in the file.
    """
    import itertools

    from app.models import Page, PageSection

    counter = itertools.count(1)

    def _make(sections: list[dict], *, slug: str | None = None, published: bool = True):
        slug = slug or f"test-page-{next(counter)}"
        page = Page(
            slug=slug,
            title_bn="পরীক্ষা",
            is_published=published,
            show_in_nav=False,
        )
        session.add(page)
        session.flush()
        for index, spec in enumerate(sections, start=1):
            session.add(
                PageSection(
                    page_id=page.id,
                    type=spec["type"],
                    sort_order=spec.get("sort_order", index),
                    is_visible=spec.get("is_visible", True),
                    content=spec.get("content", {}),
                )
            )
        session.commit()
        return page

    return _make


def test_invisible_sections_are_skipped_entirely(make_page):
    """§9.3 rule 4. Asserted on the render RESULT, not on the CSS.

    A section that reaches the template at all has already leaked. This asserts it is
    absent from `PageRender.sections`, which is the list the template iterates — so
    there is no version of the response that contains it.
    """
    page = make_page(
        [
            {
                "type": "rich_text",
                "is_visible": True,
                "content": {"body_bn": "<p>দৃশ্যমান</p>"},
            },
            {
                "type": "rich_text",
                "is_visible": False,
                "content": {"body_bn": "<p>লুকানো গোপনীয় লেখা</p>"},
            },
        ]
    )
    result = page_service.render_page(page)

    assert len(result.sections) == 1
    rendered = " ".join(str(section.context) for section in result.sections)
    assert "দৃশ্যমান" in rendered
    assert "লুকানো" not in rendered, (
        "an is_visible=false section reached the render list. §9.3 rule 4 requires it to "
        "be skipped entirely, not hidden with CSS."
    )


def test_sections_render_in_sort_order(make_page):
    page = make_page(
        [
            {"type": "rich_text", "sort_order": 30, "content": {"body_bn": "<p>তিন</p>"}},
            {"type": "rich_text", "sort_order": 10, "content": {"body_bn": "<p>এক</p>"}},
            {"type": "rich_text", "sort_order": 20, "content": {"body_bn": "<p>দুই</p>"}},
        ]
    )
    result = page_service.render_page(page)
    order = [section.row.sort_order for section in result.sections]
    assert order == [10, 20, 30]


def test_a_section_failing_validation_is_not_rendered_and_is_flagged(make_page):
    """§9.3 rule 2. Dropped AND reported — dropping silently is the failure mode."""
    page = make_page(
        [
            {"type": "rich_text", "content": {"body_bn": "<p>ঠিক আছে</p>"}},
            {"type": "quote", "content": {}},  # quote_bn is required
        ]
    )
    result = page_service.render_page(page)

    assert len(result.sections) == 1, "the broken section was rendered anyway"
    assert len(result.problems) == 1, "the broken section was dropped without a flag"
    assert "quote" in result.problems[0]
    assert not result.problems[0].isascii(), "the flag must be readable by an editor"


def test_one_broken_section_does_not_take_down_the_page(make_page):
    """The rest of the page still renders. A single bad block is not an outage."""
    page = make_page(
        [
            {"type": "hero", "sort_order": 1, "content": {"heading_bn": "শিরোনাম"}},
            {"type": "quote", "sort_order": 2, "content": {}},
            {
                "type": "rich_text",
                "sort_order": 3,
                "content": {"body_bn": "<p>শেষ</p>"},
            },
        ]
    )
    result = page_service.render_page(page)
    assert len(result.sections) == 2
    assert len(result.problems) == 1


def test_a_page_with_no_visible_sections_is_empty_not_broken(make_page):
    """Step 3.4's "Done when": an honest empty state, not a broken layout."""
    page = make_page([{"type": "rich_text", "is_visible": False, "content": {"body_bn": "x"}}])
    result = page_service.render_page(page)
    assert result.is_empty is True
    assert result.problems == []


def test_an_unpublished_page_is_not_returned(session, make_page):
    """A draft returns None so the route can 404 — same as an unknown slug."""
    make_page([{"type": "rich_text", "content": {"body_bn": "x"}}], slug="draft", published=False)
    assert page_service.get_page("draft") is None


def test_an_unknown_slug_returns_none(session):
    assert page_service.get_page("no-such-page") is None


# ─────────────────────────────────────────────────────────────────────────────
# §9.3 rule 3 — rich_text is sanitised on the way OUT
# ─────────────────────────────────────────────────────────────────────────────
def test_rich_text_is_sanitised_on_render(app, session):
    """A body written before a change to the allowlist must not stay permissive.

    This is why sanitising happens twice. The stored value here is deliberately hostile
    — as if it were written before `<script>` was removed from the allowlist.
    """
    from app.sections.rich_text import RichTextSection

    section = RichTextSection()
    context = section.context(
        {"body_bn": "<p>ঠিক আছে</p><script>alert(1)</script>"}, None
    )
    assert "<script" not in context["body_html"]
    assert "alert(1)" not in context["body_html"]
    assert "ঠিক আছে" in context["body_html"]


# ─────────────────────────────────────────────────────────────────────────────
# Every section template renders
# ─────────────────────────────────────────────────────────────────────────────
def test_every_type_has_a_template_on_disk():
    for section_type, section in registry.SECTIONS.items():
        path = app_templates() / section.template
        assert path.is_file(), f"{section_type} declares {section.template}, which is absent"


@pytest.mark.parametrize("section_type", list(SectionType))
def test_every_section_template_renders(app, session, section_type):
    """Step 3.2: each type renders. Undefined behaviour would raise under StrictUndefined.

    Rendered through Jinja with the real context builder, so a template that reads a
    key its module never sets fails here rather than on a live page.
    """
    from flask import render_template
    from jinja2 import StrictUndefined

    impl = registry.SECTIONS[section_type]
    payload = dict(VALID[section_type])
    # The ref-shaped payloads need real rows to resolve against.
    if section_type == SectionType.MODULE_LIST:
        payload = {"course_id": _make_course(session).id}
    elif section_type == SectionType.INSTITUTION_CARD:
        payload = {"institution_id": _make_institution(session).id}
    elif section_type in (SectionType.GALLERY_STRIP, SectionType.MEDIA_FEATURE):
        payload = {"media_ids": [_make_media(session).id]} if section_type == SectionType.GALLERY_STRIP else {"media_id": _make_media(session).id}

    original = app.jinja_env.undefined
    app.jinja_env.undefined = StrictUndefined
    if app.jinja_env.cache is not None:
        app.jinja_env.cache.clear()
    try:
        with app.test_request_context("/"):
            html = render_template(
                impl.template, context=impl.context(payload, None)
            )
    finally:
        app.jinja_env.undefined = original
        if app.jinja_env.cache is not None:
            app.jinja_env.cache.clear()

    assert html.strip(), f"{section_type}'s template rendered nothing"


def app_templates():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent / "app" / "templates"


def _make_course(session):
    from app.models import Course

    course = Course(slug="test-course", title_bn="কোর্স")
    session.add(course)
    session.commit()
    return course


def _make_institution(session):
    from app.models import Institution

    inst = Institution(slug="test-inst", name_bn="প্রতিষ্ঠান")
    session.add(inst)
    session.commit()
    return inst


def _make_media(session):
    from app.constants import MediaKind
    from app.models import MediaItem

    item = MediaItem(
        path="test/classroom.jpg",
        original_name="classroom.jpg",
        mime="image/jpeg",
        size_bytes=1024,
        kind=MediaKind.IMAGE,
        alt_bn="ক্লাসরুম",
        width=1600,
        height=900,
    )
    session.add(item)
    session.commit()
    return item
