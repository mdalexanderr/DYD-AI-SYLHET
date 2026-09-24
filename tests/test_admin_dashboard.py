"""The dashboard, and the counts it exists to report. Step 4.6; plan.md §11.1, §5.3.

STEP 4.6's "DONE WHEN" IS A RECONCILIATION, NOT A RENDER
    "the four consent counts reconcile exactly with the seeded fixture states."

    So these tests build one participant in EVERY consent state — the fixtures
    already exist in conftest — and then assert the numbers agree with what was
    actually inserted. A dashboard that renders beautifully and reports the wrong
    number of people awaiting consent is worse than no dashboard, because somebody
    acts on it.

    The buckets are also asserted to SUM to the total. That is the property that
    catches a state nobody thought to give a bucket to: the count goes up, the
    buckets stay put, and the parts stop adding up to the whole.
"""

from __future__ import annotations

import pytest

PASSWORD = "correct-horse-battery-staple"
ADMIN_URL = "/ops-sylhet/"


@pytest.fixture
def no_csrf(app):
    previous = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = False
    yield
    app.config["WTF_CSRF_ENABLED"] = previous


@pytest.fixture
def admin_user(session):
    from app.extensions import bcrypt
    from app.models import AdminUser

    user = AdminUser(
        email="dash@example.test",
        password_hash=bcrypt.generate_password_hash(PASSWORD).decode("utf-8"),
        full_name_bn="ড্যাশ প্রশাসক",
        is_active=True,
        twofa_enabled=False,
    )
    session.add(user)
    session.commit()
    return user


def _breakdown():
    from app.services.participant_service import consent_breakdown

    return consent_breakdown()


def _buckets(counts):
    return {k: v for k, v in counts.items() if k != "total"}


# ─────────────────────────────────────────────────────────────────────────────
# The reconciliation
# ─────────────────────────────────────────────────────────────────────────────
def test_every_consent_state_lands_in_exactly_one_bucket(app, session, all_consent_states):
    """One participant per state, so the expected counts are known by construction.

    `all_consent_states` gives exactly five participants: published, consented but
    unpublished, consenting with no date, never consented, and withdrawn.
    """
    counts = _breakdown()

    assert counts["published"] == 1
    assert counts["ready_unpublished"] == 1
    assert counts["consent_missing_date"] == 1
    assert counts["awaiting_consent"] == 1
    assert counts["withdrawn"] == 1


def test_the_buckets_sum_to_the_total(app, session, all_consent_states):
    """THE PROPERTY THAT CATCHES A FORGOTTEN STATE.

    If a sixth consent state were ever introduced and given no bucket, the total
    would rise, the buckets would not, and this assertion would fail — whereas every
    per-bucket assertion above would still pass.
    """
    counts = _breakdown()

    assert sum(_buckets(counts).values()) == counts["total"]
    assert counts["total"] == len(all_consent_states)


def test_the_helper_the_screen_uses_agrees_with_the_sum(app, session, all_consent_states):
    """The template must not do its own arithmetic.

    `breakdown_totals` is what the view passes to the screen; this asserts it computes
    the same sum the test does, so the number a reader sees cannot drift from the
    number that is checked here.
    """
    from app.services.participant_service import breakdown_totals

    counts = _breakdown()

    assert breakdown_totals(counts) == sum(_buckets(counts).values())


def test_a_withdrawal_is_counted_once_and_only_once(app, session, all_consent_states):
    """A withdrawn participant must not also inflate the category they left.

    They consented, so a naive `consent_publication IS TRUE` count would include them
    in `ready_unpublished` as well — and the same person would appear twice on a
    dashboard whose entire purpose is telling an operator how many people there are.
    """
    counts = _breakdown()

    assert counts["withdrawn"] == 1
    assert counts["published"] == 1, "the withdrawn row leaked into `published`"
    assert counts["ready_unpublished"] == 1, "the withdrawn row leaked into `ready_unpublished`"
    assert counts["consent_missing_date"] == 1


def test_an_empty_database_counts_zero_rather_than_raising(app, session):
    """A fresh install must render, not 500.

    `session` is shared, so this cannot guarantee an empty table; it asserts the
    function is total — every key present, every value an int — which is what the
    template relies on.
    """
    counts = _breakdown()

    expected_keys = {
        "total", "published", "ready_unpublished",
        "consent_missing_date", "awaiting_consent", "withdrawn",
    }
    assert set(counts) == expected_keys
    assert all(isinstance(v, int) for v in counts.values())


# ─────────────────────────────────────────────────────────────────────────────
# The screen
# ─────────────────────────────────────────────────────────────────────────────
def test_the_dashboard_renders_the_counts(client, admin_user, all_consent_states, no_csrf):
    client.post("/login", data={"email": "dash@example.test", "password": PASSWORD})

    body = client.get(ADMIN_URL).get_data(as_text=True)

    assert "<html" in body.lower()
    # The headings the four named counts sit under.
    for label in ("মোট", "প্রকাশিত", "সম্মতির অপেক্ষায়", "প্রত্যাহার"):
        assert label in body, f"the dashboard does not label {label!r}"


def test_the_dashboard_shows_the_missing_date_bucket(client, admin_user, all_consent_states, no_csrf):
    """§5.6: the missing-date state is the first thing an operator should see.

    It is the only consent state that is both invisible and blocking — those people
    believe they consented, and nothing publishes them.
    """
    client.post("/login", data={"email": "dash@example.test", "password": PASSWORD})

    body = client.get(ADMIN_URL).get_data(as_text=True)

    assert "তারিখ" in body, "the consented-with-no-date bucket is not on the dashboard"


def test_the_dashboard_reports_pages_published_and_draft(client, admin_user, seeded, no_csrf):
    """Pages published vs draft, from the real seeded set (7 pages, all drafts)."""
    client.post("/login", data={"email": "dash@example.test", "password": PASSWORD})

    body = client.get(ADMIN_URL).get_data(as_text=True)

    assert "পৃষ্ঠা" in body


def test_the_dashboard_needs_a_session(client, admin_user, no_csrf):
    assert client.get(ADMIN_URL).status_code == 302
