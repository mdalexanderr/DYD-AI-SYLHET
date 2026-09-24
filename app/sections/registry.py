"""The section registry — which types exist, and how to reach them. plan.md §9.3.

    SECTIONS["hero"]               -> the HeroSection instance
    validate_section("hero", {...}) -> (ok, bangla_reason)   raises on an unknown type
    render_section(page_section)    -> {"type", "template", "context", "row"}

WHY A REGISTRY AND NOT DIRECT IMPORTS
    The admin picker, the publish gate, the page renderer and `flask render-check` all
    need "every type". If each of them imported only the modules it cared about, a type
    could exist in one place and be absent from another — and the place it would be
    absent from is the admin picker, which is exactly how a section type becomes
    impossible to create.

WHY THE COMPLETENESS CHECK IS AT IMPORT TIME
    `SectionType` is the list of types the database, the seeds and the plan all refer
    to. A member with no module behind it is a type the admin offers and the renderer
    cannot draw, so the registry refuses to build rather than discovering it when a
    seeded page renders a blank block. This is the same reasoning as §9.3 rule 1
    (an unknown type raises) applied one level up.
"""

from __future__ import annotations

from typing import Any

from app.constants import SectionType
from app.sections.base import SectionBase, SectionError, validate_href
from app.sections.cta_band import CtaBandSection
from app.sections.fact_list import FactListSection
from app.sections.faq_list import FaqListSection
from app.sections.gallery_strip import GalleryStripSection
from app.sections.hero import HeroSection
from app.sections.institution_card import InstitutionCardSection
from app.sections.media_feature import MediaFeatureSection
from app.sections.module_list import ModuleListSection
from app.sections.participant_grid import ParticipantGridSection
from app.sections.quote import QuoteSection
from app.sections.rich_text import RichTextSection
from app.sections.stat_strip import StatStripSection
from app.sections.timeline import TimelineSection

#: The 13 modules of §4.2, in the order the admin picker lists them.
SECTION_CLASSES: tuple[type[SectionBase], ...] = (
    HeroSection,
    RichTextSection,
    StatStripSection,
    FactListSection,
    ModuleListSection,
    ParticipantGridSection,
    GalleryStripSection,
    MediaFeatureSection,
    FaqListSection,
    QuoteSection,
    CtaBandSection,
    InstitutionCardSection,
    TimelineSection,
)


def _build_registry() -> dict[str, SectionBase]:
    out: dict[str, SectionBase] = {}
    for section_class in SECTION_CLASSES:
        section = section_class()
        if section.type in out:
            raise SectionError(section.type, "two modules declare the same section type")
        out[section.type] = section

    missing = sorted(str(member) for member in SectionType if member not in out)
    if missing:
        raise SectionError(
            ", ".join(missing),
            "SectionType members with no section module — the admin would offer a type "
            "that cannot render",
        )
    return out


#: type -> instance. One instance per type: a section carries no per-render state, and
#: reusing it avoids re-reading the schema for every row of every page.
SECTIONS: dict[str, SectionBase] = _build_registry()

#: The Phase 2 name for the same mapping, kept so nothing that imported it breaks.
#: The registry IS the renderer dispatch table.
RENDERERS: dict[str, SectionBase] = SECTIONS

#: type -> schema. Derived rather than declared, so Phase 4's form generator reads the
#: schema the validator actually used and the two cannot drift.
SECTION_SCHEMAS: dict[str, dict[str, dict[str, Any]]] = {
    section_type: section.schema for section_type, section in SECTIONS.items()
}


def get_section(section_type: Any) -> SectionBase:
    """The instance for a type. RAISES for an unknown type (§9.3 rule 1).

    Raising rather than returning a fallback is the point: a section type that exists
    in the database but not in the code is a page quietly missing something, which is
    the one failure nobody notices until a human reads that page.
    """
    try:
        return SECTIONS[section_type]
    except (KeyError, TypeError) as exc:
        raise SectionError(str(section_type), "unknown section type") from exc


def get_schema(section_type: Any) -> dict[str, dict[str, Any]]:
    """The schema for a type, or raise."""
    return get_section(section_type).schema


def validate_section(section_type: Any, payload: Any) -> tuple[bool, str]:
    """Validate a payload. Returns (ok, bangla_reason).

    An unknown TYPE raises, because that is a programming error. A payload that fails
    returns False with a Bangla reason naming the field, because that is an editor
    typing something wrong and they need to be told which field (§9.3 rules 1 and 2,
    and step 3.1's "Done when").
    """
    return get_section(section_type).validate(payload)


def section_choices() -> list[dict[str, str]]:
    """The picker list for §11.2: value, Bangla label, one-line hint."""
    return [
        {
            "value": section_type,
            "label": section.label_bn,
            "hint": section.hint_bn,
        }
        for section_type, section in SECTIONS.items()
    ]


def render_section(section: Any, request: Any = None) -> dict[str, Any]:
    """Build the render payload for one `page_sections` row.

    Only builds. §9.3 rules 2 and 4 — a row that fails validation is not rendered, and
    an invisible row is skipped — are enforced by `page_service`, which is the caller
    that can record WHY a section was dropped and show it to an admin. Putting those
    decisions here would mean a silently skipped section with nothing to report.

    An unknown `type` still raises from `get_section`, because a row the code cannot
    interpret must be loud (rule 1).
    """
    impl = get_section(section.type)
    return {
        "type": section.type,
        "template": impl.template,
        "context": impl.context(section.content or {}, request),
        "row": section,
    }


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
