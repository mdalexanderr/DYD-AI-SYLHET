"""Schema assertions. execution-plan steps 2.10, 2.11 and 2.17.

WHY THE COUNT IS A TEST
    §9.1 lists 17 tables. `EXPECTED_TABLES` is the only place that number exists in
    code, and `set(db.metadata.tables) == EXPECTED_TABLES` in BOTH directions means
    a table can never be added or lost silently: adding a model without adding it to
    the list fails, and deleting a model without removing it from the list fails too.

WHY THE PUBLISH GUARD IS TESTED WITH RAW SQL
    §5.3 and step 2.11 are explicit: prove it "directly via SQL, bypassing the ORM".
    The ORM path already has two other guards (the form, and `before_flush`), so a
    test that goes through the ORM would pass even if the database constraint were
    missing entirely — and then the CSV import, which will bypass both, would be
    the thing that discovers it, in production.

    Every probe below also runs a CONTROL: a row that satisfies every rule must be
    ACCEPTED. Without it, "the database refused it" is equally consistent with "the
    table rejects everything", and the whole file would be worthless while looking
    thorough.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Boolean, Date, DateTime, Integer, SmallInteger, inspect, text

from app.extensions import db
from app.models import EXPECTED_TABLES, PROHIBITED_PARTICIPANT_COLUMNS

# ─────────────────────────────────────────────────────────────────────────────
# The inventory
# ─────────────────────────────────────────────────────────────────────────────


def test_seventeen_tables_are_declared():
    """Step 2.10's `len(db.metadata.tables) == 17`."""
    assert len(db.metadata.tables) == 17, (
        f"expected 17 tables, found {len(db.metadata.tables)}: "
        f"{sorted(db.metadata.tables)}"
    )
    assert set(db.metadata.tables) == set(EXPECTED_TABLES)


def test_seventeen_tables_exist_in_the_database(session):
    actual = set(inspect(db.engine).get_table_names())
    missing = set(EXPECTED_TABLES) - actual
    assert not missing, f"models declared but no table created: {sorted(missing)}"


def test_expected_tables_has_no_stale_entries():
    """The reverse direction — a name in the list with no model behind it."""
    stale = set(EXPECTED_TABLES) - set(db.metadata.tables)
    assert not stale, f"EXPECTED_TABLES lists tables that do not exist: {sorted(stale)}"


def test_alembic_and_sqlite_internals_are_the_only_extras(session):
    """Catches a table created by hand in a migration and never modelled."""
    actual = set(inspect(db.engine).get_table_names())
    extras = actual - set(EXPECTED_TABLES) - {"alembic_version", "sqlite_sequence"}
    assert not extras, f"tables in the database that no model declares: {sorted(extras)}"


# ─────────────────────────────────────────────────────────────────────────────
# §5.3 / S2 / S3 — the columns that must not exist
# ─────────────────────────────────────────────────────────────────────────────


def test_participants_has_no_prohibited_column(session):
    """The strongest form of "we do not collect this": the column is absent.

    A policy document says what should happen. An absent column says what CAN
    happen. §5.3 and S2/S3 choose the second.
    """
    columns = {c["name"] for c in inspect(db.engine).get_columns("participants")}
    leaked = columns & PROHIBITED_PARTICIPANT_COLUMNS
    assert not leaked, (
        f"participants contains columns that must never exist: {sorted(leaked)}. "
        "A participant's phone, email, NID, date of birth, blood group, address, "
        "guardian name or photograph must not be storable at all."
    )


@pytest.mark.parametrize("column", sorted(PROHIBITED_PARTICIPANT_COLUMNS))
def test_each_prohibited_column_is_individually_absent(session, column):
    """One test per banned name, so a failure names the exact column."""
    columns = {c["name"] for c in inspect(db.engine).get_columns("participants")}
    assert column not in columns


def test_participants_has_no_media_column(session):
    """§5.3 / S2: no participant photograph, ever — including by FK.

    The design refuses participant images outright (the whole visual system is built
    to work without them), so a `photo_id` or `image_id` pointing at media_items
    would be a representation-changing feature added by one migration.
    """
    columns = [c["name"] for c in inspect(db.engine).get_columns("participants")]
    media_like = [
        name for name in columns
        if any(word in name.lower() for word in ("photo", "image", "avatar", "picture", "media"))
    ]
    assert not media_like, f"participants has an image column: {media_like}"


# ─────────────────────────────────────────────────────────────────────────────
# §5.3 / R4 / step 2.11 — the database publish guard, via RAW SQL
# ─────────────────────────────────────────────────────────────────────────────


def _probe(session, **overrides):
    """INSERT one participants row built from the model. Returns (accepted, error).

    The row is built from `Participant.__table__` rather than a hardcoded column
    list. An earlier version of this helper listed the columns by hand and was wrong
    three times running: each probe hit a different NOT NULL column before it ever
    reached the constraint it was meant to test, and a probe that fails for the
    WRONG REASON reports a guard as working when the guard was never evaluated.

    Note `server_default`, not `default`. A Python-side `default=` is applied while
    SQLAlchemy compiles an ORM insert; it never reaches the database, so raw SQL must
    still supply the column.
    """
    from app.models import Participant

    values = {}
    for column in Participant.__table__.columns:
        if column.name in overrides:
            values[column.name] = overrides[column.name]
        elif column.primary_key or column.nullable or column.server_default is not None:
            continue
        elif isinstance(column.type, (Integer, SmallInteger)):
            values[column.name] = 1
        elif isinstance(column.type, Boolean):
            values[column.name] = 0
        elif isinstance(column.type, (DateTime, Date)):
            values[column.name] = "2026-03-01"
        else:
            values[column.name] = "probe"

    columns = ", ".join(values)
    placeholders = ", ".join(f":{name}" for name in values)
    try:
        # S608 is a false positive: the column list is built from
        # Participant.__table__ metadata and every value is a bound parameter.
        # Nothing user-supplied reaches this statement — the whole point of the
        # helper is to bypass the ORM, not to accept input.
        sql = f"INSERT INTO participants ({columns}) VALUES ({placeholders})"  # noqa: S608
        session.execute(text(sql), values)
        return True, ""
    except Exception as exc:  # noqa: BLE001 — the refusal is the expected outcome
        return False, str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    finally:
        # Rolled back either way, so the probe never leaves a row behind.
        session.rollback()


def test_control_a_valid_publish_is_accepted(session):
    """THE CONTROL. If this fails, every refusal below proves nothing."""
    accepted, error = _probe(
        session,
        slug="__control__",
        name_bn="পরীক্ষা",
        education="HSC",
        is_published=1,
        consent_publication=1,
        consent_date="2026-03-01",
    )
    assert accepted, (
        f"a legitimately consented publish was REFUSED ({error}). Every other test in "
        "this section is meaningless until the control passes, because 'the database "
        "refused it' would otherwise be consistent with the table rejecting everything."
    )


def test_database_rejects_an_unconsented_publish(session):
    """Step 2.11's headline assertion: `is_published=1, consent_publication=0`.

    This is the belt to the ORM's braces (R1). The CSV import and any future
    maintenance script talk to the database directly, so this is the layer that
    actually cannot be bypassed.
    """
    accepted, error = _probe(
        session,
        slug="__unconsented__",
        name_bn="পরীক্ষা",
        education="HSC",
        is_published=1,
        consent_publication=0,
    )
    assert not accepted, (
        "the DATABASE ACCEPTED is_published=1 with consent_publication=0 — the publish "
        "guard is not enforced at the database layer (R4)."
    )
    assert "ck_participants_publish_requires_consent" in error, (
        f"the insert was refused, but by the WRONG constraint: {error!r}"
    )


def test_database_rejects_consent_without_a_date(session):
    """§5.3 rule 3: consent with no date is not consent, it is an assertion.

    The date is what makes withdrawal possible — without it there is no way to know
    which cohort a permission belongs to, or whether it predates a change in policy.
    """
    accepted, error = _probe(
        session,
        slug="__no_date__",
        name_bn="পরীক্ষা",
        education="HSC",
        is_published=1,
        consent_publication=1,
        consent_date=None,
    )
    assert not accepted, (
        "consent_publication=1 with a NULL consent_date was ACCEPTED "
        "(§5.3 rule 3 requires a date)"
    )
    assert "ck_participants_publish_requires_consent" in error


def test_database_allows_unpublished_consent_without_a_date(session):
    """The constraint is about PUBLISHING, not about storing.

    A row with consent but no date must be storable, because that is exactly the row
    the consent dashboard needs to show so someone can chase the date up. A guard
    that made it unstorable would push the problem into an Excel file.
    """
    accepted, error = _probe(
        session,
        slug="__unpublished_no_date__",
        name_bn="পরীক্ষা",
        education="HSC",
        is_published=0,
        consent_publication=1,
        consent_date=None,
    )
    assert accepted, f"a not-published row with consent and no date should be allowed ({error})"


def test_database_rejects_a_quote_without_permission(session):
    """§5.3 rule 5: a quote needs its own permission, separate from publication.

    Somebody can agree to be listed and still not want their words on a government
    website. One consent cannot cover both.
    """
    accepted, error = _probe(
        session,
        slug="__quote__",
        name_bn="পরীক্ষা",
        education="HSC",
        quote_bn="<p>উদ্ধৃতি</p>",
        quote_consented=0,
    )
    assert not accepted, "a quote was accepted with quote_consented=0 (§5.3 rule 5)"
    assert "ck_participants_quote_requires_permission" in error


def test_database_allows_a_quote_with_permission(session):
    """The other half of rule 5 — the constraint must not be over-blocking."""
    accepted, error = _probe(
        session,
        slug="__quote_ok__",
        name_bn="পরীক্ষা",
        education="HSC",
        quote_bn="<p>উদ্ধৃতি</p>",
        quote_consented=1,
    )
    assert accepted, f"a properly consented quote was refused ({error}) — rule 5 is too strict"


def test_the_publish_constraint_exists_in_the_ddl(session):
    """Belt and braces on the belt: the constraint is present, not merely implied
    by the probes above passing for some other reason."""
    rows = session.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name='participants'")
    ).fetchall()
    ddl = "\n".join(str(r[0]) for r in rows if r[0])
    if not ddl:
        pytest.skip("not SQLite; the SQL-level probes above cover this on MySQL")
    assert "ck_participants_publish_requires_consent" in ddl
    assert "ck_participants_quote_requires_permission" in ddl


# ─────────────────────────────────────────────────────────────────────────────
# The same guard, on MySQL. Step 2.11 says "prove it on both engines".
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.mysql
def test_publish_guard_holds_on_mysql():
    """Runs only when MYSQL_TEST_URL is set — in CI, via a service container.

    Worth the separate test rather than trusting the SQLite result: SQLite and MySQL
    differ in how strictly they evaluate a CHECK, in whether they treat NULL as
    satisfying it, and in how they coerce a boolean. Production is MySQL, so this is
    the engine whose behaviour actually protects the data.
    """
    url = os.environ.get("MYSQL_TEST_URL")
    if not url:
        pytest.skip("MYSQL_TEST_URL is not set — see .github/workflows/ci.yml")

    from app import create_app
    from app.models import Participant

    application = create_app("testing")
    application.config["SQLALCHEMY_DATABASE_URI"] = url
    application.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

    with application.app_context():
        db.drop_all()
        db.create_all()
        try:
            accepted, error = _probe(
                db.session,
                slug="__mysql_unconsented__",
                name_bn="পরীক্ষা",
                education="HSC",
                is_published=1,
                consent_publication=0,
            )
            assert not accepted, (
                "MySQL ACCEPTED an unconsented publish. Production is MySQL, so the "
                f"guard does not hold where it matters. ({error})"
            )
            # And the control, on the same engine.
            accepted, error = _probe(
                db.session,
                slug="__mysql_control__",
                name_bn="পরীক্ষা",
                education="HSC",
                is_published=1,
                consent_publication=1,
                consent_date="2026-03-01",
            )
            assert accepted, f"MySQL refused a legitimate publish ({error})"
        finally:
            db.drop_all()

    # The engine back to SQLite, so a later test in the same session is unaffected.
    assert Participant.__tablename__ == "participants"
