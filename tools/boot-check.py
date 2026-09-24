"""Boot the app, build the schema, and prove the two claims that matter most.

This is not a unit test. It is the check the execution plan's step 2.17 asks for:
that the 17 tables exist, that no prohibited PII column exists, and that the
database itself refuses to publish a participant who has not consented.

Run:  python tools/boot-check.py
Exit: 0 = everything held, 1 = something did not.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Windows consoles default to cp1252 and this script prints Bangla. Same fix as
# tools/check-css.py: reconfigure stdout rather than hoping PYTHONIOENCODING is set,
# because the failure mode is a UnicodeEncodeError raised from inside a *passing*
# check, which reads as a broken app rather than a broken console.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []
NOTES: list[str] = []


def ok(msg: str) -> None:
    print(f"  OK    {msg}")


def bad(msg: str) -> None:
    FAILURES.append(msg)
    print(f"  FAIL  {msg}")


def note(msg: str) -> None:
    NOTES.append(msg)
    print(f"  note  {msg}")


def main() -> int:
    print()
    print("═══ 1. import and create_app ═══")
    try:
        from app import create_app
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  cannot import app: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return 1

    try:
        app = create_app("development")
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  create_app('development') raised: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    ok(f"create_app() succeeded — APP_ENV={app.config.get('APP_ENV')!r}")

    uri = app.config.get("SQLALCHEMY_DATABASE_URL") or app.config.get("SQLALCHEMY_DATABASE_URI")
    print(f"        DATABASE_URL = {uri}")

    print()
    print("═══ 2. models registered ═══")
    from app.extensions import db
    from app.models import EXPECTED_TABLES, PROHIBITED_PARTICIPANT_COLUMNS

    with app.app_context():
        metadata = set(db.metadata.tables)
        print(f"        db.metadata holds {len(metadata)} tables")
        for name in sorted(metadata):
            print(f"          · {name}")

        missing = EXPECTED_TABLES - metadata
        extra = metadata - EXPECTED_TABLES
        if missing:
            bad(f"models not registered: {sorted(missing)}")
        else:
            ok(f"all {len(EXPECTED_TABLES)} expected tables are declared")
        if extra:
            bad(f"tables declared but not in EXPECTED_TABLES: {sorted(extra)} — "
                "EXPECTED_TABLES is the §10.3 inventory; either add it there or remove the model")

        print()
        print("═══ 3. create_all ═══")
        try:
            db.create_all()
            ok("db.create_all() succeeded")
        except Exception as exc:  # noqa: BLE001
            bad(f"db.create_all() raised: {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()
            return 1

        from sqlalchemy import inspect as sa_inspect

        actual = set(sa_inspect(db.engine).get_table_names())
        print(f"        database now holds {len(actual)} tables")

        print()
        print("═══ 4. prohibited PII columns ═══")
        if "participants" in actual:
            cols = {c["name"] for c in sa_inspect(db.engine).get_columns("participants")}
            print(f"        participants has {len(cols)} columns:")
            print(f"          {', '.join(sorted(cols))}")
            leaked = cols & PROHIBITED_PARTICIPANT_COLUMNS
            if leaked:
                bad(f"PARTICIPANTS CONTAINS PROHIBITED COLUMNS: {sorted(leaked)}")
            else:
                ok("no prohibited PII column is present (S2/S3 held)")
        else:
            bad("participants table was not created")

        print()
        print("═══ 5. the publish guard ═══")
        from sqlalchemy import text

        ddl = ""
        rows = db.session.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='participants'")
        ).fetchall()
        ddl = "\n".join(str(r[0]) for r in rows if r[0])
        if "ck_participants_publish_requires_consent" in ddl:
            ok("CHECK constraint is present in the DDL")
        else:
            bad("CHECK constraint is ABSENT from the DDL")

        # ── Schema-driven probes ─────────────────────────────────────────────
        # The first version of this block hard-coded its column list, and was wrong
        # three times in a row: each probe hit a different NOT NULL column before it
        # ever reached the constraint it was meant to test. A probe that fails for
        # the wrong reason reports a guard as WORKING when the guard was never
        # evaluated — the most dangerous kind of green test, because it is green.
        #
        # So the row is built from the model. Every NOT NULL column that nothing
        # else supplies is filled in automatically, and only the columns under test
        # are named explicitly. Adding a NOT NULL column later cannot quietly turn
        # one of these probes into a no-op.
        from sqlalchemy import Boolean, Date, DateTime, Integer, SmallInteger

        from app.models import Participant

        table = Participant.__table__

        def _probe(**overrides) -> tuple[bool, str]:
            """INSERT one participant row. Returns (accepted, error_description)."""
            values = {}
            for column in table.columns:
                if column.name in overrides:
                    values[column.name] = overrides[column.name]
                elif (
                    column.primary_key
                    # ONLY server_default counts here. A Python-side `default=`
                    # supplies a value on the ORM path, while compiling the INSERT
                    # — it never reaches the database, so raw SQL must still
                    # provide the column. Treating the two as equivalent is what
                    # made an earlier version of this probe fail on NOT NULL and
                    # look like a working guard.
                    or column.nullable
                    or column.server_default is not None
                ):
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
            # S608 is a false positive here: the column list is built from
            # Participant.__table__ metadata and the values are bound parameters.
            # No user input appears anywhere in this statement.
            sql = f"INSERT INTO participants ({columns}) VALUES ({placeholders})"  # noqa: S608
            try:
                db.session.execute(text(sql), values)
            except Exception as exc:  # noqa: BLE001 — a refusal is the expected result
                db.session.rollback()
                # The driver's own message, not just the exception class: "which
                # constraint refused this" is the entire diagnostic value here.
                text_out = str(exc).strip()
                first = text_out.splitlines()[0] if text_out else ""
                return False, f"{type(exc).__name__}: {first}"
            db.session.rollback()
            return True, ""

        # CONTROL FIRST. A row that satisfies every rule must be ACCEPTED. Without
        # this control, all the refusals below would also "pass" against a table
        # that rejects every insert for some unrelated reason, and the whole section
        # would be worthless while looking thorough.
        accepted, err = _probe(
            slug="__probe_control__", name_bn="পরীক্ষা",
            is_published=1, consent_publication=1, consent_date="2026-03-01",
            education="HSC",
        )
        if accepted:
            ok("control: a fully consented, consented-dated publish is ACCEPTED "
               "— the guard is not over-blocking")
        else:
            bad(f"CONTROL FAILED — a legitimate publish was refused ({err}). "
                "Every result below is meaningless until this passes.")

        accepted, err = _probe(
            slug="__probe_unconsented__", name_bn="পরীক্ষা",
            is_published=1, consent_publication=0, education="HSC",
        )
        if accepted:
            bad("the DATABASE ACCEPTED is_published=1 with consent_publication=0 — "
                "the guard is not working at the database layer")
        else:
            ok(f"the database REFUSED an unconsented publish ({err}) — R4 holds at layer 3")

        accepted, err = _probe(
            slug="__probe_nodate__", name_bn="পরীক্ষা",
            is_published=1, consent_publication=1, consent_date=None, education="HSC",
        )
        if accepted:
            bad("consent_publication=1 with a NULL consent_date was ACCEPTED — "
                "§5.3 rule 3 requires a date")
        else:
            ok(f"consent_publication=1 with a NULL consent_date is refused ({err})")

        accepted, err = _probe(
            slug="__probe_quote__", name_bn="পরীক্ষা",
            quote_bn="<p>উদ্ধৃতি</p>", quote_consented=0, education="HSC",
        )
        if accepted:
            bad("a quote was accepted with quote_consented=0 — §5.3 rule 5 requires "
                "a separate permission")
        else:
            ok(f"a quote without quote_consented is refused ({err})")

        accepted, err = _probe(
            slug="__probe_quote_ok__", name_bn="পরীক্ষা",
            quote_bn="<p>উদ্ধৃতি</p>", quote_consented=1, education="HSC",
        )
        if accepted:
            ok("a quote WITH quote_consented is accepted — rule 5 is not over-blocking")
        else:
            bad(f"a properly consented quote was refused ({err}) — rule 5 is too strict")

        print()
        print("═══ 6. routes ═══")
        rules = sorted(
            (str(r.rule), ",".join(sorted(r.methods - {"HEAD", "OPTIONS"})))
            for r in app.url_map.iter_rules()
        )
        print(f"        {len(rules)} rules registered")
        for rule, methods in rules:
            print(f"          {rule:<34} {methods}")

        admin_prefix = app.config.get("ADMIN_URL_PREFIX") or ""
        if admin_prefix and admin_prefix != "/admin":
            plain = [r for r, _ in rules if r.startswith("/admin")]
            if plain:
                bad(f"S13 violated: /admin routes exist: {plain}")
            else:
                ok(f"no route under /admin; the admin lives at {admin_prefix} (S13)")

        print()
        print("═══ 7. the before_flush guard (layer 2) ═══")

        from app.models import Participant

        p = Participant(
            slug="__model_probe__",
            name_bn="পরীক্ষা",
            consent_publication=False,
            consent_date=None,
        )
        p.is_published = True
        try:
            db.session.add(p)
            db.session.flush()
            db.session.rollback()
            bad("the MODEL allowed is_published=True with no consent — "
                "the before_flush guard is not firing")
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            ok(f"the model refused it too ({type(exc).__name__}) — R4 holds at layer 2")

        from app.constants import Education

        # education is NOT NULL by design (§10.3): a participant row without an
        # education level is a row the Course page cannot render honestly. The
        # probe must satisfy every NOT NULL column or it tests the wrong thing.
        p2 = Participant(
            slug="__model_probe2__",
            name_bn="রূপা আক্তার",
            education=next(iter(Education)),
        )
        db.session.add(p2)
        db.session.flush()
        blob = p2.search_blob
        db.session.rollback()
        if blob and "রূপা" in blob:
            ok(f"search_blob is maintained by the hook ({blob!r})")
        else:
            bad(f"search_blob was not populated (got {blob!r})")

        print()
        print("═══ 8. seeding ═══")
        try:
            from app.seeds import seed_reference_data

            counts = seed_reference_data()
            ok(f"seed pass 1: {counts}")
            counts2 = seed_reference_data()
            if counts2 == counts:
                ok("seed pass 2 is identical — the seeder is idempotent")
            else:
                bad(f"second seed pass differed: {counts} vs {counts2}")
        except Exception as exc:  # noqa: BLE001
            bad(f"seeding raised: {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()

        print()
        print("═══ 9. section payloads validate against the registry ═══")
        try:
            from sqlalchemy import select as sa_select

            from app.models import PageSection
            from app.sections.registry import validate_section

            all_sections = db.session.execute(sa_select(PageSection)).scalars().all()
            print(f"        validating {len(all_sections)} seeded sections")
            bad_count = 0
            for section in all_sections:
                valid, reason = validate_section(section.type, section.content or {})
                if not valid:
                    bad_count += 1
                    bad(f"section #{section.id} type={section.type} page_id={section.page_id}: {reason}")
            if bad_count == 0:
                ok(f"all {len(all_sections)} seeded sections pass their schema")
        except Exception as exc:  # noqa: BLE001
            bad(f"section validation raised: {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()

    print()
    print("═══ 10. rendering (step 2.5: /health 200, unknown URL renders Bangla 404) ═══")
    client = app.test_client()

    # /health must answer without a template and without a login.
    try:
        response = client.get("/health")
        payload = response.get_json(silent=True)
        if response.status_code == 200 and isinstance(payload, dict):
            ok(f"/health -> 200 {payload}")
        elif response.status_code == 200:
            bad(f"/health returned 200 but not JSON: {response.data[:120]!r}")
        else:
            bad(f"/health returned {response.status_code}")
    except Exception as exc:  # noqa: BLE001
        bad(f"/health raised: {type(exc).__name__}: {exc}")

    # The Bangla 404 is the most-seen page after the homepage. Assert the STATUS and
    # that real Bangla prose rendered, not just that something came back — a
    # plain-text fallback also returns 404 and would look like a pass.
    try:
        response = client.get("/this-page-does-not-exist-9f3a")
        body = response.get_data(as_text=True)
        if response.status_code != 404:
            bad(f"unknown URL returned {response.status_code}, expected 404")
        elif "খুঁজে পাওয়া যায়নি" not in body:
            bad("unknown URL returned 404 but did NOT render the Bangla 404 page "
                f"(first 160 chars: {body[:160]!r})")
        elif "<html" not in body.lower():
            bad("the 404 body is not an HTML document — the layout did not render")
        else:
            ok(f"unknown URL -> 404, Bangla page rendered ({len(body):,} bytes)")

        # The layout must have drawn its chrome, or the page is only half a page.
        for marker_name, marker in (
            ("skip link", 'href="#main"'),
            ("site header", "<header"),
            ("main landmark", 'id="main"'),
            ("site footer", "<footer"),
            ("stylesheet", "css/app.css"),
        ):
            if marker in body:
                ok(f"404 page includes the {marker_name}")
            else:
                bad(f"404 page is MISSING the {marker_name} ({marker!r})")

        # Nothing in the error path may leak internals (§17.6).
        leaked = [
            token for token in
            ("Traceback", "sqlalchemy", "sqlite3", "/site-packages/", "SECRET_KEY")
            if token in body
        ]
        if leaked:
            bad(f"the 404 page leaks internals: {leaked}")
        else:
            ok("the 404 page leaks no traceback, driver name or path")
    except Exception as exc:  # noqa: BLE001
        bad(f"404 rendering raised: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()

    # S13: /admin is a 404, not a login page. A login page at /admin confirms the
    # admin exists and gives an attacker the form to attack.
    try:
        response = client.get("/admin")
        if response.status_code == 404:
            ok("/admin -> 404 (S13 holds)")
        else:
            bad(f"/admin returned {response.status_code}; S13 requires 404")
    except Exception as exc:  # noqa: BLE001
        bad(f"/admin raised: {type(exc).__name__}: {exc}")

    print()
    print("═══ 11. demo fixtures produce every consent state (step 2.15) ═══")
    with app.app_context():
        try:
            from sqlalchemy import func, or_, select

            from app.extensions import db
            from app.models import Participant
            from app.seeds import seed_demo_participants

            created = seed_demo_participants(count=60)
            ok(f"seed_demo_participants -> {created}")

            def count_where(*conditions) -> int:
                return db.session.execute(
                    select(func.count(Participant.id)).where(*conditions)
                ).scalar_one()

            # §8.2: every one of these must exist, because the consent rules cannot
            # be verified against happy-path rows. A missing state is a rule that
            # will not be exercised until a real person is affected by it.
            states = {
                "published (consented AND dated)": count_where(
                    Participant.is_published.is_(True)
                ),
                "consented but NOT published": count_where(
                    Participant.consent_publication.is_(True),
                    Participant.is_published.is_(False),
                ),
                "consenting with NO date": count_where(
                    Participant.consent_publication.is_(True),
                    Participant.consent_date.is_(None),
                ),
                "never consented": count_where(
                    Participant.consent_publication.is_(False)
                ),
                "consent WITHDRAWN": count_where(
                    Participant.consent_withdrawn_at.is_not(None)
                ),
                "no outcome recorded (zero-outcome)": count_where(
                    Participant.outcome_type.is_(None)
                ),
            }
            for label, value in states.items():
                if value:
                    ok(f"{label}: {value}")
                else:
                    bad(f"NO record in state: {label} — §8.2 requires this state to exist")

            # THE INVARIANT, checked across the WHOLE table rather than per-row.
            # This is the assertion the entire project exists to satisfy: not one
            # published participant anywhere lacks consent or a consent date.
            illegal = count_where(
                Participant.is_published.is_(True),
                or_(
                    Participant.consent_publication.is_(False),
                    Participant.consent_date.is_(None),
                ),
            )
            if illegal:
                bad(f"{illegal} PUBLISHED participant(s) lack consent — R4 is BROKEN")
            else:
                ok("no published participant anywhere lacks consent (R4 holds table-wide)")

            # §6.5 / S6: a bucket small enough to require suppression.
            small = count_where(
                Participant.outcome_type == "teaching",
                Participant.is_published.is_(True),
            )
            if 0 < small < 5:
                ok(f"a {small}-person outcome bucket exists, so the <5 rule is testable")
            else:
                note(f"the small-outcome bucket holds {small} published rows (expected 1-4)")
        except Exception as exc:  # noqa: BLE001
            bad(f"demo seeding raised: {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()

    print()
    print("═══ RESULT ═══")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAIL  {f}")
        print(f"\n  {len(FAILURES)} failure(s)\n")
        return 1
    print("  everything held\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
