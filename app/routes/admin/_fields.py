"""Schema-driven admin forms. plan.md §11.2, §9.3.

WHY THIS IS GENERATED AND NOT WRITTEN OUT THIRTEEN TIMES
    §9.3 rule 5 says "adding a section type is one file plus one template". The
    section classes already carry that declaration — `schema` — and the registry
    already exposes it (`SECTION_SCHEMAS`), with a docstring that says Phase 4's form
    generator reads "the schema the validator actually used and the two cannot
    drift". This module is that generator: it turns a schema into form rows, and the
    submitted form back into a payload, so a field added to a section type appears
    in the admin without anybody remembering to add it.

WHY PARSING IS HERE AND NOT IN THE TEMPLATE
    A template can render inputs; it cannot decide that an empty `int` must be
    ABSENT rather than 0, or that `bool` is "was the checkbox in the form" rather
    than a value. Those decisions are the difference between a payload that validates
    and one that does not, and they belong in one place with a test.

WHAT VALIDATION IS NOT DONE HERE
    Nothing is checked twice. `section_payload()` produces the payload in the shape
    the schema describes; `registry.validate_section()` decides whether it is any good
    and hands back an English reason naming the field (§11.1 — a validation failure is
    only ever shown in the admin). A second set of rules here would be a second answer
    to "is this section publishable", and the publish gate would follow whichever it
    happened to call.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.routes.admin._labels import choice_label, field_label, hint as schema_hint

#: The child keys of the two structured list-item types. Anything else a `list`
#: holds is a scalar and gets one input per row.
#:
#: The labels are DERIVED from the child keys — `label_bn` becomes "Label (Bangla)" —
#: for the same reason the record forms derive theirs: a hand-written label beside a
#: key is a second copy that goes stale when the key is renamed.
STRUCTURED_ITEMS: dict[str, tuple[tuple[str, str], ...]] = {
    "pair": (("label_bn", ""), ("value_bn", "")),
    "timeline_item": (
        ("date_bn", ""),
        ("title_bn", ""),
        ("body_bn", ""),
    ),
}

#: How many blank rows the editor offers after the last filled one. One is enough to
#: add, and asking for more would make every section form taller than the screen.
SPARE_ROWS = 1

#: A list never renders more blank rows than this, however large `max_items` is.
MAX_RENDERED_ROWS = 30


def _ref_choices(model_name: str) -> list[dict[str, Any]]:
    """Pickable rows for a `ref` field, as (id, label) dicts.

    Read live rather than cached: an editor who uploads an image and then opens a
    hero section must see it, and the admin is a low-traffic screen where a query is
    cheaper than a stale dropdown.
    """
    from app.extensions import db
    from app import models

    model = getattr(models, model_name, None)
    if model is None:  # a schema naming a model that does not exist
        return []

    label_column = {
        "MediaItem": "alt_bn",
        "Course": "title_bn",
        "Institution": "name_bn",
        "Faq": "question_bn",
        "Participant": "name_bn",
        "Stat": "label_bn",
    }.get(model_name, "id")

    stmt = db.select(model)
    if hasattr(model, "is_active"):
        stmt = stmt.where(model.is_active.is_(True))
    if model_name == "MediaItem":
        stmt = stmt.order_by(model.id.desc())
    elif hasattr(model, "sort_order"):
        stmt = stmt.order_by(model.sort_order, model.id)

    out = []
    for row in db.session.execute(stmt.limit(300)).scalars():
        label = getattr(row, label_column, None) or f"#{row.id}"
        if model_name == "MediaItem":
            label = f"#{row.id} · {label[:60]}"
        out.append({"value": row.id, "label": str(label)})
    return out


def describe(schema: Mapping[str, Mapping[str, Any]], payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Form rows for a section, filled from `payload`.

    One dict per row, with a `kind` the template switches on. The kinds are the form
    controls, not the schema types: `ref` becomes a select, `list` of `pair` becomes
    repeated two-column rows, and so on.
    """
    rows: list[dict[str, Any]] = []

    for name, spec in schema.items():
        kind = spec.get("type", "str")
        row: dict[str, Any] = {
            "name": name,
            "label": choice_label(spec, name),
            "required": bool(spec.get("required")),
            "hint": schema_hint(spec),
            "value": payload.get(name),
        }

        if kind == "text":
            row["kind"] = "textarea"
            row["value"] = row["value"] or ""

        elif kind == "bool":
            row["kind"] = "checkbox"
            row["value"] = bool(row["value"])

        elif kind == "int":
            row["kind"] = "number"
            row["min"] = spec.get("min")
            row["max"] = spec.get("max")
            row["value"] = "" if row["value"] is None else row["value"]

        elif kind == "enum":
            row["kind"] = "select"
            row["options"] = [
                {"value": choice, "label": choice} for choice in spec.get("choices", ())
            ]
            row["value"] = row["value"] or ""

        elif kind == "ref":
            row["kind"] = "select"
            row["options"] = _ref_choices(spec.get("model", ""))
            row["value"] = row["value"] or ""

        elif kind == "cta":
            row["kind"] = "cta"
            cta = row["value"] if isinstance(row["value"], dict) else {}
            row["label_value"] = cta.get("label", "")
            row["href_value"] = cta.get("href", "")

        elif kind in ("list", "list_ref"):
            item = spec.get("item") or {}
            item_type = item.get("type", "str")
            values = row["value"] if isinstance(row["value"], list) else []

            if item_type in STRUCTURED_ITEMS:
                row["kind"] = "list_structured"
                row["columns"] = [
                    {"key": key, "label": label or field_label(key)}
                    for key, label in STRUCTURED_ITEMS[item_type]
                ]
                row["rows"] = [
                    {
                        "index": index,
                        "cells": [
                            {
                                "key": key,
                                "label": label or field_label(key),
                                "value": (item_value or {}).get(key, "")
                                if isinstance(item_value, dict)
                                else "",
                            }
                            for key, label in STRUCTURED_ITEMS[item_type]
                        ],
                    }
                    for index, item_value in enumerate(values)
                ]
                row["rows"] += [
                    {
                        "index": len(values) + spare,
                        "cells": [
                            {"key": key, "label": label or field_label(key), "value": ""}
                            for key, label in STRUCTURED_ITEMS[item_type]
                        ],
                    }
                    for spare in range(SPARE_ROWS)
                ]
            elif item_type == "ref":
                row["kind"] = "list_ref"
                options = _ref_choices(item.get("model", "") or spec.get("model", ""))
                row["options"] = options
                row["rows"] = [
                    {"index": index, "value": value} for index, value in enumerate(values)
                ]
                row["rows"] += [
                    {"index": len(values) + spare, "value": ""}
                    for spare in range(SPARE_ROWS)
                ]
            else:
                row["kind"] = "list_scalar"
                row["scalar_kind"] = "number" if item_type == "int" else "text"
                row["rows"] = [
                    {"index": index, "value": value} for index, value in enumerate(values)
                ]
                row["rows"] += [
                    {"index": len(values) + spare, "value": ""}
                    for spare in range(SPARE_ROWS)
                ]
        else:
            row["kind"] = "text"
            row["value"] = row["value"] or ""

        rows.append(row)

    return rows


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _as_int(value: Any) -> int | None:
    """An int, or None. Blank is ABSENT, not zero — `min: 1` fields would otherwise
    fail validation on an empty box the editor never filled in."""
    text = _clean(value)
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _collect_rows(form: Mapping[str, Any], name: str) -> dict[int, dict[str, str]]:
    """Group `name.3.label_bn` style keys by their row index."""
    prefix = f"{name}."
    rows: dict[int, dict[str, str]] = {}
    for key in form.keys():
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        index_text, _, child = rest.partition(".")
        if not child:
            continue
        index = _as_int(index_text)
        if index is None:
            continue
        rows.setdefault(index, {})[child] = _clean(form.get(key))
    return rows


def _scalar_rows(form: Mapping[str, Any], name: str) -> list[str]:
    """Group `name.3` style keys (a list of plain values) by index, in order."""
    prefix = f"{name}."
    rows: list[tuple[int, str]] = []
    for key in form.keys():
        if not key.startswith(prefix):
            continue
        index = _as_int(key[len(prefix):])
        if index is None:
            continue
        rows.append((index, _clean(form.get(key))))
    return [value for _, value in sorted(rows)]


def section_payload(section_type: str, form: Mapping[str, Any]) -> dict[str, Any]:
    """The submitted form as a section payload.

    Values the editor left blank are OMITTED for optional fields rather than sent as
    empty strings or zeroes. `validate_section` treats absent and empty alike, but a
    payload with `"limit": 0` is a different thing from one that never mentioned a
    limit — and the first would fail a `min: 1` check the editor never intended to
    trigger.
    """
    from app.sections.registry import get_schema

    schema = get_schema(section_type)
    payload: dict[str, Any] = {}

    for name, spec in schema.items():
        kind = spec.get("type", "str")
        required = bool(spec.get("required"))

        if kind == "bool":
            # A checkbox that is not in the form is unchecked. That is not the same
            # as "absent": `narrow: false` is a decision the editor made.
            payload[name] = name in form

        elif kind == "int":
            value = _as_int(form.get(name))
            if value is not None:
                payload[name] = value

        elif kind == "cta":
            label = _clean(form.get(f"{name}__label"))
            href = _clean(form.get(f"{name}__href"))
            if label or href:
                payload[name] = {"label": label, "href": href}

        elif kind in ("list", "list_ref"):
            item = spec.get("item") or {}
            item_type = item.get("type", "str")
            built: list[Any] = []

            if item_type in STRUCTURED_ITEMS:
                child_keys = STRUCTURED_ITEMS[item_type]
                for index, cells in sorted(_collect_rows(form, name).items()):
                    if not any(_clean(cells.get(key)) for key, _ in child_keys):
                        continue  # a spacer row nobody filled in
                    built.append({key: _clean(cells.get(key)) for key, _ in child_keys})
            elif item_type == "ref":
                for value in _scalar_rows(form, name):
                    parsed = _as_int(value)
                    if parsed is not None:
                        built.append(parsed)
            elif item_type == "int":
                for value in _scalar_rows(form, name):
                    parsed = _as_int(value)
                    if parsed is not None:
                        built.append(parsed)
            else:
                built = [value for value in _scalar_rows(form, name) if value]

            if built or required:
                payload[name] = built

        else:
            value = _clean(form.get(name))
            if value or required:
                payload[name] = value

    return payload


__all__ = ["MAX_RENDERED_ROWS", "SPARE_ROWS", "describe", "section_payload"]
