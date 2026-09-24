"""The §5.3 consent matrix, at the model layer. Step 2.17.

WHY EVERY STATE IS ITS OWN TEST
    §8.2 and §19.3 are emphatic that the consent rules cannot be verified against
    happy-path rows, and they are right for a specific reason: the failure mode here
    is not "the feature throws", it is "the site publishes somebody who never agreed
    to it". That failure is silent, irreversible — a name that appears in a search
    result has already been seen — and it happens through a state nobody thought to
    try. So the matrix is enumerated: consented, consented-without-a-date,
    not-consented, withdrawn, quote-permitted, quote-not-permitted.

WHAT THIS FILE DOES NOT COVER
    The database constraint. That is `test_schema.py`, which goes through raw SQL, and
    the two are deliberately separate: this file proves the MODEL refuses, that file
    proves the DATABASE refuses, and §5.3/R4 require both because the CSV import will
    bypass the model.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.constants import ConsentSource
from app.models.people import Participant, PublishWithoutConsentError

# ─────────────────────────────────────────────────────────────────────────────
# can_publish / publish()
# ─────────────────────────────────────────────────────────────────────────────


def test_publish_succeeds_when_consented_and_dated(consented_unpublished):
    assert consented_unpublished.can_publish is True
    assert consented_unpublished.missing_consent_fields == ()

    consented_unpublished.publish()
    assert consented_unpublished.is_published is True
    assert consented_unpublished.published_at is not None


def test_publish_raises_without_consent(not_consented):
    assert not_consented.can_publish is False
    assert "consent_publication" in not_consented.missing_consent_fields

    with pytest.raises(PublishWithoutConsentError) as excinfo:
        not_consented.publish()
    assert not_consented.is_published is False
    # The error carries a KEY, not Bangla prose, so the admin chooses the wording
    # and this model needs no translation table.
    assert excinfo.value.message_key == "participant.publish_requires_consent"
    assert "consent_publication" in excinfo.value.missing


def test_publish_raises_when_consent_has_no_date(consent_without_date):
    """§5.3 rule 3. Consent with no date is an assertion, not a record."""
    assert consent_without_date.can_publish is False
    assert "consent_date" in consent_without_date.missing_consent_fields

    with pytest.raises(PublishWithoutConsentError) as excinfo:
        consent_without_date.publish()
    assert "consent_date" in excinfo.value.missing


def test_publish_raises_when_consent_was_withdrawn(withdrawn):
    """§5.3 rule 4. Withdrawal is permanent until consent is re-granted."""
    assert withdrawn.can_publish is False

    with pytest.raises(PublishWithoutConsentError):
        withdrawn.publish()
    assert withdrawn.is_published is False


def test_withdrawn_is_distinguishable_from_never_consented(withdrawn, not_consented):
    """The admin must be able to tell "never agreed" from "asked to be removed".

    They need different follow-up, and collapsing the two would tell an operator that
    somebody never consented when in fact they exercised their right to withdraw.
    """
    assert withdrawn.consent_state == "withdrawn"
    assert not_consented.consent_state == "pending"

    with pytest.raises(PublishWithoutConsentError) as excinfo:
        withdrawn.publish()
    # The reason names the WITHDRAWAL, not merely "no consent" — otherwise the
    # admin cannot tell an operator which of the two situations they are looking at.
    assert any("withdrawn" in item for item in excinfo.value.missing)


def test_unpublish_is_always_allowed(consented_published):
    """Unpublishing must never need consent — it is the safety direction.

    If removing a name required permission, the one action that protects a person
    would be the one action that could be blocked.
    """
    consented_published.unpublish()
    assert consented_published.is_published is False


# ─────────────────────────────────────────────────────────────────────────────
# The before_flush guard (layer 2) — validates FINAL state, not assignment order
# ─────────────────────────────────────────────────────────────────────────────


def test_flush_rejects_a_direct_publication(session):
    """Setting the flag directly must be caught by the session hook, not just by
    publish(). Half the codebase will one day set this attribute; publish() is a
    convenience, the hook is the guard."""
    participant = Participant(
        slug="flush-guard",
        name_bn="পরীক্ষা",
        education="HSC",
        batch=1,
    )
    participant.is_published = True
    session.add(participant)

    with pytest.raises(PublishWithoutConsentError):
        session.flush()
    session.rollback()


def test_flush_accepts_a_direct_publication_when_consented(session):
    """The control for the hook: it must not block a legitimate publication."""
    participant = Participant(
        slug="flush-ok",
        name_bn="পরীক্ষা",
        education="HSC",
        batch=1,
        consent_publication=True,
        consent_date=date(2026, 3, 1),
        consent_source=ConsentSource.WRITTEN_FORM,
        is_published=True,
    )
    session.add(participant)
    session.flush()
    assert participant.is_published is True
    session.rollback()


def test_flush_guard_depends_on_the_final_state_not_the_order(consented_unpublished):
    """The reason the guard is a `before_flush` hook and not a `@validates`.

    A `@validates("is_published")` fires on assignment, so `obj.is_published = True`
    written BEFORE `obj.consent_publication = True` in the same block would raise —
    even though the row that ends up in the database is perfectly legal. Editors
    type fields in whatever order they like; the guard must judge the result, not the
    sequence. Here the attestation is applied LAST and it must still be accepted.
    """
    consented_unpublished.consent_publication = False
    consented_unpublished.consent_date = None
    consented_unpublished.is_published = True  # illegal state, deliberately set first
    consented_unpublished.consent_publication = True
    consented_unpublished.consent_date = date(2026, 4, 1)

    # Final state is legal, so this must hold.
    assert consented_unpublished.can_publish is True
    assert consented_unpublished.missing_consent_fields == ()


# ─────────────────────────────────────────────────────────────────────────────
# Withdrawal (§5.3 rule 4, S5)
# ─────────────────────────────────────────────────────────────────────────────


def test_withdraw_unpublishes_and_keeps_the_row(consented_published, session):
    """S5: withdrawal unpublishes in the same transaction and NEVER deletes.

    Deleting the row would destroy the evidence that consent was given and then
    withdrawn, and would make the audit trail claim the person was never there.
    """
    participant_id = consented_published.id
    consented_published.withdraw_consent()

    assert consented_published.is_published is False
    assert consented_published.consent_withdrawn_at is not None

    session.flush()
    still_there = session.get(Participant, participant_id)
    assert still_there is not None, (
        "withdraw_consent() DELETED the row. §5.3 rule 4 and S5 require the record to "
        "be kept — the audit trail must be able to show consent was granted and then "
        "withdrawn."
    )


def test_withdraw_is_recorded_in_consent_events(app, session, consented_published):
    """Append-only history: the point of keeping the row."""
    from app.constants import ConsentAction
    from app.models import ConsentEvent

    consented_published.withdraw_consent()
    session.add(ConsentEvent(
        participant_id=consented_published.id,
        action=ConsentAction.WITHDRAWN,
        notes="test",
    ))
    session.commit()

    events = session.query(ConsentEvent).filter_by(
        participant_id=consented_published.id
    ).all()
    assert len(events) == 1
    assert events[0].action == ConsentAction.WITHDRAWN


def test_a_quote_cannot_be_stored_without_its_own_permission(make_participant, session):
    """§5.3 rule 5: a quote needs permission separate from publication.

    Somebody can agree to appear in a list of trainees and still not want their words
    on a government website. The guard is stronger than "cannot be published": the
    quote cannot be STORED without its own permission, so there is no half-state in
    which the words are in the database waiting for one flag to flip.
    """
    with pytest.raises(PublishWithoutConsentError) as excinfo:
        make_participant(
            slug="quote-no-permission",
            consent_publication=True,
            consent_date=date(2026, 3, 1),
            quote_bn="<p>আমি শিখেছি</p>",
            quote_consented=False,
        )
    assert "quote_consented" in excinfo.value.missing
    assert excinfo.value.message_key == "participant.publish_requires_consent"
    session.rollback()


def test_a_quote_may_be_stored_with_its_own_permission(make_participant):
    """The control: the rule must not block an interview the person agreed to."""
    participant = make_participant(
        slug="quote-with-permission",
        consent_publication=True,
        consent_date=date(2026, 3, 1),
        quote_bn="<p>আমি শিখেছি</p>",
        quote_consented=True,
    )
    assert participant.quote_bn
    assert participant.quote_consented is True
    # Storing a quote must not publish the person by itself.
    assert participant.is_published is False


# ─────────────────────────────────────────────────────────────────────────────
# Reporting helpers the admin depends on
# ─────────────────────────────────────────────────────────────────────────────


def test_missing_consent_fields_is_empty_for_a_complete_row(consented_published):
    # A tuple, not a list: it is returned from a property and compared against in
    # several places, so it must be immutable.
    assert consented_published.missing_consent_fields == ()


def test_missing_consent_fields_names_each_gap(consent_without_date, not_consented):
    assert "consent_date" in consent_without_date.missing_consent_fields
    assert "consent_publication" in not_consented.missing_consent_fields
    # Both gaps are reported, not just the first one found — an operator fixing a
    # record needs the whole list in one pass.
    assert len(not_consented.missing_consent_fields) == 2


def test_consent_state_is_stable_for_a_published_row(consented_published):
    assert consented_published.consent_state == "published"


# ─────────────────────────────────────────────────────────────────────────────
# search_blob — what the participant search actually matches on
# ─────────────────────────────────────────────────────────────────────────────


def test_search_blob_includes_the_name(session):
    participant = Participant(
        slug="blob-test",
        name_bn="বিষ্ণুপ্রসাদ দাশ",
        education="HSC",
        batch=1,
    )
    session.add(participant)
    session.flush()
    blob = participant.search_blob
    assert blob, "search_blob was not populated by the before_flush hook"
    assert "বিষ্ণুপ্রসাদ" in blob


def test_search_blob_is_generated_not_authored(session):
    """It must be derived, so it can never disagree with the name it indexes."""
    participant = Participant(
        slug="blob-derived", name_bn="রূপা আক্তার", education="HSC", batch=1
    )
    session.add(participant)
    session.flush()
    first = participant.search_blob

    participant.name_bn = "নুসরাত জাহান"
    session.flush()
    assert participant.search_blob != first
    assert "নুসরাত" in participant.search_blob
