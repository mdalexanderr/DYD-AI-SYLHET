"""Section schemas and validation — the declarative half of §9.3.

    validate_section("hero", {...})  ->  (ok: bool, reason_bn: str)

WHY THE SCHEMAS LIVE HERE RATHER THAN WITH THE RENDERERS
    Phase 2 seeds 8 pages with their sections, so the payload shape has to exist
    before anything renders one. Putting the declaration in its own module means
    the renderers added in Phase 3 consume it instead of defining it — there is
    one definition of what a `stat_strip` contains, and it is this one.

WHY A DECLARATIVE SCHEMA AND NOT A FREE-FORM BLOCK BUILDER
    §4.2: a generic block builder cannot be validated and lets the admin produce
    layout that breaks the design system. A declared schema per type means the
    publish gate can name the exact field that is wrong (§11.2), and an unknown
    type raises instead of rendering garbage (§9.3 rule 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.constants import SECTION_TYPE_HINTS, SECTION_TYPE_LABELS, SectionType


class SectionError(ValueError):
    """Unknown section type, or a schema that cannot be interpreted."""

    def __init__(self, section_type: str, reason: str) -> None:
        self.section_type = section_type
        self.reason = reason
        super().__init__(f"{section_type}: {reason}")


@dataclass(frozen=True)
class Field:
    """One field in a section payload.

    Deliberately small. Every type below is something a section genuinely needs;
    anything more expressive would be a block builder with extra steps.
    """

    kind: str  # str | text | int | bool | enum | cta | ref | list | list_ref
    required: bool = False
    max_len: int | None = None
    choices: tuple[str, ...] = ()
    min_value: int | None = None
    max_value: int | None = None
    label_bn: str = ""
    item: Field | None = None  # for list / list_ref


def _s(max_len: int, required: bool = False, label: str = "") -> Field:
    return Field("str", required=required, max_len=max_len, label_bn=label)


def _text(required: bool = False, label: str = "") -> Field:
    return Field("text", required=required, label_bn=label)


def _int(required: bool = False, lo: int | None = None, hi: int | None = None,
         label: str = "") -> Field:
    return Field("int", required=required, min_value=lo, max_value=hi, label_bn=label)


def _cta(required: bool = False, label: str = "বাটন") -> Field:
    """A call to action. A `cta` field is a mapping with a Bangla label and an href."""
    return Field("cta", required=required, label_bn=label)


def _ref(model: str, required: bool = False, label: str = "") -> Field:
    """A foreign key to another record. `choices` carries the model name."""
    return Field("ref", required=required, choices=(model,), label_bn=label)


LAYOUT_CHOICES = ("left", "right", "full")
SORT_CHOICES = ("name", "recent", "manual")

def _outcomes() -> tuple[Any, ...]:
    """OutcomeType members, imported lazily to avoid a cycle with app.constants.

    This MUST be defined above SECTION_SCHEMAS. SECTION_SCHEMAS is a plain
    module-level dict literal, so its values are evaluated while the module is
    being read; a helper defined further down the same file does not exist yet,
    and the resulting NameError happens at IMPORT time — meaning the application
    cannot start at all, and the traceback points at a line that looks fine.
    """
    from app.constants import OutcomeType

    return tuple(OutcomeType)

# ── The 13 types (§4.2) ──────────────────────────────────────────────────────
SECTION_SCHEMAS: dict[str, dict[str, Field]] = {
    SectionType.HERO: {
        "heading_bn": _s(160, required=True, label="শিরোনাম"),
        "subheading_bn": _s(320, label="উপশিরোনাম"),
        # §4.2 calls this `background_media_id`; the §9.3 example calls it
        # `media_id`. One name is used here — the code example's — and the
        # discrepancy is recorded in plan.md's open items rather than honoured
        # twice, because two keys for one value is two keys that will diverge.
        "media_id": _ref("MediaItem", label="ছবি"),
        "primary_cta": _cta(label="প্রধান বাটন"),
        "secondary_cta": _cta(label="দ্বিতীয় বাটন"),
    },
    SectionType.RICH_TEXT: {
        "heading_bn": _s(200, label="শিরোনাম"),
        "body_bn": _text(required=True, label="বিষয়বস্তু"),
    },
    SectionType.STAT_STRIP: {
        "heading_bn": _s(200, label="শিরোনাম"),
        "stat_keys": Field("list", required=True, label_bn="পরিসংখ্যান",
                           item=_s(64, required=True)),
    },
    SectionType.FACT_LIST: {
        "heading_bn": _s(200, label="শিরোনাম"),
        "items": Field("list", required=True, label_bn="তথ্য",
                       item=Field("pair", required=True, label_bn="লেবেল ও মান")),
    },
    SectionType.MODULE_LIST: {
        "heading_bn": _s(200, label="শিরোনাম"),
        "course_id": _ref("Course", required=True, label="কোর্স"),
    },
    SectionType.PARTICIPANT_GRID: {
        "heading_bn": _s(200, label="শিরোনাম"),
        "limit": _int(lo=1, hi=48, label="সর্বোচ্চ সংখ্যা"),
        "sort": Field("enum", choices=SORT_CHOICES, label_bn="সাজানোর নিয়ম"),
        "outcome": Field("enum", choices=tuple(o.value for o in _outcomes()),
                         label_bn="ফলাফল ফিল্টার"),
    },
    SectionType.GALLERY_STRIP: {
        "heading_bn": _s(200, label="শিরোনাম"),
        "media_ids": Field("list_ref", required=True, label_bn="মিডিয়া",
                           item=_ref("MediaItem", required=True)),
        "columns": _int(lo=1, hi=4, label="কলাম সংখ্যা"),
    },
    SectionType.MEDIA_FEATURE: {
        "heading_bn": _s(200, label="শিরোনাম"),
        "body_bn": _text(label="বিষয়বস্তু"),
        "media_id": _ref("MediaItem", required=True, label="মিডিয়া"),
        "layout": Field("enum", choices=LAYOUT_CHOICES, label_bn="বিন্যাস"),
    },
    SectionType.FAQ_LIST: {
        "heading_bn": _s(200, label="শিরোনাম"),
        "faq_ids": Field("list", label_bn="নির্দিষ্ট প্রশ্ন",
                         item=_int(required=True)),
        "category": _s(64, label="শ্রেণি"),
    },
    SectionType.QUOTE: {
        # Required, because a quote section with no quote renders an empty block.
        # Whether the quote is PERMITTED is a participant-level rule (§5.3 rule 5),
        # not a section-level one.
        "quote_bn": _text(required=True, label="উদ্ধৃতি"),
        "attribution_bn": _s(160, label="উৎস"),
    },
    SectionType.CTA_BAND: {
        "heading_bn": _s(200, required=True, label="শিরোনাম"),
        "body_bn": _text(label="বিষয়বস্তু"),
        "cta_label": _s(80, label="বাটনের লেখা"),
        "cta_href": _s(300, label="বাটনের লিংক"),
    },
    SectionType.INSTITUTION_CARD: {
        "heading_bn": _s(200, label="শিরোনাম"),
        "institution_id": _ref("Institution", required=True, label="প্রতিষ্ঠান"),
    },
    SectionType.TIMELINE: {
        "heading_bn": _s(200, label="শিরোনাম"),
        "items": Field("list", required=True, label_bn="ঘটনাপ্রবাহ",
                       item=Field("timeline_item", required=True, label_bn="ঘটনা")),
    },
}


def get_schema(section_type: str) -> dict[str, Field]:
    """The schema for a type, or raise.

    §9.3 rule 1: an unknown type RAISES and is reported in the admin, rather than
    being skipped. A silently skipped section is a page that is quietly missing
    something, which is exactly the failure the admin would not notice.
    """
    try:
        return SECTION_SCHEMAS[section_type]
    except KeyError as exc:
        raise SectionError(section_type, "unknown section type") from exc


def validate_section(section_type: str, payload: Any) -> tuple[bool, str]:
    """Validate a payload. Returns (ok, reason). Never raises for bad DATA.

    A missing or unknown type RAISES, because that is a programming error. A
    payload that fails validation returns False with a Bangla reason, because that
    is an editor typing something wrong and they need to be told which field.

    ``payload`` is typed ``Any``, not ``dict``, on purpose: this function validates
    UNTRUSTED input — the admin form posts, and the seed JSON, both of which can
    contain anything. Annotating it ``dict`` would make the isinstance guard below
    unreachable to a type checker, which is the reverse of the truth: the guard is
    the only thing standing between a malformed payload and a 500.
    """
    schema = get_schema(section_type)

    if not isinstance(payload, dict):
        return False, "সেকশনের তথ্য সঠিক বিন্যাসে নেই।"

    for name, spec in schema.items():
        if name not in payload or payload[name] in (None, "", []):
            if spec.required:
                return False, f"“{spec.label_bn or name}” আবশ্যক।"
            continue
        ok, reason = _check(spec, payload[name], spec.label_bn or name)
        if not ok:
            return False, reason

    return True, ""


def _check(spec: Field, value: Any, label: str) -> tuple[bool, str]:
    if spec.kind in ("str", "text"):
        if not isinstance(value, str):
            return False, f"“{label}” লেখা হতে হবে।"
        if spec.max_len and len(value) > spec.max_len:
            return False, f"“{label}” সর্বোচ্চ {spec.max_len} অক্ষরের হতে পারে।"
        return True, ""

    if spec.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return False, f"“{label}” সংখ্যা হতে হবে।"
        if spec.min_value is not None and value < spec.min_value:
            return False, f"“{label}” কমপক্ষে {spec.min_value} হতে হবে।"
        if spec.max_value is not None and value > spec.max_value:
            return False, f"“{label}” সর্বোচ্চ {spec.max_value} হতে পারে।"
        return True, ""

    if spec.kind == "bool":
        return (isinstance(value, bool), f"“{label}” সত্য/মিথ্যা হতে হবে।")

    if spec.kind == "enum":
        if value not in spec.choices:
            return False, f"“{label}” এর মান সঠিক নয় (হতে পারে: {', '.join(spec.choices)})।"
        return True, ""

    if spec.kind == "cta":
        if not isinstance(value, dict):
            return False, f"“{label}” এ লেবেল ও লিংক থাকতে হবে।"
        if not value.get("label"):
            return False, f"“{label}” এর লেখা আবশ্যক।"
        href = str(value.get("href") or "")
        if not href:
            return False, f"“{label}” এর লিংক আবশ্যক।"
        # No javascript: URLs, and no absolute URLs to an unknown origin — a CTA
        # in the CMS is otherwise a way to inject a redirect onto a government page.
        if href.lower().startswith(("javascript:", "data:")):
            return False, f"“{label}” এর লিংক নিরাপদ নয়।"
        if href.startswith("http") and not href.startswith(
            ("https://sylhet.dydaiproject.com", "https://www.dydaiproject.com")
        ):
            return False, f"“{label}” এর বাইরের লিংক অনুমোদিত নয়।"
        return True, ""

    if spec.kind == "ref":
        if not isinstance(value, int) or isinstance(value, bool):
            return False, f"“{label}” এর রেফারেন্স সঠিক নয়।"
        return True, ""

    if spec.kind in ("list", "list_ref"):
        if not isinstance(value, list):
            return False, f"“{label}” একটি তালিকা হতে হবে।"
        if spec.item:
            for index, item in enumerate(value, 1):
                ok, reason = _check(spec.item, item, f"{label} #{index}")
                if not ok:
                    return False, reason
        return True, ""

    if spec.kind == "pair":
        if not isinstance(value, dict):
            return False, f"“{label}” এ লেবেল ও মান থাকতে হবে।"
        missing = [k for k in ("label_bn", "value_bn") if not value.get(k)]
        if missing:
            return False, f"“{label}” এ {', '.join(missing)} আবশ্যক।"
        return True, ""

    if spec.kind == "timeline_item":
        if not isinstance(value, dict):
            return False, f"“{label}” এ তথ্য থাকতে হবে।"
        missing = [k for k in ("date_bn", "title_bn") if not value.get(k)]
        if missing:
            return False, f"“{label}” এ {', '.join(missing)} আবশ্যক।"
        return True, ""

    return False, f"“{label}” এর ধরন অজানা ({spec.kind})।"


def section_choices() -> list[dict[str, str]]:
    """The 13 types with Bangla labels and one-line hints, for the picker (§11.2)."""
    return [
        {
            "value": section_type.value,
            "label": SECTION_TYPE_LABELS[section_type],
            "hint": SECTION_TYPE_HINTS[section_type],
        }
        for section_type in SectionType
    ]


#: Populated in Phase 3, one entry per type: type -> callable(payload, request) -> dict.
#: Kept here so the registry is the single place that knows which types exist.
RENDERERS: dict[str, Any] = {}

__all__ = [
    "RENDERERS",
    "SECTION_SCHEMAS",
    "Field",
    "SectionError",
    "get_schema",
    "section_choices",
    "validate_section",
]


# re-exported for the dataclass default machinery; kept out of the public surface
_ = field
