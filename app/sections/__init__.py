"""Section types. plan.md §4.2, §9.3, §9.1.

THE REGISTRY IS THE SINGLE SOURCE OF TRUTH FOR "WHICH TYPES EXIST"
    The admin picker (`section_choices`), the validator (`validate_section`) and,
    from Phase 3, the page renderer all read `registry`, so a section type can never
    exist in one place and be missing from another. That is the whole reason §9.3
    rule 1 makes an unknown type RAISE rather than be skipped: a silently skipped
    section is a page quietly missing something, which is the one failure nobody
    notices until a human reads the page.

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

from app.sections.registry import (
    RENDERERS,
    SECTION_SCHEMAS,
    Field,
    SectionError,
    get_schema,
    section_choices,
    validate_section,
)

__all__ = [
    "RENDERERS",
    "SECTION_SCHEMAS",
    "Field",
    "SectionError",
    "get_schema",
    "section_choices",
    "validate_section",
]
