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


# ─────────────────────────────────────────────────────────────────────────────
# The snapshot must fit in the column
# ─────────────────────────────────────────────────────────────────────────────


def _sample_value(column):
    """A plausible value for a column, chosen by its TYPE rather than by its name.

    Why by type: the failure this guards against was a `datetime.date` reaching a JSON
    column, and every `Date` column in the schema has the same problem — `consent_date`,
    a course's start and end. A test that filled in one named column would have to be
    extended every time somebody adds a date, which is the definition of a test that gets
    skipped instead of updated.
    """
    from datetime import UTC, date, datetime
    from decimal import Decimal
    from enum import Enum as PyEnum

    from sqlalchemy import JSON, Boolean, Date, DateTime, Integer, Numeric

    column_type = column.type

    # Order matters: `Boolean` and `DateTime` are checked before the types they subclass.
    if isinstance(column_type, DateTime):
        return datetime(2026, 1, 15, 9, 30, tzinfo=UTC)
    if isinstance(column_type, Date):
        return date(2026, 1, 15)
    if isinstance(column_type, Boolean):
        return True
    if isinstance(column_type, Integer):
        return 7
    if isinstance(column_type, Numeric):
        return Decimal("1.50")
    if isinstance(column_type, JSON):
        return {"nested": [1, "two"]}
    enum_class = getattr(column_type, "enum_class", None)
    if isinstance(enum_class, type) and issubclass(enum_class, PyEnum):
        return next(iter(enum_class))
    return "x"


def test_every_model_snapshot_is_json_serialisable(app, session):
    """Every column of every model, filled and snapshotted, must survive `json.dumps`.

    THIS IS THE REGRESSION TEST FOR A 500 ON THE CONSENT SCREEN. `ModelMixin.to_dict`
    converted `datetime` and enums but not `date`, so recording consent WITH A DATE wrote
    a snapshot containing a `datetime.date`, and SQLAlchemy raised
    `Object of type date is not JSON serializable` at COMMIT. The operator saw a 500 on a
    form that looked correct, and the consent record was lost.

    It walks the whole schema rather than the one model that broke, because the same
    mistake can be made again by adding a `Date`, `Numeric` or `JSON` column anywhere —
    and the audit write is on the path of nearly every screen in the panel.
    """
    import json

    from app.extensions import db

    failures: list[str] = []
    checked = 0

    for mapper in db.Model.registry.mappers:
        model = mapper.class_
        # Some tables are on the bare declarative Base — `consent_events`, `audit_logs`,
        # `login_attempts`. They are append-only records that are never the SUBJECT of a
        # snapshot (you do not audit an audit row), and `audit.snapshot` returns None for
        # them by design. The walk skips exactly those, and `checked` below proves it did
        # not quietly skip everything.
        if not hasattr(model, "to_dict"):
            continue
        instance = model()
        for column in model.__table__.columns:
            try:
                setattr(instance, column.name, _sample_value(column))
            except Exception:  # noqa: BLE001 — a column that refuses the sample still
                continue  # gets snapshotted as None, which is also worth covering.
        try:
            json.dumps(instance.to_dict())
            checked += 1
        except (TypeError, ValueError) as error:
            failures.append(f"{model.__name__}: {error}")

    assert checked > 15, f"only {checked} models were covered — the walk is not working"
    assert not failures, "a snapshot cannot be stored in the audit log: " + "; ".join(failures)


def test_a_snapshot_renders_a_date_as_a_string(app, session):
    """The specific value, read back the way the admin's audit screen reads it."""
    from datetime import date

    from app.models import Participant

    row = Participant(slug="snap", name_bn="নাম", education="Other")
    row.consent_date = date(2026, 1, 15)

    snapshot = row.to_dict()
    assert snapshot["consent_date"] == "2026-01-15"
    assert isinstance(snapshot["consent_date"], str)
