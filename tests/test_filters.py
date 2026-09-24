"""Jinja filters. execution-plan step 2.7 and §19.3.

STEP 2.7'S TWO ACCEPTANCE EXAMPLES ARE LITERAL TESTS HERE
    `bn_date(date(2026, 9, 23))` must render `২৩ সেপ্টেম্বর ২০২৬` and
    `bn_num(124)` must render `১২৪`. They are written exactly as the plan writes
    them, because a plan that states an observable outcome and a test that asserts
    something adjacent is how a spec quietly stops being met.

WHY EVERY NUMBER A READER SEES IS IN BANGLA (§7.4)
    A government page that says "124" in a Bangla sentence reads as a foreign
    document. The filters exist so that no template ever has to remember this.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.filters import (
    bn_currency,
    bn_date,
    bn_num,
    bn_num_or_dash,
    mask_none,
)

# ─────────────────────────────────────────────────────────────────────────────
# bn_num — §7.4: Bangla digits everywhere
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "০"),
        (1, "১"),
        (9, "৯"),
        (10, "১০"),
        (124, "১২৪"),
        (1000, "১০০০"),
        (2026, "২০২৬"),
        (300, "৩০০"),
    ],
)
def test_bn_num_renders_bangla_digits(value, expected):
    assert bn_num(value) == expected


def test_bn_num_renders_a_string_of_digits():
    """Templates frequently hold a value that is already a string."""
    assert bn_num("124") == "১২৪"


def test_bn_num_leaves_bangla_digits_alone():
    """Idempotent, so a value passed through twice is not corrupted."""
    assert bn_num("১২৪") == "১২৪"


def test_bn_num_does_not_invent_a_value():
    """Nothing must be rendered for an absent number — not a zero.

    A missing figure shown as ০ is a false statement about the programme, and this
    rule matters most for the statistics pages (§6.5, S6).
    """
    assert bn_num(None) == ""


def test_bn_num_keeps_a_negative_sign():
    assert bn_num(-12) == "-১২"


def test_bn_num_preserves_a_decimal_rather_than_rounding_it():
    """A decimal figure must not be silently rounded.

    4.9 becoming "৫" is a different number from the one the data holds, and on a
    results page that is a wrong statement, not a rounding preference.
    """
    assert bn_num(4.9) == "৪.৯"


# ─────────────────────────────────────────────────────────────────────────────
# bn_date — step 2.7's acceptance example
# ─────────────────────────────────────────────────────────────────────────────


def test_bn_date_renders_the_long_bangla_form():
    """Verbatim from step 2.7: `bn_date(date(2026, 9, 23))` -> `২৩ সেপ্টেম্বর ২০২৬`."""
    assert bn_date(date(2026, 9, 23)) == "২৩ সেপ্টেম্বর ২০২৬"


@pytest.mark.parametrize(
    ("month", "expected_bn"),
    [
        (1, "জানুয়ারি"),
        (2, "ফেব্রুয়ারি"),
        (3, "মার্চ"),
        (4, "এপ্রিল"),
        (5, "মে"),
        (6, "জুন"),
        (7, "জুলাই"),
        (8, "আগস্ট"),
        (9, "সেপ্টেম্বর"),
        (10, "অক্টোবর"),
        (11, "নভেম্বর"),
        (12, "ডিসেম্বর"),
    ],
)
def test_bn_date_has_all_twelve_bangla_months(month, expected_bn):
    """All twelve, because a missing month is a page that renders a blank where a
    date should be — and it would be missing precisely in the months nobody tested."""
    rendered = bn_date(date(2026, month, 1))
    assert expected_bn in rendered


def test_bn_date_renders_no_leading_zero():
    """`০১ সেপ্টেম্বর` is how a form is filled in, not how a date is read."""
    assert bn_date(date(2026, 9, 1)).startswith("১ ")


def test_bn_date_renders_a_dash_for_none():
    """An em dash, not an empty string: a blank table cell reads as "zero", and on a
    date field that is a false statement (§5.4)."""
    assert bn_date(None) == "—"


def test_bn_date_accepts_a_datetime():
    # A naive datetime on purpose: the app's own `utcnow()` returns a naive value
    # (app/models/base.py), so this is the shape a filter actually receives. Using a
    # tz-aware datetime here would test a case the application never produces.
    naive = datetime(2026, 9, 23, 14, 30)  # noqa: DTZ001
    assert "সেপ্টেম্বর" in bn_date(naive)


def test_bn_date_has_a_short_style():
    """A table cell needs a shorter form than a paragraph."""
    short = bn_date(date(2026, 9, 23), style="short")
    assert short
    assert "২০২৬" in short


# ─────────────────────────────────────────────────────────────────────────────
# The suppression rule (§6.5, S6) — the one with privacy consequences
# ─────────────────────────────────────────────────────────────────────────────


def test_bn_num_or_dash_suppresses_on_the_sample_size_not_the_value():
    """S6: the decision is made on how many RECORDS underlie the figure.

    This is the subtle case the whole rule turns on. The value shown might be 7 —
    an average, or a total — while only three people produced it. Suppressing on the
    displayed number would let "average 7" through for a group of two, which
    identifies both of them.
    """
    assert bn_num_or_dash(7, suppress_below=5, count=3) == "—"
    assert bn_num_or_dash(3, suppress_below=5, count=3) == "—"


def test_bn_num_or_dash_renders_at_the_threshold():
    """Exclusive, not inclusive: exactly 5 records is safe to show."""
    assert bn_num_or_dash(5, suppress_below=5, count=5) == "৫"


def test_bn_num_or_dash_renders_above_the_threshold():
    assert bn_num_or_dash(124, suppress_below=5, count=124) == "১২৪"


def test_bn_num_or_dash_dashes_a_missing_value():
    assert bn_num_or_dash(None) == "—"
    assert bn_num_or_dash("") == "—"


def test_bn_num_or_dash_renders_zero_when_zero_is_meant():
    """A genuine zero is a fact and must be shown as ০, not suppressed.

    Suppression exists to hide SMALL numbers. Treating 0 as "below the threshold"
    would make an outcome nobody chose indistinguishable from one that was hidden —
    exactly the ambiguity S6 exists to avoid.
    """
    assert bn_num_or_dash(0, suppress_below=0, count=0) == "০"


def test_bn_num_or_dash_does_not_suppress_when_no_sample_size_is_given():
    """A caller with no cohort figure must get the value, not a silent dash.

    Suppressing by default would make a missing argument look like a privacy
    decision, and the statistic would simply vanish from the site with no error.
    """
    assert bn_num_or_dash(124, suppress_below=5) == "১২৪"
    assert bn_num_or_dash(124, count=124) == "১২৪"


# ─────────────────────────────────────────────────────────────────────────────
# bn_currency / mask_none
# ─────────────────────────────────────────────────────────────────────────────


def test_bn_currency_uses_the_bangla_taka_sign_and_digits():
    rendered = bn_currency(5000)
    assert "৫০০০" in rendered
    assert "৳" in rendered


def test_bn_currency_renders_a_dash_for_none():
    assert bn_currency(None) == "—"
    assert bn_currency("") == "—"


def test_mask_none_renders_a_dash():
    assert mask_none(None) == "—"


def test_mask_none_passes_a_value_through():
    assert mask_none("রূপা আক্তার") == "রূপা আক্তার"


def test_mask_none_treats_an_empty_string_as_absent():
    """An empty string in a table cell looks like a rendering bug. A dash says
    "there is nothing here", which is a different and true statement."""
    assert mask_none("") == "—"
