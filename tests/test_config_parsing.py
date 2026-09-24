"""How configuration values are read out of the environment. plan.md §20.1, §12.1.

WHY THIS FILE EXISTS
    `ADMIN_IP_ALLOWLIST=` with its documentation on the same line — which is exactly
    how `.env.example` documents it — resolved to the COMMENT TEXT rather than to
    nothing, because python-dotenv only strips an inline comment when a non-empty
    value precedes it. The allowlist then became truthy with no valid entries and
    denied every admin request.

    These tests pin both halves of the fix: a comment-only value reads as absent, and
    a value that legitimately CONTAINS `#` is not truncated. The second half matters
    as much as the first — SECRET_KEY and passwords can contain `#`.

    They exercise `_raw`/`_csv`/`_str` directly rather than going through the config
    classes, because those classes evaluate their attributes once at import time and
    cannot be re-read per test.
"""

from __future__ import annotations

import pytest

from app.config import _bool, _csv, _int, _raw, _str

#: The exact string python-dotenv produced for `ADMIN_IP_ALLOWLIST=` in the
#: development `.env` — captured from the running app, not invented.
COMMENT_ONLY = "# CIDR list, comma-separated; empty = off."


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every test here names the variables it cares about; remove them afterwards."""
    for name in ("DYD_TEST_CSV", "DYD_TEST_STR", "DYD_TEST_INT", "DYD_TEST_BOOL"):
        monkeypatch.delenv(name, raising=False)


def test_a_comment_only_value_reads_as_absent(monkeypatch):
    """THE BUG. Treated as data, this string switched a security control on."""
    monkeypatch.setenv("DYD_TEST_CSV", COMMENT_ONLY)

    assert _raw("DYD_TEST_CSV") == ""
    assert _csv("DYD_TEST_CSV") == ()


def test_the_comment_becomes_a_truthy_allowlist_if_unhandled(monkeypatch):
    """The failure mode, demonstrated rather than described.

    This is what the raw string splits into — two entries, neither parseable as a
    CIDR, and a truthy tuple, so `if not allowlist: return None` never fires.
    """
    parts = tuple(p.strip() for p in COMMENT_ONLY.split(",") if p.strip())

    assert parts == ("# CIDR list", "comma-separated; empty = off.")
    assert bool(parts) is True, "an 'empty' setting must not be truthy"


def test_a_comment_only_int_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("DYD_TEST_INT", "   # thirty minutes")

    assert _int("DYD_TEST_INT", 1800) == 1800


def test_a_comment_only_bool_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("DYD_TEST_BOOL", "# on by default")

    assert _bool("DYD_TEST_BOOL", True) is True


def test_a_value_containing_a_hash_is_not_truncated(monkeypatch):
    """THE OTHER HALF OF THE FIX, and the reason it is not a blanket strip.

    A SECRET_KEY or a database password with a `#` in it must survive intact.
    Truncating one of those would break the deployment in a way that is far harder to
    diagnose than the bug being fixed.
    """
    monkeypatch.setenv("DYD_TEST_STR", "abc#def#ghi")

    assert _str("DYD_TEST_STR") == "abc#def#ghi"


def test_a_hypothetical_secret_with_a_trailing_hash_survives(monkeypatch):
    monkeypatch.setenv("DYD_TEST_STR", "p4ss#w0rd#")

    assert _str("DYD_TEST_STR") == "p4ss#w0rd#"


def test_a_normal_csv_still_parses(monkeypatch):
    """The fix must not have broken the ordinary case."""
    monkeypatch.setenv("DYD_TEST_CSV", "10.0.0.0/8, 203.0.113.7 ,127.0.0.1")

    assert _csv("DYD_TEST_CSV") == ("10.0.0.0/8", "203.0.113.7", "127.0.0.1")


def test_a_csv_of_only_commas_is_empty(monkeypatch):
    monkeypatch.setenv("DYD_TEST_CSV", " , , ")

    assert _csv("DYD_TEST_CSV") == ()


def test_an_absent_variable_uses_the_default():
    assert _raw("DYD_TEST_CSV_NOT_SET") is None
    assert _csv("DYD_TEST_CSV_NOT_SET", ("fallback",)) == ("fallback",)


def test_an_int_that_is_genuinely_broken_still_raises(monkeypatch):
    """The comment fix must not swallow a real typo.

    `ADMIN_IP_ALLOWLIST=` documented inline is a trap; `SESSION_LIFETIME_SECONDS=8h`
    is a mistake somebody needs to be told about, loudly, at boot.
    """
    monkeypatch.setenv("DYD_TEST_INT", "eight hours")

    with pytest.raises(ValueError, match="DYD_TEST_INT must be an integer"):
        _int("DYD_TEST_INT", 28800)
