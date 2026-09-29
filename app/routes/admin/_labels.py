"""English labels for the admin panel. plan.md §11, §14.1.

THE ADMIN IS ENGLISH; THE SITE IS BANGLA
    §14.1 makes the public site Bangla-first and that has not changed. The panel is
    a different reader with a different job: one operator maintaining records, using
    the vocabulary of the CMS. So the interface is English, and the CONTENT it
    displays stays Bangla and keeps `lang="bn"` so it is pronounced correctly.

WHY THIS FILE DERIVES LABELS INSTEAD OF HOLDING A DICTIONARY
    Every closed vocabulary in this project already names its members in English —
    `OutcomeType.FURTHER_STUDY = "further_study"`, `SectionType.FAQ_LIST = "faq_list"`.
    The `_LABELS` maps in `constants.py` exist to turn those into Bangla for the
    public site. Their English counterpart is the value itself, so a second
    hand-written dictionary would be ~90 strings that duplicate the enums and drift
    the first time somebody adds a member.

    Two exceptions, both real:
      * Acronyms. `humanise("HSC")` is "Hsc". See `ACRONYMS`.
      * Section-type hints. Those are prose ("A page title, standfirst and one call
        to action"), not names, so they are written out — 13 of them, in one place.
"""

from __future__ import annotations

#: Words that are spelled in capitals, not title case. A short list, checked first,
#: because getting these wrong is the visible kind of wrong: "Faq list" and "Hsc".
ACRONYMS: dict[str, str] = {
    "HSC": "HSC",
    "SMS": "SMS",
    "FAQ": "FAQ",
    "FAQS": "FAQs",
    "CTA": "CTA",
    "AI": "AI",
    "URL": "URL",
    "ID": "ID",
    "CSV": "CSV",
    "TOTP": "TOTP",
}

#: Suffixes a stored field name may carry, and what they mean to the operator.
#: `heading_bn` holds Bangla text — in an English panel that is the one fact about
#: the field worth putting in its label, because the wrong choice is invisible until
#: it is published.
FIELD_SUFFIXES: dict[str, str] = {
    "bn": "Bangla",
    "en": "English",
}

#: Section types (§4.2). The label is the type's name; the hint is what the picker
#: says to help an editor choose. `SECTION_TYPE_LABELS` in `constants.py` holds the
#: Bangla pair for the public site; these are the admin's.
SECTION_TYPE_NAMES_EN: dict[str, str] = {
    "hero": "Hero",
    "rich_text": "Rich text",
    "stat_strip": "Statistic strip",
    "fact_list": "Fact list",
    "module_list": "Module list",
    "participant_grid": "Participant grid",
    "gallery_strip": "Gallery strip",
    "media_feature": "Media feature",
    "faq_list": "FAQ list",
    "quote": "Quote",
    "cta_band": "Call to action",
    "institution_card": "Institution card",
    "timeline": "Timeline",
}

SECTION_TYPE_HINTS_EN: dict[str, str] = {
    "hero": "Page title, standfirst and one action.",
    "rich_text": "A sanitised HTML body.",
    "stat_strip": "A row of defined statistics.",
    "fact_list": "Label and value pairs.",
    "module_list": "The course modules, in order.",
    "participant_grid": "Cards for consented participants.",
    "gallery_strip": "A grid of images or video links.",
    "media_feature": "An image beside text.",
    "faq_list": "Grouped questions and answers.",
    "quote": "One quotation. Needs the person's consent.",
    "cta_band": "An action at the end of a page.",
    "institution_card": "One institution's details.",
    "timeline": "Events in date order.",
}


def humanise(value: str) -> str:
    """`further_study` → "Further study", `HSC` → "HSC", `faq_list` → "FAQ list".

    Never raises and never returns an empty string for a non-empty input: a label
    that comes back blank turns a form field unlabelled, which is an accessibility
    defect, and the fallback is just the raw value.
    """
    if not value:
        return ""

    words = str(value).replace("-", "_").split("_")
    out: list[str] = []
    for word in words:
        if not word:
            continue
        upper = word.upper()
        if upper in ACRONYMS:
            out.append(ACRONYMS[upper])
        elif word.isupper() and len(word) <= 4:
            # A stored value like "HSC" or "OK" that the acronym list has not met yet.
            out.append(word)
        else:
            out.append(word[0].upper() + word[1:])
    return " ".join(out) or str(value)


def field_label(name: str) -> str:
    """A stored field name → the label on the form.

    `heading_bn` becomes "Heading (Bangla)". The parenthetical is not decoration: in
    an English panel it is the only thing that tells an operator that this box wants
    Bangla and the one above it wants English, and getting that wrong is a mistake
    nobody sees until the page is live.
    """
    if not name:
        return ""

    parts = str(name).split("_")
    suffix = parts[-1] if parts else ""
    if len(parts) > 1 and suffix in FIELD_SUFFIXES:
        stem = humanise("_".join(parts[:-1]))
        return f"{stem} ({FIELD_SUFFIXES[suffix]})"
    return humanise(name)


def section_name(section_type: str) -> str:
    """The English name of a section type, falling back to a humanised key."""
    return SECTION_TYPE_NAMES_EN.get(str(section_type)) or humanise(section_type)


def section_hint(section_type: str) -> str:
    return SECTION_TYPE_HINTS_EN.get(str(section_type), "")


def choice_label(rule: dict, name: str) -> str:
    """The label for one schema field.

    Prefers a hand-written English label, then derives one from the field name. A
    section that genuinely needs a better label than its key supplies can set
    `label_en` in its schema and this picks it up without touching the other twelve.
    """
    explicit = rule.get("label_en")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    return field_label(name)


def hint(rule: dict) -> str:
    """The English hint for one schema field. Empty when the schema supplies none."""
    for key in ("hint_en", "hint"):
        value = rule.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def enum_label(member: object) -> str:
    """An enum member → its English label, derived from the value."""
    value = getattr(member, "value", member)
    return humanise(str(value))


__all__ = [
    "ACRONYMS",
    "SECTION_TYPE_HINTS_EN",
    "SECTION_TYPE_NAMES_EN",
    "choice_label",
    "enum_label",
    "field_label",
    "hint",
    "humanise",
    "section_hint",
    "section_name",
]
