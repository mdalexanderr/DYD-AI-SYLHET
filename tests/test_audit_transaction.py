"""Audit transaction semantics. execution-plan step 4.7; plan.md §12.1.

4.7's "DONE WHEN", VERBATIM
    "a test asserts that a rolled-back change leaves **no** audit row — otherwise the
    log lies."

    That is the whole point of `app/security/audit.py`, and until now it was a design
    note in a docstring with nothing behind it. The rule is that `audit.record()`
    NEVER commits: the row must be written in the SAME transaction as the change it
    describes, so the log records outcomes rather than attempts. If it committed, it
    would claim changes that never happened, which is worse than having no log at all
    — a log that is sometimes wrong is a log nobody can rely on, and the only
    situation you need it for is the one where being wrong matters most.

WHY THIS IS TESTED BEFORE ANYTHING WRITES TO IT
    4.8 and 4.9 are the first admin mutations, and every one of them will call this
    helper. Establishing the transaction contract first means those screens are
    written against a rule that is already known to hold, rather than the rule being
    inferred afterwards from however they happened to behave.

WHERE THE FUNCTIONALITY LIVES
    In `app/security/audit.py` (Phase 2), not in a new `app/services/audit_service.py`.
    §9.1's tree names the latter for P6/P8, but the module already exists, does the
    job, and is imported by 4.1's login path — creating a second one to satisfy a
    filename would give the project two places that write audit rows, which is exactly
    the drift this module's docstring warns about.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func


def _audit_count() -> int:
    """Read the audit table through a FRESH query.

    Not through the identity map: a rolled-back `record()` leaves a dirty instance in
    the session, and counting rows from the identity map would report it as present
    when the database never saw it.
    """
    from app.extensions import db
    from app.models import AuditLog

    return int(db.session.execute(db.select(func.count(AuditLog.id))).scalar_one())


# ─────────────────────────────────────────────────────────────────────────────
# The contract: one transaction, one outcome
# ─────────────────────────────────────────────────────────────────────────────
def test_a_rolled_back_change_leaves_no_audit_row(app, session):
    """4.7's "Done when". If this fails, the audit log lies."""
    from app.extensions import db
    from app.models import Page
    from app.security import audit

    before = _audit_count()

    page = Page(slug="rollback-probe", title_bn="পরিবর্তনের আগে")
    db.session.add(page)
    db.session.flush()

    snapshot = audit.snapshot(page)
    page.title_bn = "পরিবর্তনের পরে"
    audit.record("page.update", entity=page, before=snapshot, after=audit.snapshot(page))

    # The transaction that would have contained both the change and its audit row.
    db.session.rollback()

    assert _audit_count() == before, (
        "a rolled-back change left an audit row — the log now claims a change that "
        "never happened"
    )
    assert db.session.execute(
        db.select(Page).where(Page.slug == "rollback-probe")
    ).scalars().first() is None, "the page change survived the rollback, so the test proves nothing"


def test_a_committed_change_keeps_exactly_one_audit_row(app, session):
    """The other half: the row must survive when the change does."""
    from app.extensions import db
    from app.models import Page
    from app.security import audit

    before = _audit_count()

    page = Page(slug="commit-probe", title_bn="আগে")
    db.session.add(page)
    db.session.flush()

    snapshot = audit.snapshot(page)
    page.title_bn = "পরে"
    audit.record("page.update", entity=page, before=snapshot, after=audit.snapshot(page))
    db.session.commit()

    assert _audit_count() == before + 1, "a committed change wrote no audit row, or wrote two"

    # Leave the test database as found.
    db.session.delete(page)
    db.session.commit()


def test_record_leaves_the_row_pending_rather_than_persisting_it(app, session):
    """`record()` must not commit — asserted WITHOUT a query.

    The first version of this test counted rows with a `SELECT` and passed for the
    wrong reason in the opposite direction: SQLAlchemy AUTOFLUSHES pending objects
    before executing a query, so the count saw a row that had never been committed and
    the assertion described the flush rather than the commit.

    A pending instance has no primary key. Checking `__new__` and `id is None` asks
    the question directly, and neither touches the database.
    """
    from app.extensions import db
    from app.security import audit

    # BEFORE the row exists. Reading this after `record()` would autoflush the pending
    # row and `before` would already include it — which is exactly how the second
    # version of this test failed, having been written to avoid that same trap.
    before = _audit_count()

    row = audit.record("probe.no_commit", entity_type="Probe", entity_id="1", after={"ok": True})

    assert row in db.session.new, "record() persisted the row instead of leaving it pending"
    assert row.id is None, "the row already has a primary key, so it was flushed or committed"

    db.session.rollback()

    # After the rollback the session is clean, so this count is the database's answer.
    assert _audit_count() == before, "the rolled-back probe row survived"


# ─────────────────────────────────────────────────────────────────────────────
# The snapshot: what must NOT reach the log
# ─────────────────────────────────────────────────────────────────────────────
def test_the_snapshot_excludes_declared_secrets(app, session):
    """The audit log is shown in the admin UI (§6.13).

    A password hash or a TOTP seed surviving into it would be readable by anyone who
    reached the admin — and the TOTP seed is the second factor itself.
    """
    from app.models import AdminUser
    from app.security import audit

    user = AdminUser(
        email="snapshot-probe@example.test",
        password_hash="a-bcrypt-hash-that-must-not-appear",
        full_name_bn="স্ন্যাপশট",
        twofa_secret="a-totp-seed-that-must-not-appear",
    )
    session.add(user)
    session.commit()

    snap = audit.snapshot(user)

    assert snap is not None
    assert "email" in snap, "the snapshot dropped everything, so it proves nothing"
    assert "password_hash" not in snap, "a password hash reached the audit log"
    assert "twofa_secret" not in snap, "a TOTP seed reached the audit log"
    assert "recovery_codes" not in snap


def test_snapshot_of_none_is_none(app):
    """A create has no `before`; a delete has no `after`. Both are legitimate."""
    from app.security import audit

    assert audit.snapshot(None) is None


# ─────────────────────────────────────────────────────────────────────────────
# Use outside a request: the CLI and seeder path
# ─────────────────────────────────────────────────────────────────────────────
def test_record_works_with_no_request_context(app, session):
    """`flask seed` writes before the admin account exists.

    "Who did this" genuinely has no answer there, so the actor is None rather than the
    helper raising — which would make seeding fail on the first install.
    """
    from app.extensions import db
    from app.security import audit

    with app.app_context():
        row = audit.record(
            "cli.probe", entity_type="Probe", entity_id="1", after={"ok": True}
        )

        assert row.actor_id is None
        assert row.ip is None
        assert row.action == "cli.probe"
        db.session.rollback()


def test_record_login_carries_the_address_and_the_reason(app, session):
    """Login rows have no entity — the subject is the account itself."""
    from app.extensions import db
    from app.security import audit

    with app.app_context():
        row = audit.record_login(email="log@example.test", successful=False, reason="bad_password")
        db.session.flush()

        assert row.entity_id == "log@example.test"
        assert row.entity_type == "AdminUser"
        assert row.after_json["successful"] is False
        assert row.after_json["reason"] == "bad_password"

        db.session.rollback()


@pytest.mark.parametrize("successful", [True, False])
def test_both_login_outcomes_are_recorded(app, session, successful):
    """Recording only failures leaves the log unable to answer "was this account
    accessed from an address we do not recognise", which is the question asked."""
    from app.extensions import db
    from app.security import audit

    with app.app_context():
        row = audit.record_login(email="both@example.test", successful=successful)
        db.session.flush()

        assert row.after_json["successful"] is successful
        db.session.rollback()
