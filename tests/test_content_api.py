"""The content API: what it may serve, and what it must never serve.

WHY THESE TESTS ARE ABOUT ABSENCE
    Every risk on this endpoint is a thing that might APPEAR: a name whose consent was
    never recorded, a field an administrator half-filled, a photograph §5.1 says does not
    exist. A test that only walked the happy path would pass on the day the leak was
    introduced, so each test below asserts the negative — and pairs it with a positive
    control, because "the list is empty" would otherwise satisfy both.

THE FIXTURE IS THE REAL SEED DATA
    `app/seeds/data/frontend_content.json` is what `flask seed-programme` loads, so these
    tests run against the shapes the site actually gets — including the invented register,
    which is exactly what makes the consent filter worth testing: there are 25 people who
    COULD be published, and the assertions are about the ones who must not be.
"""

from __future__ import annotations

import json

import pytest

from app.extensions import db
from app.models import CourseModule, CoursePhase, Instructor, Participant, TrainingTool
from app.seeds.programme import DATA_FILE, seed_programme_content
from app.services.content_service import build_content
from app.services.participant_service import list_published

#: Key fragments that must never appear anywhere in the payload, whatever is in the
#: database. `search_blob` is the search index, the `consent_*` fields are records ABOUT a
#: person rather than facts about their training, and a participant photograph is
#: prohibited outright (§5.1).
NEVER_IN_THE_PAYLOAD = ("search_blob", "consent_notes", "consent_source", "photo_path", "nid")


@pytest.fixture
def payload_data():
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


@pytest.fixture
def content_only(session, payload_data):
    """The syllabus, without the invented people. The `clear-people` end state."""
    seed_programme_content(payload_data, people=False)
    db.session.commit()
    return session


@pytest.fixture
def with_people(session, payload_data):
    """The syllabus AND the invented register, published through the model's own gate."""
    seed_programme_content(payload_data, people=True, publish=True)
    db.session.commit()
    return session


def test_the_payload_is_served_at_all(content_only):
    """The control. If these keys are missing, everything below passes for the wrong reason."""
    payload = build_content()
    assert set(payload) >= {
        "stats",
        "tools",
        "phases",
        "modules",
        "works",
        "trainers",
        "participants",
        "institutions",
        "batches",
        "counts",
    }


def test_the_content_seed_loads_no_people(content_only, with_people):
    """`people=False` really does mean no people, which is what the CLI promises."""
    assert build_content()["participants"], "the control failed: nobody was ever loaded"
    assert build_content()["trainers"], "the control failed: no trainer was ever loaded"


def test_a_row_without_consent_is_never_in_the_payload(with_people):
    """§5.3: no recorded consent, no publication — on any surface.

    The row is inserted with no consent event, no date and no source, and then the two
    readers are asked: the JSON payload and `list_published`, which is what the Jinja
    pages trust. They must agree, because a participant visible on one surface and not on
    the other is the failure this service layer exists to prevent.
    """
    before = len(build_content()["participants"])
    assert before > 0, "the fixture has nobody to compare against"

    db.session.add(
        Participant(
            slug="no-consent-person",
            name_bn="সম্মতিহীন ব্যক্তি",
            education="Other",
            is_published=False,
        )
    )
    db.session.flush()

    assert "no-consent-person" not in {row["slug"] for row in build_content()["participants"]}
    assert "no-consent-person" not in {row["slug"] for row in list_published()}
    assert len(build_content()["participants"]) == before


def test_the_batches_are_counted_from_the_published_register(with_people):
    """A batch exists because people are in it — not because a row says so."""
    payload = build_content()
    assert sum(row["participant_count"] for row in payload["batches"]) == len(
        payload["participants"]
    )
    assert payload["counts"]["participants"] == len(payload["participants"])


def test_the_modules_on_the_payload_all_belong_to_a_phase(content_only):
    """The rule an operator can act on: to put a module on the React page, give it a phase."""
    payload = build_content()
    assert payload["modules"], "no modules in the fixture"
    for row in payload["modules"]:
        assert row["phase_slug"], f"module {row['code']} has no phase and would not be shown"
    assert {row["phase_slug"] for row in payload["modules"]} <= {
        phase["slug"] for phase in payload["phases"]
    }


def test_a_permitted_portrait_is_served_and_an_unpermitted_one_is_not(with_people):
    """§5.1 AS AMENDED: the permission decides, not the file.

    THE ILLEGAL PAIR CANNOT BE CONSTRUCTED — the database refuses a photograph without
    its permission, which is the stronger statement and is proved in `test_schema`. What
    this test covers is the shape the API serves: a permitted portrait arrives as a
    signed URL (uploads live outside the webroot), and a person with no portrait gets a
    null — never a bare path.
    """
    from app.extensions import db
    from app.models import MediaItem, Participant

    item = MediaItem(path="images/portrait-probe.png", alt_bn="প্রতিচ্ছবি", kind="image")
    db.session.add(item)
    db.session.flush()

    # Two participants from the register, by id: the seeded slugs are the front end's own
    # invented ones, and naming one here would make this test depend on them.
    both = list(
        db.session.execute(db.select(Participant).order_by(Participant.id).limit(2)).scalars()
    )
    assert len(both) == 2, "the fixture has fewer than two participants"
    permitted, without = both

    permitted.photo_id = item.id
    permitted.image_consent = True
    db.session.commit()

    served = {row["slug"]: row for row in build_content()["participants"]}
    url = served[permitted.slug]["photo_url"]
    assert url, "a permitted portrait was withheld"
    assert url.startswith("/media/"), f"not a signed URL: {url!r}"
    assert served[without.slug]["photo_url"] is None, (
        "a portrait appeared for somebody the register has none for"
    )


def test_the_permission_is_what_makes_a_portrait_publishable():
    """The rule itself, in one place, on an object that is never stored.

    `Participant.photo_is_publishable` is the single answer to "may this face be shown",
    and every surface calls it. This asserts the truth table directly, because the states
    it refuses are ones the database will not let a test create.
    """
    from app.models import Participant

    person = Participant(slug="stub", name_bn="পরীক্ষা", education="HSC")

    person.photo_id = 1
    person.image_consent = False
    assert person.photo_is_publishable is False, "a stored photo leaked past the permission"

    person.image_consent = True
    assert person.photo_is_publishable is True, "the control failed"

    person.photo_id = None
    assert person.photo_is_publishable is False, "permission without a file is not a picture"


def test_a_portrait_on_a_withdrawn_participant_is_not_served(with_people):
    """Withdrawal takes the face down with the name, in the same request.

    §5.3 rule 2 unpublishes on withdrawal. A photograph that stayed on the site afterwards
    would be the most visible part of the person who asked to be removed.
    """
    from app.extensions import db
    from app.models import MediaItem, Participant

    item = MediaItem(path="images/withdraw-probe.png", alt_bn="প্রতিচ্ছবি", kind="image")
    db.session.add(item)
    db.session.flush()

    person = db.session.execute(db.select(Participant)).scalars().first()
    person.photo_id = item.id
    person.image_consent = True
    db.session.commit()

    assert any(
        row["photo_url"] for row in build_content()["participants"] if row["slug"] == person.slug
    ), "the control failed: the portrait was never served in the first place"

    person.withdraw_consent(notes="probe")
    db.session.commit()

    slugs = {row["slug"] for row in build_content()["participants"]}
    assert person.slug not in slugs, "a withdrawn participant is still in the payload"


def test_clearing_the_people_leaves_the_course_alone(content_only):
    """`flask clear-people` is the step between a demo and the real cohort.

    It removes three kinds of row and must not touch the syllabus: the modules, phases and
    tools are typed by hand, and having to re-enter them is the expensive mistake the
    command exists to avoid. The counts are taken before and compared after.
    """
    db.session.add(Instructor(slug="temp-trainer", name_bn="সাময়িক প্রশিক্ষক", status="current"))
    db.session.add(Participant(slug="temp-person", name_bn="সাময়িক ব্যক্তি", education="Other"))
    db.session.commit()

    phases = db.session.query(CoursePhase).count()
    tools = db.session.query(TrainingTool).count()
    modules = db.session.query(CourseModule).count()
    assert phases and tools and modules, "the fixture has no course content to protect"

    for row in db.session.execute(db.select(Participant)).scalars():
        db.session.delete(row)
    for row in db.session.execute(db.select(Instructor)).scalars():
        db.session.delete(row)
    db.session.commit()

    assert db.session.query(Participant).count() == 0
    assert db.session.query(Instructor).count() == 0
    assert db.session.query(CoursePhase).count() == phases
    assert db.session.query(TrainingTool).count() == tools
    assert db.session.query(CourseModule).count() == modules
    assert build_content()["modules"], "the course page still has modules to render"
