"""Bangla text handling. Step 2.17, plan.md §19.3.

WHY THIS FILE EXISTS AT ALL
    Every one of these cases has broken a real Bangladeshi data-entry system:

      • conjuncts (বিষ্ণুপ্রসাদ) — ষ্ণ and প্র are single glyphs built from multiple
        code points, so a naive length check or a byte-based truncation splits them.
      • the মোঃ abbreviation — a colon after three letters, which a lexer treats as
        punctuation.
      • zero-width joiners and non-breaking spaces — invisible, and they make two
        strings that LOOK identical compare as different.
      • NFC vs NFD — the same name can be stored two ways; a search that compares
        bytes finds one and misses the other.

    These are not curiosities. They are the reason §9.4 makes utf8mb4 mandatory and
    the reason `search_blob` is normalised rather than stored raw.
"""

from __future__ import annotations

import unicodedata

from app.models.people import build_search_blob, normalise_query

# ─────────────────────────────────────────────────────────────────────────────
# Round-tripping through the database
# ─────────────────────────────────────────────────────────────────────────────


def test_every_edge_case_name_survives_a_round_trip(make_participant, bangla_names, session):
    """Store and re-read. If the connection is not utf8mb4, this is where it shows.

    A latin1 MySQL schema mangles Bangla SILENTLY — the insert succeeds and the text
    comes back as question marks or mojibake, which is only ever caught by a human
    reading the site (§9.4, R5). This test catches it in CI instead.
    """
    for index, name in enumerate(bangla_names, start=1):
        participant = make_participant(slug=f"round-trip-{index}", name_bn=name)
        session.expire_all()
        stored = session.get(type(participant), participant.id)
        assert stored is not None
        assert stored.name_bn == name, (
            f"name changed on round-trip.\n  wrote: {name!r}\n  read:  {stored.name_bn!r}\n"
            "This is the signature of a non-utf8mb4 database connection (§9.4, R5)."
        )


def test_a_sixty_character_name_fits(make_participant, bangla_names):
    """Bangladeshi names with all four parts plus a title routinely reach 60 chars."""
    longest = max(bangla_names, key=len)
    participant = make_participant(slug="long-name", name_bn=longest)
    assert participant.name_bn == longest
    assert len(participant.name_bn) >= 40


def test_mixed_script_name_is_accepted(make_participant):
    """Latin transliteration must be storable, because it is what appears on a
    passport and therefore on a certificate."""
    participant = make_participant(slug="latin-name", name_bn="Lata Rani Das")
    assert participant.name_bn == "Lata Rani Das"
    assert participant.name_en is None or isinstance(participant.name_en, str)


# ─────────────────────────────────────────────────────────────────────────────
# normalise_query / build_search_blob
# ─────────────────────────────────────────────────────────────────────────────


def test_normalise_query_applies_nfc():
    """NFC, so a decomposed input matches a composed record.

    The fixture uses a name containing `ো` (U+09CB), which has a canonical
    decomposition into `ে` + `া`. Bengali vowel signs like `ূ` do NOT decompose, so
    an earlier version of this test used a name that normalised to itself, and the
    assertion "these differ" failed — which is the test being wrong, not the filter.
    """
    composed = unicodedata.normalize("NFC", "মোঃ আব্দুল করিম")
    decomposed = unicodedata.normalize("NFD", "মোঃ আব্দুল করিম")
    assert decomposed != composed, (
        "the fixture does not actually decompose — pick a name containing a vowel "
        "sign with a canonical decomposition, e.g. `ো` (U+09CB)"
    )

    assert normalise_query(decomposed) == normalise_query(composed)


def test_normalise_query_strips_zero_width_characters():
    """A zero-width joiner is invisible. It must not make two identical-looking
    names unmatchable."""
    with_zwj = "শাহজাদা\u200dআলম"
    without = "শাহজাদাআলম"
    assert normalise_query(with_zwj) == normalise_query(without)


def test_normalise_query_strips_a_non_breaking_space():
    assert normalise_query("দাস\u00a0রানী") == normalise_query("দাস রানী")


def test_normalise_query_is_case_insensitive_for_latin():
    """casefold(), not lower() — lower() is wrong for several scripts and the point
    is to be right for the ones we do not speak."""
    assert normalise_query("LATA RANI DAS") == normalise_query("lata rani das")


def test_normalise_query_handles_an_empty_string():
    assert normalise_query("") == ""
    assert normalise_query("   ") == ""


def test_normalise_query_survives_whitespace_only_garbage():
    assert normalise_query("\u200b\u200c\u200d") == ""


def test_search_blob_contains_a_normalised_name():
    blob = build_search_blob("বিষ্ণুপ্রসাদ দাশ", None)
    assert blob == normalise_query(blob), "the blob must already be normalised"
    assert "বিষ্ণুপ্রসাদ" in blob


def test_search_blob_includes_both_scripts_when_both_are_known():
    """A search is done in whatever script the operator types in."""
    blob = build_search_blob("রূপা আক্তার", "Rupa Akter")
    assert "রূপা" in blob
    assert "rupa" in blob


def test_search_blob_of_nothing_is_empty_not_an_error():
    assert build_search_blob(None, None) == ""


# ─────────────────────────────────────────────────────────────────────────────
# The end-to-end property the above exists to guarantee
# ─────────────────────────────────────────────────────────────────────────────


def test_a_zwj_name_is_findable_by_a_query_typed_without_the_joiner(app, session):
    """The whole point: searching for what you SEE finds what is stored.

    The joiner is invisible, so a reader looking at শাহজাদাআলম cannot know it is
    there, and will type the name without it — possibly with a space instead, since
    it looks like two words. `search_blob` therefore has to be normalised at WRITE
    time; a search that normalised only the query would still miss.

    The assertion is per-TERM, because that is how the participant search will work:
    the query is tokenised and each term must appear. Asserting the whole query as
    one substring would be testing a search implementation that does not exist yet.
    """
    from sqlalchemy import select

    from app.models import Participant

    participant = Participant(
        slug="zwj-search",
        name_bn="শাহজাদা\u200dআলম",
        education="HSC",
        batch=1,
    )
    session.add(participant)
    session.commit()

    blob = participant.search_blob
    assert "\u200d" not in blob, "the zero-width joiner survived into search_blob"

    for term in ("শাহজাদা", "আলম"):
        needle = normalise_query(term)
        found = session.execute(
            select(Participant).where(Participant.search_blob.contains(needle))
        ).scalars().all()
        assert found, (
            f"searching for {term!r} did not find a name containing it. This is the bug "
            "that makes a search box feel broken to real users while every unit test "
            "passes."
        )
