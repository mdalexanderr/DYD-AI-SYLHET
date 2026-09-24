"""Shared pytest fixtures. execution-plan step 2.17, plan.md §19.3.

WHY THESE FIXTURES AND NOT SOMETHING SIMPLER
    The suite has one job beyond regression: it is the only place the CONSENT RULES
    can be exercised exhaustively. §8.2 and §19.3 both say so explicitly — "the
    consent rules in §5.3 cannot be verified against three happy-path rows" — which
    is why every consent state gets its own factory fixture below rather than tests
    building participants inline.

A FRESH SCHEMA PER TEST
    drop_all/create_all is slower than a transaction rollback per test, and it is
    chosen deliberately: a leaked transaction that half-applies a consent change
    produces a test that passes once and fails on the second run, which is the
    single most expensive kind of test to debug. On a skeleton this suite runs in
    well under a second either way.

    TestConfig uses StaticPool so this works at all. Without it, SQLite's default
    pool hands every new connection its OWN empty in-memory database, the schema
    created here is invisible to the next connection, and every test fails with
    "no such table" — which reads as a model bug rather than a pooling one.
"""

from __future__ import annotations

from datetime import date

import pytest

from app import create_app
from app.constants import ConsentSource, Education, OutcomeType
from app.extensions import db as _db

# ─────────────────────────────────────────────────────────────────────────────
# Application and database
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def app():
    """One application per test session, built with TestConfig.

    Session-scoped because building the app is the slow part (extensions, filters,
    blueprints) and nothing in the suite mutates application config. The database
    is what must be fresh, and that is handled per test.
    """
    return create_app("testing")


@pytest.fixture
def session(app):
    """A clean schema and a live session. The entry point for nearly every test."""
    with app.app_context():
        _db.drop_all()
        _db.create_all()
        try:
            yield _db.session
        finally:
            _db.session.rollback()
            _db.session.remove()


@pytest.fixture
def client(app, session):
    """A test client with a fresh schema already in place.

    Depends on `session` purely so the schema exists before the first request. The
    request gets its own session, so anything a test seeds must be COMMITTED to be
    visible to the request — which is realistic, and catches a test that relies on
    uncommitted state that would not survive an actual request in production.
    """
    return app.test_client()


@pytest.fixture
def runner(app):
    """A Click runner, for the CLI commands (check-health, seed, render-check)."""
    return app.test_cli_runner()


# ─────────────────────────────────────────────────────────────────────────────
# Participant factories — one per consent state (§5.3, §8.2, §19.3)
# ─────────────────────────────────────────────────────────────────────────────


def _participant_kwargs(**overrides):
    """Defaults that satisfy every NOT NULL column, so a test states only what it
    is about. `education` has no default and is NOT NULL; the booleans have
    PYTHON-side defaults only, which the ORM applies during flush."""
    base = {
        "slug": "test-participant",
        "name_bn": "রূপা আক্তার",
        "education": Education.HSC,
        "batch": 1,
    }
    base.update(overrides)
    return base


@pytest.fixture
def make_participant(session):
    """Build, add and COMMIT a Participant. Returns the instance.

    Committing rather than flushing is deliberate: a test that seeds data and then
    makes an HTTP request needs the data to be visible to the request's separate
    session. Flushing would make half the suite pass for the wrong reason.
    """
    from app.models import Participant

    counter = {"n": 0}

    def _make(**overrides):
        counter["n"] += 1
        kwargs = _participant_kwargs(**overrides)
        if "slug" not in overrides:
            kwargs["slug"] = f"test-participant-{counter['n']}"
        participant = Participant(**kwargs)
        session.add(participant)
        session.commit()
        return participant

    return _make


@pytest.fixture
def consented_published(make_participant):
    """Consent given, dated, and published. The only state that may appear publicly."""
    return make_participant(
        slug="consented-published",
        consent_publication=True,
        consent_date=date(2026, 3, 1),
        consent_source=ConsentSource.WRITTEN_FORM,
        is_published=True,
        outcome_type=OutcomeType.FREELANCING,
    )


@pytest.fixture
def consented_unpublished(make_participant):
    """Consent given but not published. Legal, and must not appear on the site."""
    return make_participant(
        slug="consented-unpublished",
        consent_publication=True,
        consent_date=date(2026, 3, 1),
        consent_source=ConsentSource.WRITTEN_FORM,
        is_published=False,
    )


@pytest.fixture
def consent_without_date(make_participant):
    """The §5.3 rule-3 case: consented, but with no date recorded.

    This participant must be VISIBLE in the admin consent dashboard (they need a
    date chased up) and must NEVER be publishable. Both halves matter.
    """
    return make_participant(
        slug="consent-without-date",
        consent_publication=True,
        consent_date=None,
        is_published=False,
    )


@pytest.fixture
def not_consented(make_participant):
    """No consent at all. The record exists; it must never be public."""
    return make_participant(
        slug="not-consented",
        consent_publication=False,
        consent_date=None,
        is_published=False,
    )


@pytest.fixture
def withdrawn(make_participant):
    """Consented once, then withdrew (§5.3 rule 4).

    The ROW IS KEPT. Deleting it would destroy the evidence that consent was ever
    given and withdrawn, and would make the audit trail lie.
    """
    from app.models.base import utcnow

    return make_participant(
        slug="withdrawn",
        consent_publication=True,
        consent_date=date(2026, 3, 1),
        consent_withdrawn_at=utcnow(),
        is_published=False,
    )


@pytest.fixture
def all_consent_states(
    consented_published,
    consented_unpublished,
    consent_without_date,
    not_consented,
    withdrawn,
):
    """Every state in one place, for the dashboard and filter tests."""
    return {
        "published": consented_published,
        "unpublished": consented_unpublished,
        "no_date": consent_without_date,
        "not_consented": not_consented,
        "withdrawn": withdrawn,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Bangla edge cases (§19.3)
# ─────────────────────────────────────────────────────────────────────────────

#: Names that break things in a Bangladeshi context. Each one is a bug that has
#: actually been seen in a form-based system in this region.
BANGLA_EDGE_NAMES = [
    "বিষ্ণুপ্রসাদ দাশ",                      # conjuncts: ষ্ণ and প্র
    "মোঃ আব্দুল করিম",                     # the ubiquitous মোঃ abbreviation
    "শাহজাদা\u200dআলম",                     # zero-width joiner
    "র\u200dূপা",                            # ZWJ mid-word
    "দাস\u00a0রানী",                        # non-breaking space
    ("বাংলাদেশ কৃত্রিম বুদ্ধিমত্তা প্রশিক্ষণার্থীর নাম" * 2)[:60],  # 60-char name
    "Lata Rani Das",                          # Latin transliteration
]


@pytest.fixture
def bangla_names():
    return list(BANGLA_EDGE_NAMES)


# ─────────────────────────────────────────────────────────────────────────────
# Seeded reference data, for tests that need pages/sections
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def seeded(session):
    """Run the real seeder against the test database.

    Uses the production seeder rather than fixtures, so a change that breaks
    seeding breaks the test suite too rather than only the deploy.
    """
    from app.seeds import seed_reference_data

    return seed_reference_data()
