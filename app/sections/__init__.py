"""Section types. plan.md §4.2, §9.3, §9.1.

THE REGISTRY IS THE SINGLE SOURCE OF TRUTH FOR "WHICH TYPES EXIST"
    The admin picker (`section_choices`), the validator (`validate_section`), the page
    renderer (`render_section`) and `flask render-check` all read `registry`, so a
    section type can never exist in one place and be missing from another. §9.3 rule 1
    makes an unknown type RAISE rather than be skipped: a silently skipped section is a
    page quietly missing something, which is the one failure nobody notices until a
    human reads that page.

ONE MODULE PER TYPE, COLLECTED BY `registry`
    `app/sections/<type>.py` declares one type's schema, validation and template
    context. `registry.SECTION_CLASSES` lists all thirteen, and the registry refuses to
    build if `SectionType` has a member with no module behind it — which would be a
    type the admin offers and the renderer cannot draw.

WHY `RENDERERS` IS DECLARED AND EMPTY
    It is the type → callable mapping the page pipeline will drive (Phase 3). It
    lives here because this is the module that already knows the type list. It is
    left genuinely empty rather than stubbed with placeholders, because a renderer
    that returns a "coming soon" block makes a half-built page look finished.

WHY THESE NAMES ARE RE-EXPORTED
    So call sites can write `from app.sections import validate_section` and the file
    layout inside §9.3 stays free to change — splitting the 13 validators into one
    module per type, which is the plan's intent — without touching every caller.
"""

from __future__ import annotations

from app.sections.base import SectionBase, SectionError, validate_href
from app.sections.registry import (
    RENDERERS,
    SECTION_CLASSES,
    SECTION_SCHEMAS,
    SECTIONS,
    get_schema,
    get_section,
    render_section,
    section_choices,
    validate_section,
)

__all__ = [
    "RENDERERS",
    "SECTIONS",
    "SECTION_CLASSES",
    "SECTION_SCHEMAS",
    "SectionBase",
    "SectionError",
    "get_schema",
    "get_section",
    "render_section",
    "section_choices",
    "validate_href",
    "validate_section",
]
