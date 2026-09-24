"""The 13 section types and their schemas. §4.2, §9.3, steps 2.10 and 2.13.

WHY THE REGISTRY IS ASSERTED SO HEAVILY
    The section registry is the contract between the admin editor and the public
    renderer. If a type exists in the registry but not in the database, or a schema
    drifts from what the seeder writes, the failure surfaces as a blank area on a
    live page — the single hardest class of bug to notice, because a page that is
    missing one block still looks like a page.

    §9.3 rule 1 also makes an important choice worth testing: an UNKNOWN type RAISES
    rather than being skipped. A silently skipped section is a page quietly missing
    something, which is precisely what nobody would notice.
"""

from __future__ import annotations

import pytest

from app.constants import SectionType
from app.sections import registry


def test_thirteen_section_types_are_declared():
    """§4.2 lists 13. The number is asserted because "we added one and forgot the
    renderer" is a normal mistake, and counting is the cheapest way to catch it."""
    assert len(SectionType) == 13
    assert len(registry.SECTION_SCHEMAS) == 13


def test_every_type_has_a_schema():
    for section_type in SectionType:
        assert section_type in registry.SECTION_SCHEMAS, (
            f"{section_type} is declared as a type but has no schema, so the admin "
            "would offer an editor a form that cannot be validated"
        )


def test_no_schema_exists_for_an_undeclared_type():
    """The reverse direction."""
    for key in registry.SECTION_SCHEMAS:
        assert key in set(SectionType), f"schema for unknown type {key!r}"


def test_section_choices_covers_every_type_with_a_bangla_label_and_hint():
    choices = registry.section_choices()
    assert len(choices) == 13
    for choice in choices:
        assert choice["value"]
        assert choice["label"], f"{choice['value']} has no Bangla label"
        assert choice["hint"], f"{choice['value']} has no hint for the picker"
        # The labels and hints are what an editor reads, so they must be Bangla.
        assert not choice["label"].isascii()
        assert not choice["hint"].isascii()


def test_get_schema_raises_for_an_unknown_type():
    """§9.3 rule 1 — raise, do not skip."""
    with pytest.raises(registry.SectionError):
        registry.get_schema("not_a_real_section_type")


def test_validate_section_raises_for_an_unknown_type():
    """A programming error is a raise; bad DATA is a return value. The two must not
    be confused, or an editor's typo becomes a 500."""
    with pytest.raises(registry.SectionError):
        registry.validate_section("nope", {})


# ─────────────────────────────────────────────────────────────────────────────
# Validation returns a Bangla reason, never raises, for bad data
# ─────────────────────────────────────────────────────────────────────────────


def test_a_missing_required_field_is_reported_in_bangla():
    ok, reason = registry.validate_section(SectionType.HERO, {})
    assert ok is False
    assert reason
    assert not reason.isascii(), "the reason an editor reads must be in Bangla"


def test_a_valid_hero_passes():
    ok, reason = registry.validate_section(
        SectionType.HERO, {"heading_bn": "সিলেটের যুবকদের জন্য এআই প্রশিক্ষণ"}
    )
    assert ok, reason


def test_a_non_dict_payload_is_rejected_not_raised():
    """The admin form and the seed JSON can both hand over anything."""
    ok, reason = registry.validate_section(SectionType.HERO, "not a dict")
    assert ok is False
    assert reason


def test_an_over_long_string_is_rejected():
    ok, reason = registry.validate_section(SectionType.HERO, {"heading_bn": "ক" * 500})
    assert ok is False
    assert reason


def test_an_integer_out_of_range_is_rejected():
    ok, reason = registry.validate_section(
        SectionType.PARTICIPANT_GRID, {"limit": 9999}
    )
    assert ok is False
    assert reason


def test_an_enum_outside_its_choices_is_rejected():
    ok, reason = registry.validate_section(
        SectionType.PARTICIPANT_GRID, {"sort": "by_whatever"}
    )
    assert ok is False
    assert reason


# ─────────────────────────────────────────────────────────────────────────────
# CTA href validation — a CTA in a CMS is an open redirect unless constrained
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "href",
    ["javascript:alert(1)", "JavaScript:alert(1)", "data:text/html;base64,PHNjcmlwdD4="],
)
def test_a_dangerous_cta_href_is_rejected(href):
    """`javascript:` in a CMS field is stored XSS waiting for a click."""
    ok, reason = registry.validate_section(
        SectionType.HERO,
        {"heading_bn": "শিরোনাম", "primary_cta": {"label": "যান", "href": href}},
    )
    assert ok is False, f"{href!r} was accepted as a CTA target"
    assert reason


def test_an_external_cta_href_is_rejected():
    """A call to action pointing off-site turns a government page into a redirect.

    Only this site's own origins are allowed. If a genuine external link is ever
    needed it should be a plain link in rich text, where it is visibly a link.
    """
    ok, reason = registry.validate_section(
        SectionType.HERO,
        {
            "heading_bn": "শিরোনাম",
            "primary_cta": {"label": "যান", "href": "https://example.com/phish"},
        },
    )
    assert ok is False
    assert reason


def test_an_internal_cta_href_is_accepted():
    ok, reason = registry.validate_section(
        SectionType.HERO,
        {"heading_bn": "শিরোনাম", "primary_cta": {"label": "ব্যাচ ১ দেখুন", "href": "/batch-1"}},
    )
    assert ok, reason


def test_a_cta_without_a_label_is_rejected():
    """A button with no text is unclickable and invisible to a screen reader."""
    ok, reason = registry.validate_section(
        SectionType.HERO,
        {"heading_bn": "শিরোনাম", "primary_cta": {"label": "", "href": "/batch-1"}},
    )
    assert ok is False
    assert reason


# ─────────────────────────────────────────────────────────────────────────────
# The seeded content must satisfy the registry — the round trip that matters
# ─────────────────────────────────────────────────────────────────────────────


def test_every_seeded_section_validates(seeded, session):
    """The real seeder's output against the real schemas.

    This is the test that catches drift between `app/seeds/pages.json` and the
    registry. Without it, a schema change breaks seeding at deploy time — on the
    server, at the one moment nobody wants to be debugging.
    """
    from sqlalchemy import select

    from app.models import PageSection

    sections = session.execute(select(PageSection)).scalars().all()
    assert sections, "the seeder produced no sections at all"

    failures = []
    for section in sections:
        ok, reason = registry.validate_section(section.type, section.content or {})
        if not ok:
            failures.append(f"#{section.id} type={section.type}: {reason}")

    assert not failures, "seeded sections do not satisfy their own schema:\n  " + "\n  ".join(failures)


def test_seeded_pages_are_drafts_not_published(seeded, session):
    """Seeding must never publish. A half-written page going live on first deploy is
    exactly what the draft state exists to prevent (§4.3, §11.2)."""
    from sqlalchemy import select

    from app.models import Page

    pages = session.execute(select(Page)).scalars().all()
    assert pages
    published = [p.slug for p in pages if p.is_published]
    assert not published, f"the seeder published pages: {published}"


def test_seeded_pages_cannot_publish_without_visible_sections(seeded, session):
    """§11.2: an empty page is worse than a draft, because it looks like the site is
    broken. Every seeded page has sections, so every one of them CAN publish."""
    from sqlalchemy import select

    from app.models import Page

    for page in session.execute(select(Page)).scalars().all():
        allowed, reason = page.can_publish
        assert allowed, f"seeded page {page.slug!r} cannot publish: {reason}"
