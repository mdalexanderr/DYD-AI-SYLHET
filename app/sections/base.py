"""SectionBase — the declaration every section type shares. plan.md §9.3, step 3.1.

    class HeroSection(SectionBase):
        type = "hero"
        template = "sections/hero.html"
        schema = {
            "heading_bn": {"type": "str", "required": True, "max": 160},
            "media_id":   {"type": "ref", "model": "MediaItem"},
        }
        def context(self, payload, request):
            return {"heading": payload["heading_bn"], "media": self.media(payload.get("media_id"))}

WHY ONE MODULE PER TYPE AND NOT A GENERIC BLOCK RENDERER
    §9.3: "Adding a section type is one file plus one template, and it cannot silently
    render garbage from a malformed payload." A generic renderer that walks a JSON blob
    has to guess at every field, cannot validate, and lets the admin produce layout
    that breaks the design system. Here, validation, defaults, media resolution and
    (from Phase 4) the per-type admin form all fall out of the same declaration.

WHY `validate()` RETURNS A BANGLA REASON INSTEAD OF RAISING
    Bad DATA is an editor typing something wrong, and they need to be told which field
    and why — in the language they are working in. Bad CODE (an unknown section type)
    raises `SectionError`, because that is not something an editor can fix. Mixing the
    two turns an editor's typo into a 500 (§9.3 rules 1 and 2).

WHY THE REASON NAMES THE FIELD
    Step 3.1's "Done when": "a malformed payload raises with the field name and the
    reason — not a generic error." §11.2's publish gate depends on this: it shows the
    editor exactly which section and which field is stopping publication.
"""

from __future__ import annotations

import re
from typing import Any

from app.constants import SECTION_TYPE_HINTS, SECTION_TYPE_LABELS, SectionType

#: Anchored schemes that must never reach an href. A CMS field is stored XSS waiting
#: for a click otherwise, and it is a government domain.
_UNSAFE_HREF = re.compile(r"^\s*(javascript|data|vbscript)\s*:", re.IGNORECASE)

#: Origins a CTA is allowed to point at. An external CTA turns a public page into an
#: open redirect; a genuine external link belongs in rich text, where it is visibly a
#: link rather than a button.
_ALLOWED_CTA_ORIGINS = (
    "https://sylhet.dydaiproject.com",
    "https://www.dydaiproject.com",
)

EM_DASH = "—"


class SectionError(ValueError):
    """Unknown section type, or a schema that cannot be interpreted.

    Raised for PROGRAMMING errors only. A payload that fails validation returns
    (False, reason) instead — see the module docstring.
    """

    def __init__(self, section_type: str, reason: str) -> None:
        self.section_type = section_type
        self.reason = reason
        super().__init__(f"{section_type}: {reason}")


# ─────────────────────────────────────────────────────────────────────────────
# Field checking
# ─────────────────────────────────────────────────────────────────────────────
def _label(name: str, spec: dict[str, Any]) -> str:
    """The name an editor sees. Falls back to the key so it is never empty."""
    return spec.get("label_bn") or name


def validate_href(href: Any, label: str = "লিংক") -> tuple[bool, str]:
    """May this href be rendered? Shared by `cta` fields and by `cta_band`.

    `cta_band` stores its href flat rather than as a `cta` mapping, so the same rule
    has to serve two shapes. Two implementations of it would be a bug waiting for
    whichever shape was added second — and the rule is a security one: a CMS-supplied
    href is stored XSS waiting for a click, and an open redirect on a government
    domain.

    Relative paths, `mailto:` and `tel:` are allowed. Absolute URLs are allowed only
    to this site's own HTTPS origins, so an http:// link to ourselves is rejected too.
    """
    text = str(href or "").strip()
    if not text:
        return False, f"“{label}” এর লিংক আবশ্যক।"
    if _UNSAFE_HREF.match(text):
        return False, f"“{label}” এর লিংক নিরাপদ নয়।"
    if text.startswith(("http://", "https://")) and not text.startswith(
        _ALLOWED_CTA_ORIGINS
    ):
        return False, f"“{label}” এর বাইরের লিংক অনুমোদিত নয়।"
    return True, ""


def _check_scalar(kind: str, spec: dict[str, Any], value: Any, label: str) -> tuple[bool, str]:
    if kind in ("str", "text"):
        if not isinstance(value, str):
            return False, f"“{label}” লেখা হতে হবে।"
        limit = spec.get("max")
        if limit and kind == "str" and len(value) > limit:
            return False, f"“{label}” সর্বোচ্চ {limit} অক্ষরের হতে পারে।"
        return True, ""

    if kind == "int":
        # bool is an int subclass in Python, so it must be excluded explicitly or
        # `True` would sail through as 1.
        if isinstance(value, bool) or not isinstance(value, int):
            return False, f"“{label}” সংখ্যা হতে হবে।"
        low, high = spec.get("min"), spec.get("max")
        if low is not None and value < low:
            return False, f"“{label}” কমপক্ষে {low} হতে হবে।"
        if high is not None and value > high:
            return False, f"“{label}” সর্বোচ্চ {high} হতে পারে।"
        return True, ""

    if kind == "bool":
        if not isinstance(value, bool):
            return False, f"“{label}” সত্য/মিথ্যা হতে হবে।"
        return True, ""

    if kind == "enum":
        choices = tuple(spec.get("choices") or ())
        if value not in choices:
            return False, f"“{label}” এর মান সঠিক নয় (হতে পারে: {', '.join(choices)})।"
        return True, ""

    if kind == "cta":
        if not isinstance(value, dict):
            return False, f"“{label}” এ লেখা ও লিংক দুটোই থাকতে হবে।"
        if not str(value.get("label") or "").strip():
            return False, f"“{label}” এর লেখা আবশ্যক।"
        return validate_href(value.get("href"), label)

    if kind == "ref":
        if isinstance(value, bool) or not isinstance(value, int):
            return False, f"“{label}” এর রেফারেন্স সঠিক নয়।"
        return True, ""

    if kind == "pair":
        if not isinstance(value, dict):
            return False, f"“{label}” এ লেবেল ও মান থাকতে হবে।"
        missing = [key for key in ("label_bn", "value_bn") if not value.get(key)]
        if missing:
            return False, f"“{label}” এ {', '.join(missing)} আবশ্যক।"
        return True, ""

    if kind == "timeline_item":
        if not isinstance(value, dict):
            return False, f"“{label}” এ তথ্য থাকতে হবে।"
        missing = [key for key in ("date_bn", "title_bn") if not value.get(key)]
        if missing:
            return False, f"“{label}” এ {', '.join(missing)} আবশ্যক।"
        return True, ""

    return False, f"“{label}” এর ধরন অজানা ({kind})।"


def _check_field(spec: dict[str, Any], payload: dict[str, Any], name: str) -> tuple[bool, str]:
    """Validate one field. Returns (ok, bangla_reason)."""
    label = _label(name, spec)
    kind = spec.get("type", "")
    required = bool(spec.get("required", False))
    present = name in payload and payload[name] not in (None, "", [])

    if not present:
        if required:
            return False, f"“{label}” আবশ্যক।"
        return True, ""

    value = payload[name]

    if kind in ("list", "list_ref"):
        if not isinstance(value, list):
            return False, f"“{label}” একটি তালিকা হতে হবে।"
        low, high = spec.get("min_items"), spec.get("max_items")
        if low is not None and len(value) < low:
            return False, f"“{label}” এ কমপক্ষে {low}টি থাকতে হবে।"
        if high is not None and len(value) > high:
            return False, f"“{label}” এ সর্বোচ্চ {high}টি থাকতে পারে।"
        item_spec = spec.get("item")
        if item_spec:
            for index, item in enumerate(value, start=1):
                ok, reason = _check_scalar(
                    item_spec.get("type", ""), item_spec, item, f"{label} #{index}"
                )
                if not ok:
                    return False, reason
        return True, ""

    return _check_scalar(kind, spec, value, label)


# ─────────────────────────────────────────────────────────────────────────────
class SectionBase:
    """One section type: its schema, its validation, and its template context."""

    #: The value stored in `page_sections.type`. Must match a `SectionType` member.
    type: str = ""

    #: Template path under `app/templates/`.
    template: str = ""

    #: field_name -> spec. See `_check_scalar` for the keys each type accepts.
    schema: dict[str, dict[str, Any]] = {}

    #: Bangla name and one-line hint, for the admin picker (§11.2). Defaulted from
    #: `constants` by `__init_subclass__` so a new type cannot forget them.
    label_bn: str = ""
    hint_bn: str = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Fill in the label and hint from `constants`, and refuse a nameless type.

        Doing this at class-creation time means `section_choices()` cannot go blank
        for a type somebody adds later, and a subclass that forgets `type` fails at
        import rather than at render.
        """
        super().__init_subclass__(**kwargs)
        if not cls.type:
            raise SectionError(cls.__name__, "a section class must declare `type`")
        try:
            enum_member = SectionType(cls.type)
        except ValueError as exc:
            raise SectionError(
                cls.type, "not a member of SectionType — add it to app/constants.py"
            ) from exc
        cls.label_bn = cls.label_bn or SECTION_TYPE_LABELS.get(enum_member, "")
        cls.hint_bn = cls.hint_bn or SECTION_TYPE_HINTS.get(enum_member, "")
        if not cls.template:
            cls.template = f"sections/{cls.type}.html"

    # ── Validation ──────────────────────────────────────────────────────────
    def validate(self, payload: Any) -> tuple[bool, str]:
        """(ok, bangla_reason). Never raises for bad DATA — see the docstring."""
        if not isinstance(payload, dict):
            return False, "সেকশনের তথ্য সঠিক বিন্যাসে নেই।"

        for name, spec in self.schema.items():
            if not isinstance(spec, dict):
                raise SectionError(self.type, f"schema for {name!r} is not a dict")
            ok, reason = _check_field(spec, payload, name)
            if not ok:
                return False, reason

        return self._validate_extra(payload)

    def _validate_extra(self, payload: dict[str, Any]) -> tuple[bool, str]:
        """Cross-field rules. Overridden where a type needs them."""
        return True, ""

    # ── Context ─────────────────────────────────────────────────────────────
    def context(self, payload: dict[str, Any], request: Any = None) -> dict[str, Any]:
        """What the template needs. Overridden by every real type."""
        return dict(payload)

    # ── Resolvers ───────────────────────────────────────────────────────────
    # Sections run at render time inside a request, so reading the database here is
    # expected. Each resolver returns an empty value rather than raising when the row
    # is gone: a deleted media item should leave a gap in a page, not 500 the site.
    def media(self, media_id: Any) -> dict[str, Any] | None:
        """A media item in the shape `media_figure` expects (§10.5)."""
        if not isinstance(media_id, int) or isinstance(media_id, bool):
            return None
        from app.models import MediaItem

        item = _get(MediaItem, media_id)
        return item.to_view() if item is not None else None

    def media_list(self, media_ids: Any) -> list[dict[str, Any]]:
        if not isinstance(media_ids, list):
            return []
        out = []
        for media_id in media_ids:
            view = self.media(media_id)
            if view is not None:
                out.append(view)
        return out

    def course(self, course_id: Any):
        from app.models import Course

        return _get(Course, course_id)

    def institution(self, institution_id: Any):
        from app.models import Institution

        return _get(Institution, institution_id)

    def faqs(self, faq_ids: Any = None, category: str | None = None) -> list[Any]:
        """Active FAQs, by explicit id list or by category, always in display order."""
        from sqlalchemy import select

        from app.extensions import db
        from app.models import Faq

        stmt = select(Faq).where(Faq.is_active.is_(True))
        if isinstance(faq_ids, list) and faq_ids:
            stmt = stmt.where(Faq.id.in_([i for i in faq_ids if isinstance(i, int)]))
        elif category:
            stmt = stmt.where(Faq.category == category)
        stmt = stmt.order_by(Faq.sort_order, Faq.id)
        return list(db.session.execute(stmt).scalars())

    def stats(self, stat_keys: Any) -> list[dict[str, Any]]:
        """Stats in the order the section asks for, via the stats service.

        Goes through the service rather than the model because §5.4's `<5`
        suppression and the "computed" source both live there — a section must not be
        able to show a raw figure the service would have suppressed.
        """
        from app.services import stats_service

        return stats_service.strip_for_keys(stat_keys)

    def participants(
        self,
        *,
        limit: int | None = None,
        sort: str = "manual",
        outcome: str | None = None,
        query: str | None = None,
    ) -> list[Any]:
        """Published participants. Always through the service, never a bare query.

        The service applies the consent filter. A section that queried the model
        directly would be a second place the publication rules are expressed, and the
        first one to drift.
        """
        from app.services import participant_service

        return participant_service.list_published(
            limit=limit, sort=sort, outcome=outcome, query=query
        )


def _get(model: type, pk: Any):
    """Fetch by primary key, tolerating a junk value.

    `db.session.get` raises on a non-integer key with some drivers, and a seed file
    with `"media_id": "3"` should not be able to 500 a page.
    """
    if not isinstance(pk, int) or isinstance(pk, bool):
        return None
    from app.extensions import db

    return db.session.get(model, pk)
