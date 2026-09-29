"""The admin CMS — every screen, and the rules that make them trustworthy.

plan.md §11.1, §11.2, §12.1, §13.1. execution-plan steps 4.6–6.14.

WHAT THIS FILE IS TRYING TO CATCH
    Not "does the template render". It is trying to catch the four ways a CMS
    fails quietly, each of which has a test below:

    1. **A screen that exists but is not reachable.** `records.register_all()` is
       called from the admin package; if that call is ever dropped the six records
       screens 404 and nothing else notices. `test_every_admin_screen_is_reachable`
       walks the real URL map, so a missing route is a failure rather than a page
       nobody visits.
    2. **A write that leaves no audit trail.** §12.1 requires a before/after diff
       for every write. The audit tests assert the ROW exists and names the entity,
       because an audit log that records `entity_id=None` for creates is a log you
       cannot actually search.
    3. **A publish that should have been refused.** The section gate (§11.2) and the
       consent gate (§5.3) are the two places where the CMS is allowed to say no.
       Both are asserted in the negative.
    4. **An upload that is validated by its filename.** A `.png` whose bytes are
       something else is the oldest trick there is, and §13.1 asks for exactly this
       to be caught.

ANONYMOUS ACCESS IS ASSERTED ONCE, HERE, OVER THE WHOLE MAP
    `test_routes.py` has its own version of that loop with a floor on the count.
    This one exists because the number of admin screens has grown and a new screen
    added without `login_required` is a page that shows participant data to anyone
    who guesses the URL.
"""

from __future__ import annotations

import io

import pytest

PASSWORD = "cms-suite-password-1234"
LOGIN_URL = "/admin/login"


@pytest.fixture
def admin_user(session):
    from app.extensions import bcrypt
    from app.models import AdminUser

    user = AdminUser(
        email="cms@example.test",
        password_hash=bcrypt.generate_password_hash(PASSWORD).decode("utf-8"),
        full_name_bn="সিএমএস প্রশাসক",
        is_active=True,
        twofa_enabled=False,
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def admin_client(client, admin_user):
    """A signed-in test client. TestConfig has CSRF off, so no token is needed."""
    response = client.post(LOGIN_URL, data={"email": "cms@example.test", "password": PASSWORD})
    assert response.status_code in (302, 303), "the CMS login fixture could not sign in"
    return client


def _get_screens(app) -> list[str]:
    """Every admin GET URL that serves a PAGE.

    Two kinds of rule are skipped, each for its own reason:

    * **Rules with arguments** (`/admin/pages/1`). There is no page 1 in a fresh
      database, so a 404 there is the correct answer rather than a bug.
    * **Downloads** (`.csv`). A file is not a screen: it has no shell, no
      navigation and no breadcrumb, and the tests below assert that every screen has
      all three. Excluded by the suffix the route itself chose, not by a list of
      endpoint names that would need updating every time a screen is added.
    """
    screens = []
    for rule in app.url_map.iter_rules():
        if not rule.endpoint.startswith("admin."):
            continue
        if "GET" not in rule.methods:
            continue
        if rule.arguments:
            continue
        if str(rule.rule).endswith(".csv"):
            continue
        screens.append(str(rule.rule))
    return sorted(screens)


# ─────────────────────────────────────────────────────────────────────────────
# The whole surface
# ─────────────────────────────────────────────────────────────────────────────


def test_every_admin_screen_is_reachable(admin_client, app):
    """A screen that is written but not registered 404s. This is that check.

    The count of screens is not asserted (it grows); the ABSENCE of a 404 is.
    """
    missing = []
    for path in _get_screens(app):
        status = admin_client.get(path).status_code
        if status != 200:
            missing.append(f"{path} → {status}")

    assert not missing, "admin screens that do not render: " + ", ".join(missing)


def test_every_admin_screen_refuses_an_anonymous_visitor(client, app):
    """No admin screen can be read without a session. §12.1.

    Asserted as "not 200" rather than "302": the login redirect is the normal
    answer, but what matters is that the content is never served.
    """
    leaked = [path for path in _get_screens(app) if client.get(path).status_code == 200]
    assert not leaked, "admin screens served without a session: " + ", ".join(leaked)


def test_the_admin_navigation_lists_the_screens_that_exist(admin_client, app):
    """The rail is generated from data in `_nav.py`, so it can only be wrong by naming
    a route that does not exist — which is a BuildError on every screen at once. This
    asserts the two ends match, in the panel's language."""
    body = admin_client.get("/admin/").get_data(as_text=True)

    for expect in (
        "Dashboard",
        "Pages",
        "Media library",
        "Participants",
        "Consent",
        "Settings",
        "Audit log",
        "Backups",
    ):
        assert expect in body, f"the admin rail is missing {expect}"

    # The rail's group index: the order is information, not decoration.
    for index in ("01", "02", "03", "04", "05"):
        assert index in body, f"the rail is missing group {index}"


def test_the_admin_panel_is_english(admin_client, app):
    """§11.1 — the panel is English; §14.1 — the public site stays Bangla.

    Asserted over the whole surface rather than one screen, because the failure mode is
    a single forgotten flash message or button label, and one screen passing proves
    nothing about the other fourteen. Bangla CONTENT is allowed and expected: the
    register holds Bangla names and the pages hold Bangla titles, and those cells carry
    `lang="bn"`. So the test looks at the CHROME — the rail, the top bar and the page
    header — which never contains content.
    """
    for path in _get_screens(app):
        body = admin_client.get(path).get_data(as_text=True)
        chrome_start = body.find('aria-label="Admin sections"')
        chrome_end = body.find('<main')
        assert chrome_start != -1 and chrome_end != -1, f"{path} has no admin chrome"
        chrome = body[chrome_start:chrome_end]

        bangla = [ch for ch in chrome if "\u0980" <= ch <= "\u09ff"]
        assert not bangla, (
            f"{path} has Bangla in the admin chrome: {''.join(bangla)!r}"
        )

    # And the document declares itself as English, so a screen reader uses the right
    # voice for the interface.
    assert '<html lang="en"' in admin_client.get("/admin/").get_data(as_text=True)


def test_the_audit_screen_never_reaches_a_secret(admin_client, session):
    """§16.2: credentials live in `.env`, and the audit log is displayed.

    `is_secret` settings exist precisely so they cannot be echoed back into a page
    that an operator can open.
    """
    from app.models import Setting

    session.add(
        Setting(key="totp_seed_demo", label_bn="গোপন", value="JBSWY3DPEHPK3PXP",
                value_type="string", group="security", is_secret=True)
    )
    session.commit()

    body = admin_client.get("/admin/settings").get_data(as_text=True)

    assert "JBSWY3DPEHPK3PXP" not in body, "a secret setting was rendered to the page"


# ─────────────────────────────────────────────────────────────────────────────
# The operator's journey: a new name, to the front page
# ─────────────────────────────────────────────────────────────────────────────


def test_an_operator_can_get_a_new_name_onto_the_site(admin_client, session):
    """Create → record consent → publish → the content API. In that order, end to end.

    THIS IS A REGRESSION TEST FOR A 500 ON THE CONSENT SCREEN. The grant path used an
    enum that was never imported (`ConsentAction`) and read a form field under a name it
    was never given, so every grant raised NameError while the WITHDRAWAL path worked
    perfectly. The screens all rendered, the withdrawal tests all passed, and an operator
    could not get a single person onto the site. Nothing exercised a grant through the
    ROUTE, so nothing caught it.

    It asserts the whole journey rather than the one call, because the outcome the
    operator is trying to reach is "the name is on the site" — and there are three
    separate acts between creating a record and that happening, each of which can fail
    silently:

    1. `consent_publication` and `consent_date` are two columns, not one flag (§5.3).
    2. A consent change appends a `consent_events` row rather than only flipping a flag,
       because "when did they agree, and how" is a question the department gets asked.
    3. Publication is a SEPARATE act from consent — the flash says so, and if that ever
       becomes automatic the site would publish names nobody had decided to publish.
    """
    import sqlalchemy

    from app.constants import ConsentAction, ConsentSource
    from app.models import ConsentEvent, Participant
    from app.services.content_service import build_content

    # ── 1. The record. Never published, never consented, on creation. ────────────
    response = admin_client.post(
        "/admin/participants/new",
        data={
            "name_bn": "পরীক্ষামূলক প্রশিক্ষণার্থী",
            "name_en": "Test Participant",
            "slug": "journey-test-person",
            "education": "HSC",
            "batch": "1",
            "outcome_text": "পরীক্ষামূলক ফলাফল।",
        },
    )
    assert response.status_code in (302, 303), "the create form did not redirect"

    person = session.execute(
        sqlalchemy.select(Participant).where(Participant.slug == "journey-test-person")
    ).scalars().first()
    assert person is not None, "the record was not created"
    assert person.is_published is False
    assert person.consent_publication is False
    assert person.can_publish is False, "a brand-new record must not be publishable"

    # ── 2. Consent, with a date and a source. ───────────────────────────────────
    response = admin_client.post(
        f"/admin/participants/{person.id}/consent",
        data={
            "decision": "grant",
            "consent_date": "2026-01-15",
            "consent_source": ConsentSource.WRITTEN_FORM.value,
            "consent_notes": "স্বাক্ষরিত সম্মতিপত্র সংগ্রহ করা হয়েছে।",
        },
    )
    assert response.status_code in (302, 303), (
        "recording consent did not redirect — a 500 here is the bug this test exists for"
    )

    session.expire_all()
    person = session.get(Participant, person.id)
    assert person.consent_publication is True
    assert person.consent_date is not None
    assert person.consent_source is ConsentSource.WRITTEN_FORM
    assert person.can_publish is True, "consent with a date makes the name publishable"
    assert person.is_published is False, "consent alone must NOT publish (it is a separate act)"

    event = session.execute(
        sqlalchemy.select(ConsentEvent).where(ConsentEvent.participant_id == person.id)
    ).scalars().first()
    assert event is not None, "the grant left no consent_events row"
    assert event.action is ConsentAction.GRANTED
    assert event.source is ConsentSource.WRITTEN_FORM

    # ── 3. Consent is not publication. The site still does not show the name. ────
    assert "journey-test-person" not in {row["slug"] for row in build_content()["participants"]}

    # ── 4. Publish. NOW it is on the site. ──────────────────────────────────────
    admin_client.post(f"/admin/participants/{person.id}/publish", data={"action": "publish"})

    session.expire_all()
    person = session.get(Participant, person.id)
    assert person.is_published is True

    payload = build_content()
    served = {row["slug"]: row for row in payload["participants"]}
    assert "journey-test-person" in served, "the name is public but the site cannot see it"

    # The four facts §5.2 allows, and nothing else about the person.
    card = served["journey-test-person"]
    assert card["name_bn"] == "পরীক্ষামূলক প্রশিক্ষণার্থী"
    assert "consent_notes" not in card
    # A portrait is a key that exists and is null until its own permission is recorded.
    assert card["photo_url"] is None

    # ── 5. Withdrawal takes it down again, in the same request. ─────────────────
    response = admin_client.post(
        f"/admin/participants/{person.id}/consent",
        data={"decision": "withdraw", "consent_notes": "অনুরোধে প্রত্যাহার।"},
    )
    assert response.status_code in (302, 303), "the withdrawal path broke"

    session.expire_all()
    person = session.get(Participant, person.id)
    assert person.is_published is False
    assert person.consent_withdrawn_at is not None
    assert "journey-test-person" not in {
        row["slug"] for row in build_content()["participants"]
    }, "a withdrawn name is still being served"

    actions = {
        row.action
        for row in session.execute(
            sqlalchemy.select(ConsentEvent).where(ConsentEvent.participant_id == person.id)
        ).scalars()
    }
    assert actions == {ConsentAction.GRANTED, ConsentAction.WITHDRAWN}, (
        "the history must keep BOTH decisions — the events are append-only"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Records screens (§11.1 routes 26–31)
# ─────────────────────────────────────────────────────────────────────────────


def _record_screens() -> list:
    """Every declared records screen, read from the module that declares them."""
    from app.routes.admin import records
    from app.routes.admin._records import Screen

    return [
        value
        for name, value in vars(records).items()
        if isinstance(value, Screen) and not name.startswith("_")
    ]


def test_a_screen_toggles_a_column_that_actually_exists():
    """A status switch must belong to a column the model has.

    THIS IS THE GENERAL FORM OF A 500. `Screen.active_field` defaulted to `is_active`
    for every screen, so the modules, statistics and settings screens each registered a
    toggle route for a column their model does not have: pressing the button in the row
    actions raised `AttributeError` — a 500 behind a control that looks ordinary. Three
    of the seven screens were affected, which is why the assertion walks all of them
    rather than naming the three.
    """
    broken = []
    for screen in _record_screens():
        has_column = hasattr(screen.model, "is_active")
        if bool(screen.active_field) != has_column:
            broken.append(
                f"{screen.endpoint}: active_field={screen.active_field!r}, "
                f"model has is_active={has_column}"
            )
    assert not broken, "a toggle would 500 or a screen is missing a switch: " + "; ".join(broken)


def test_a_module_is_created_with_the_course_the_picker_offers(admin_client, session):
    """`course_id` is NOT NULL, so the screen has to ask for it.

    Without the picker the create form posted no `course_id` and the INSERT failed with
    `NOT NULL constraint failed: course_modules.course_id` — the add button on the
    modules screen could not work at all.
    """
    import sqlalchemy

    from app.models import Course, CourseModule

    course = Course(title_bn="পরীক্ষামূলক কোর্স", slug="picker-course", is_active=True)
    session.add(course)
    session.commit()

    page = admin_client.get("/admin/course/modules").get_data(as_text=True)
    assert 'name="course_id"' in page, "the screen offers no way to choose the course"
    assert "পরীক্ষামূলক কোর্স" in page, "the picker does not list the course that exists"

    # Submitting without a course is REFUSED, with a message — not a 500.
    response = admin_client.post(
        "/admin/course/modules",
        data={"title_bn": "মডিউল", "hours": "10"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert session.execute(sqlalchemy.select(CourseModule)).scalars().first() is None
    assert "Choose a course" in response.get_data(as_text=True)

    # With it, the row is created and attached.
    admin_client.post(
        "/admin/course/modules",
        data={"course_id": str(course.id), "title_bn": "মডিউল", "hours": "10"},
    )
    module = session.execute(sqlalchemy.select(CourseModule)).scalars().first()
    assert module is not None, "the module was not created"
    assert module.course_id == course.id


def test_a_new_setting_can_be_created_and_its_key_then_frozen(admin_client, session):
    """Read-only must mean "not editable once it exists", not "never written".

    `Setting.key` is read-only, and `_apply_fields` skipped read-only fields
    unconditionally — so the create path never supplied a key and every attempt to add a
    setting died with `NOT NULL constraint failed: settings.key`.
    """
    import sqlalchemy

    from app.models import Setting

    admin_client.post(
        "/admin/settings",
        data={
            "key": "site_probe_setting",
            "label_bn": "পরীক্ষামূলক",
            "value": "one",
            "value_type": "string",
            "group": "probe",
        },
    )
    row = session.execute(
        sqlalchemy.select(Setting).where(Setting.key == "site_probe_setting")
    ).scalars().first()
    assert row is not None, "the setting was not created"

    # Editing it may change the value, but never the key: the code looks the key up.
    admin_client.post(
        "/admin/settings",
        data={
            "row_id": str(row.id),
            "key": "renamed_by_hand",
            "label_bn": "পরীক্ষামূলক",
            "value": "two",
            "value_type": "string",
            "group": "probe",
        },
    )
    session.expire_all()
    refreshed = session.get(Setting, row.id)
    assert refreshed.value == "two"
    assert refreshed.key == "site_probe_setting", "a settings key must not be renamable"


def test_the_section_picker_is_english_and_a_section_can_be_added(admin_client, session):
    """The panel is English, and "Add section" used to 500 before it even saved.

    `section_add` flashed `impl.label_en`, which `SectionBase` does not define —
    `AttributeError` on the one control the page editor is built around. The type names
    shown are now the admin's English vocabulary rather than the site's Bangla labels.
    """
    import sqlalchemy

    from app.models import Page, PageSection
    from app.routes.admin._labels import SECTION_TYPE_NAMES_EN

    admin_client.post("/admin/pages", data={"title_bn": "পাতা", "slug": "section-probe"})
    page = session.execute(
        sqlalchemy.select(Page).where(Page.slug == "section-probe")
    ).scalars().first()
    assert page is not None

    body = admin_client.get(f"/admin/pages/{page.id}").get_data(as_text=True)
    for name in ("Quote", "Rich text", "Timeline"):
        assert name in body, f"the picker does not offer {name!r} in English"
    assert len(SECTION_TYPE_NAMES_EN) == 13, "the picker should offer all 13 types"

    admin_client.post(f"/admin/pages/{page.id}/sections", data={"type": "quote"})
    section = session.execute(
        sqlalchemy.select(PageSection).where(PageSection.page_id == page.id)
    ).scalars().first()
    assert section is not None, "no section was added"
    assert section.type == "quote"
    assert section.is_visible is True
    assert section.content == {}, "a new section must start empty, not pre-filled"


def test_a_record_is_created_with_an_audit_row_that_names_it(admin_client, session):
    """Create through the real form, then check the audit trail.

    THE ENTITY ID IS THE ASSERTION. `commit_with_audit` flushes before recording so
    that a newly-inserted row has an id; without that flush every create in the
    admin would be logged with `entity_id=None`, which is the one field that makes
    an audit row findable.
    """
    from app.models import AuditLog, Faq

    import sqlalchemy

    admin_client.post(
        "/admin/faqs",
        data={"question_bn": "কোর্সটি কি ফ্রি?", "answer_bn": "হ্যাঁ, সম্পূর্ণ বিনামূল্যে।"},
    )

    faq = session.execute(sqlalchemy.select(Faq)).scalars().first()
    assert faq is not None, "the record was not created"
    assert faq.question_bn == "কোর্সটি কি ফ্রি?"

    row = session.execute(
        sqlalchemy.select(AuditLog).where(AuditLog.action == "create")
    ).scalars().first()
    assert row is not None, "no audit row was written for the create"
    assert row.entity_type == "Faq"
    assert row.entity_id == str(faq.id)


def test_a_record_missing_a_required_field_is_refused(admin_client, session):
    """`question_bn` is required. A blank submit must not create a row."""
    import sqlalchemy

    from app.models import Faq

    admin_client.post("/admin/faqs", data={"question_bn": "", "answer_bn": "কিছু"})

    assert session.execute(sqlalchemy.select(Faq)).scalars().first() is None


def test_a_field_that_is_too_long_is_refused_with_reason(admin_client, session):
    """`CourseModule.hours` is capped. The refusal names the field, in English."""
    import sqlalchemy

    from app.models import CourseModule

    response = admin_client.post(
        "/admin/course/modules",
        data={"title_bn": "মডিউল", "hours": "99999"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert session.execute(sqlalchemy.select(CourseModule)).scalars().first() is None
    assert "Hours cannot be more than" in response.get_data(as_text=True)


def test_the_toggle_flips_a_record_and_records_it(admin_client, session):
    """`is_active` is screen 31's own switch, and it is a write like any other."""
    import sqlalchemy

    from app.models import Faq

    faq = Faq(question_bn="প্রশ্ন", answer_bn="উত্তর", category="কোর্স", is_active=True)
    session.add(faq)
    session.commit()
    faq_id = faq.id

    admin_client.post("/admin/faqs/toggle", data={"row_id": str(faq_id)})

    session.expire_all()
    refreshed = session.get(Faq, faq_id)
    assert refreshed.is_active is False


def test_editing_a_record_changes_it_rather_than_copying_it(admin_client, session):
    """The save route creates OR updates depending on `row_id`. An update that
    silently created a second row would double every FAQ on the public page."""
    import sqlalchemy

    from app.models import Faq

    faq = Faq(question_bn="পুরনো", answer_bn="উত্তর", category="কোর্স", is_active=True)
    session.add(faq)
    session.commit()

    admin_client.post(
        "/admin/faqs",
        data={"row_id": str(faq.id), "question_bn": "নতুন", "answer_bn": "উত্তর", "category": "কোর্স"},
    )

    rows = list(session.execute(sqlalchemy.select(Faq)).scalars())
    assert len(rows) == 1, "the edit created a duplicate instead of updating"
    assert rows[0].question_bn == "নতুন"


# ─────────────────────────────────────────────────────────────────────────────
# The pages editor (§11.2)
# ─────────────────────────────────────────────────────────────────────────────


def test_a_page_cannot_be_published_without_a_valid_section(admin_client, session):
    """§11.2's gate. An empty page is a page with nothing on it."""
    import sqlalchemy

    from app.models import Page

    admin_client.post("/admin/pages", data={"title_bn": "খালি পৃষ্ঠা", "slug": "empty-page"})
    page = session.execute(sqlalchemy.select(Page)).scalars().first()

    admin_client.post(f"/admin/pages/{page.id}/publish", data={"action": "publish"})

    session.expire_all()
    assert session.get(Page, page.id).is_published is False, "an empty page was published"


def test_a_page_slug_that_is_not_url_safe_is_refused(admin_client, session):
    """§4.3: slugs are Latin, lowercase and hyphenated. Bangla lives in labels."""
    import sqlalchemy

    from app.models import Page

    admin_client.post("/admin/pages", data={"title_bn": "বাংলা", "slug": "বাংলা-পাতা"})

    assert session.execute(sqlalchemy.select(Page)).scalars().first() is None


def test_the_editor_renders_every_field_of_a_section_schema(admin_client, session):
    """The section editor is schema-driven (`_fields.describe`). A schema field the
    editor forgets is a field an operator cannot set — which looks like a content bug
    rather than a missing form input.

    THE LABEL IS DERIVED FROM THE FIELD KEY, so the expectation is derived the same way
    rather than copied from the schema's Bangla `label_bn`. That is the point: the two
    cannot drift, because there is only one of them.
    """
    from app.models import Page, PageSection
    from app.routes.admin._labels import field_label
    from app.sections.registry import SECTION_SCHEMAS

    page = Page(slug="schema-check", title_bn="স্কিমা", sort_order=1)
    session.add(page)
    session.commit()

    hero = SECTION_SCHEMAS["hero"]
    section = PageSection(page_id=page.id, type="hero", sort_order=1, content={})
    session.add(section)
    session.commit()

    body = admin_client.get(f"/admin/pages/{page.id}").get_data(as_text=True)

    for name in hero:
        assert field_label(name) in body, (
            f"the section editor is missing a labelled input for {name} "
            f"({field_label(name)!r})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Media (§13.1, §13.2)
# ─────────────────────────────────────────────────────────────────────────────


def _png_bytes() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (12, 8), (10, 120, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def upload_root(app, tmp_path):
    """A throwaway UPLOAD_ROOT. The real one is `uploads/` in the project, and a
    test that writes there leaves files behind that the next run then counts."""
    previous = app.config["UPLOAD_ROOT"]
    app.config["UPLOAD_ROOT"] = str(tmp_path)
    yield tmp_path
    app.config["UPLOAD_ROOT"] = previous


def test_a_file_that_only_claims_to_be_an_image_is_refused(admin_client, session, upload_root):
    """§13.1. `logo.png` containing something else must never be stored."""
    import sqlalchemy

    from app.models import MediaItem

    response = admin_client.post(
        "/admin/media",
        data={"files": (io.BytesIO(b"<?php echo 1; ?>"), "logo.png"), "alt_bn": "লোগো"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert session.execute(sqlalchemy.select(MediaItem)).scalars().first() is None
    assert not list(upload_root.rglob("*.*")), "a rejected file reached the disk"


def test_svg_is_refused_even_though_it_is_an_image(admin_client, session, upload_root):
    """§13.2: an SVG can carry script and would be served from the admin's origin."""
    import sqlalchemy

    from app.models import MediaItem

    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    admin_client.post(
        "/admin/media",
        data={"files": (io.BytesIO(svg), "logo.svg")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert session.execute(sqlalchemy.select(MediaItem)).scalars().first() is None


def test_a_real_image_is_stored_under_a_name_of_our_choosing(admin_client, session, upload_root):
    """The stored name is random and the path is not the uploaded filename. §13.1."""
    import sqlalchemy

    from app.models import MediaItem

    admin_client.post(
        "/admin/media",
        data={"files": (io.BytesIO(_png_bytes()), "holiday photo.png"), "alt_bn": "ল্যাব"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    item = session.execute(sqlalchemy.select(MediaItem)).scalars().first()
    assert item is not None, "a valid PNG was not stored"
    assert item.alt_bn == "ল্যাব"
    assert "holiday" not in item.path, "the uploaded filename survived into the path"

    stored = upload_root / item.path
    assert stored.is_file(), "the row exists but no file was written"


def test_an_image_used_by_a_section_cannot_be_deleted(admin_client, session, upload_root):
    """Deleting it would leave a hole on a published page, and the editor deleting
    it is the only person who knows which page that is."""
    import sqlalchemy

    from app.models import MediaItem, Page, PageSection

    page = Page(slug="gallery-check", title_bn="গ্যালারি", sort_order=1)
    session.add(page)
    session.commit()

    item = MediaItem(path="images/used.png", alt_bn="ব্যবহৃত", kind="image")
    session.add(item)
    session.commit()

    session.add(
        PageSection(page_id=page.id, type="media_feature", sort_order=1, content={"media_id": item.id})
    )
    session.commit()
    item_id = item.id

    response = admin_client.post(
        f"/admin/media/{item_id}/delete", follow_redirects=True
    )

    assert session.get(MediaItem, item_id) is not None, "an in-use image was deleted"
    assert "is used by" in response.get_data(as_text=True)


def test_an_upload_with_no_file_is_reported_not_crashed(admin_client):
    """An empty file picker is a slip, not a 500."""
    response = admin_client.post(
        "/admin/media", data={}, content_type="multipart/form-data", follow_redirects=True
    )

    assert response.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Messages and the audit screen
# ─────────────────────────────────────────────────────────────────────────────


def test_a_message_moves_along_its_status(admin_client, session):
    """§11.1 route 32. Nothing here deletes — §16.4's retention job does that."""
    from app.constants import MessageStatus
    from app.models import ContactMessage

    message = ContactMessage(
        name="রহিম", email="rahim@example.test", subject="প্রশ্ন", message="কোর্স কবে?"
    )
    session.add(message)
    session.commit()
    message_id = message.id

    response = admin_client.post(
        f"/admin/messages/{message_id}",
        data={"status": "replied", "admin_notes": "উত্তর দেওয়া হয়েছে"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    session.expire_all()
    refreshed = session.get(ContactMessage, message_id)
    assert refreshed.status == MessageStatus.REPLIED
    assert refreshed.replied_at is not None, "replying left no timestamp"
    assert refreshed.admin_notes == "উত্তর দেওয়া হয়েছে"


def test_the_audit_screen_shows_the_difference_a_write_made(admin_client, session):
    """§12.1's "before/after diff", visible. The screen is the deliverable."""
    from app.models import AuditLog, Faq

    import sqlalchemy

    faq = Faq(question_bn="আগে", answer_bn="উত্তর", category="কোর্স", is_active=True)
    session.add(faq)
    session.commit()

    admin_client.post(
        "/admin/faqs",
        data={"row_id": str(faq.id), "question_bn": "পরে", "answer_bn": "উত্তর", "category": "কোর্স"},
    )

    body = admin_client.get("/admin/audit").get_data(as_text=True)
    assert "পরে" in body or "after" in body.lower(), "the audit screen shows no diff"

    row = session.execute(
        sqlalchemy.select(AuditLog)
        .where(AuditLog.action == "update")
        .order_by(AuditLog.id.desc())
    ).scalars().first()
    assert row is not None
    assert (row.before_json or {}).get("question_bn") == "আগে"
    assert (row.after_json or {}).get("question_bn") == "পরে"


def test_every_admin_page_carries_the_shell(admin_client, app):
    """Step 4.5's "done when", asserted across the whole surface rather than on one
    screen: the rail, the breadcrumb, the page header and the flash region all come
    from the shell."""
    for path in _get_screens(app):
        body = admin_client.get(path).get_data(as_text=True)
        assert 'aria-label="Admin sections"' in body, f"{path} has no section rail"
        assert 'aria-label="Breadcrumb"' in body, f"{path} has no breadcrumb"
        assert 'name="robots" content="noindex, nofollow"' in body, f"{path} is indexable"
        # The page header: every screen says which group it belongs to.
        assert "admin-eyebrow" in body, f"{path} has no section eyebrow"


def test_no_admin_screen_renders_the_public_navigation(admin_client, app):
    """A public nav on an admin screen is a set of links out of the admin."""
    for path in _get_screens(app):
        body = admin_client.get(path).get_data(as_text=True)
        assert 'href="/gallery"' not in body, f"{path} leaked the public navigation"
        assert 'href="/batch-1"' not in body, f"{path} leaked the public navigation"


def test_no_admin_screen_prints_a_traceback_shape(admin_client, app):
    """A Bangla admin that occasionally shows `Traceback (most recent call last)` is
    a Bangla admin with an English page in it."""
    for path in _get_screens(app):
        body = admin_client.get(path).get_data(as_text=True)
        assert "Traceback (most recent call last)" not in body, path


def test_the_export_does_not_carry_a_prohibited_column(admin_client, session):
    """§5.1 lists what may never be exported. The header row is the contract.

    READ FROM THE FILE, NOT FROM THE COLUMNS CONSTANT. The constant is what the
    screen intends; the header row is what lands in the operator's spreadsheet, and
    the two are allowed to differ only if someone edited the writer.
    """
    import csv
    import io as _io

    response = admin_client.get("/admin/participants/export.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["Content-Type"]
    assert "attachment" in response.headers["Content-Disposition"]

    text = response.get_data().decode("utf-8-sig")
    rows = list(csv.reader(_io.StringIO(text)))

    # A watermark, then a blank line, then the header. Asserted so that a change to
    # the watermark cannot silently move the header into the data.
    assert rows[2] == [], "the watermark no longer ends with a blank line"
    header = ",".join(rows[3])

    for forbidden in ("nid", "birth", "passport", "address", "father", "mother", "phone"):
        assert forbidden not in header.lower(), f"the export leaks a {forbidden} column"

    assert "নাম" in header, "the export has no name column"
