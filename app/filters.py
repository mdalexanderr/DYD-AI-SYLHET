"""Jinja filters and URL helpers. plan.md §9.2, §14.1, §14.3, §8.1 rule 3.

SHARED WITH THE DESIGN HARNESS
    ``static_url`` and ``asset_url`` are injected as Jinja *globals* rather than
    filters so that ``tools/render-design.py`` can supply its own implementations
    and render the real component macros without a Flask app. That is the contract
    described in ``app/templates/components/base.html``: if a third global is ever
    needed, both places must learn it — and the harness will fail first, which is
    the point.

NUMBERS ARE FORMATTED AT RENDER, NEVER STORED FORMATTED (§14.1)
    ``bn_num`` is a display concern. Nothing in the database holds a Bangla
    numeral, so a copy change or a locale change never needs a migration.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from flask import current_app, url_for

from app.constants import (
    CONSENT_SOURCE_LABELS,
    EDUCATION_LABELS,
    MESSAGE_STATUS_LABELS,
    OUTCOME_LABELS,
    SECTION_TYPE_LABELS,
)

_BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

BN_MONTHS = (
    "জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন",
    "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর",
)

#: Shown wherever a suppressed or absent value would otherwise be blank. §5.4
#: renders a suppressed statistic as this, and an empty table cell uses the same
#: character so a reader cannot tell a missing value from a hidden one — which is
#: the correct behaviour for a small-cell suppression.
EM_DASH = "—"


def bn_num(value: Any) -> str:
    """ASCII digits to Bangla digits. ``124`` -> ``১২৪``.

    Leaves everything that is not a digit alone, so ``"১০টি"`` and ``1.5`` both
    behave sensibly and a caller does not have to know which case they have.
    """
    if value is None:
        return ""
    return str(value).translate(_BN_DIGITS)


def bn_num_or_dash(value: Any, suppress_below: int | None = None,
                   count: int | None = None) -> str:
    """Bangla numerals, or an em dash when the value must not be shown.

    ``suppress_below``/``count`` implement §5.4 in ONE place. The service layer is
    still responsible for not producing a small-cell figure at all; this is the
    final backstop, not the mechanism.
    """
    if value is None or value == "":
        return EM_DASH
    if suppress_below is not None and count is not None and count < suppress_below:
        return EM_DASH
    return bn_num(value)


def bn_date(value: date | datetime | None, style: str = "long") -> str:
    """A date in Bangla. ``long`` prose, ``short`` tables (§14.3).

        bn_date(date(2026, 9, 23))                    -> ২৩ সেপ্টেম্বর ২০২৬
        bn_date(date(2026, 9, 23), style="short")     -> ২৩/০৯/২০২৬
    """
    if value is None:
        return EM_DASH
    if isinstance(value, datetime):
        value = value.date()
    if style == "short":
        return bn_num(f"{value.day:02d}/{value.month:02d}/{value.year}")
    return f"{bn_num(value.day)} {BN_MONTHS[value.month - 1]} {bn_num(value.year)}"


def bn_time(value: datetime | None) -> str:
    """Bangla day-part prefix plus the time (§14.3: সকাল / দুপুর / বিকাল)."""
    if value is None:
        return EM_DASH
    hour = value.hour
    if hour < 5:
        part = "রাত"
    elif hour < 12:
        part = "সকাল"
    elif hour < 16:
        part = "দুপুর"
    elif hour < 19:
        part = "বিকাল"
    else:
        part = "রাত"
    h12 = hour % 12 or 12
    return f"{part} {bn_num(h12)}:{bn_num(value.minute):0>2}"


def bn_currency(value: Any) -> str:
    """Taka with Bangla numerals, e.g. ``৳২০০``."""
    if value in (None, ""):
        return EM_DASH
    return f"৳{bn_num(value)}"


def mask_none(value: Any, placeholder: str = EM_DASH) -> str:
    """Never render an empty string where a value was expected.

    A blank cell in a government table reads as "zero", not as "unknown".
    """
    if value is None or value == "" or (isinstance(value, str) and not value.strip()):
        return placeholder
    return str(value)


def bn_label(kind: str, value: Any) -> str:
    """Look up a Bangla label for a stored enum value.

    Templates call ``bn_label('education', p.education)`` rather than an
    if/elif chain, so adding an education level is one edit in constants.py.
    """
    maps = {
        "education": EDUCATION_LABELS,
        "outcome": OUTCOME_LABELS,
        "consent_source": CONSENT_SOURCE_LABELS,
        "message_status": MESSAGE_STATUS_LABELS,
        "section_type": SECTION_TYPE_LABELS,
    }
    table = maps.get(kind)
    if not table:
        return str(value or "")
    key = getattr(value, "value", value)
    return table.get(key, str(key or ""))


# ── URL helpers (§8.1 rule 3) ────────────────────────────────────────────────
_DIGEST_LENGTH = 8


@lru_cache(maxsize=256)
def _file_digest(path_str: str, mtime: float) -> str:
    """sha256[:8] of a static file.

    Keyed on mtime so a rebuild during ``flask run --debug`` produces a new
    version without restarting the process — a cache-buster that only changes on
    restart is a cache-buster that fails exactly when it is needed.
    """
    try:
        data = Path(path_str).read_bytes()
    except OSError:
        return "0"
    return hashlib.sha256(data).hexdigest()[:_DIGEST_LENGTH]


def static_url(filename: str) -> str:
    """An ordinary static URL. Use for anything that is not cache-sensitive."""
    try:
        return url_for("static", filename=filename)
    except RuntimeError:
        # No request context (a CLI or the seed path). A relative URL is
        # acceptable there and wrong nowhere.
        return f"/static/{filename}"


def asset_url(filename: str) -> str:
    """A static URL with ``?v=<sha256[:8]>`` so a rebuild busts the 1-year cache.

    The long ``Cache-Control: immutable`` on hashed assets is only safe because
    of this: without it, a CSS change would not reach a returning visitor for a
    year (§15.1).
    """
    path = Path(current_app.static_folder or "") / filename
    try:
        version = _file_digest(str(path), path.stat().st_mtime)
    except (OSError, RuntimeError):
        version = "0"
    return f"{static_url(filename)}?v={version}"


def clear_asset_cache() -> None:
    _file_digest.cache_clear()


# ── Registration ─────────────────────────────────────────────────────────────
FILTERS = {
    "bn_num": bn_num,
    "bn_date": bn_date,
    "bn_time": bn_time,
    "bn_currency": bn_currency,
    "mask_none": mask_none,
}

#: Filters that take an argument, registered separately for clarity in tests.
ARG_FILTERS = {
    "bn_num_or_dash": bn_num_or_dash,
    "bn_label": bn_label,
}


def register_filters(app) -> None:
    app.jinja_env.filters.update(FILTERS)
    app.jinja_env.filters.update(ARG_FILTERS)
    app.jinja_env.globals["static_url"] = static_url
    app.jinja_env.globals["asset_url"] = asset_url
    app.jinja_env.globals["EM_DASH"] = EM_DASH
    # `section_render` is added in Phase 3, when the renderers exist. Registering a
    # placeholder now would mean a template could call it and silently render
    # nothing, which is worse than an undefined error.
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True


__all__ = [
    "ARG_FILTERS",
    "BN_MONTHS",
    "EM_DASH",
    "FILTERS",
    "asset_url",
    "bn_currency",
    "bn_date",
    "bn_label",
    "bn_num",
    "clear_asset_cache",
    "mask_none",
    "register_filters",
    "static_url",
]

_ = re  # kept for regex-based filters added in Phase 3
