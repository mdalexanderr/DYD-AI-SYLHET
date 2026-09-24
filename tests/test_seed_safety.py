"""The seeder must not be able to destroy editorial state. plan.md §20, §11.2.

WHY THIS FILE EXISTS
    `flask seed` is run by the deploy, unattended, against a database that already
    holds the department's content. It therefore has to be safe to run at any time,
    and that is a property of the seeder rather than of the deploy script — the deploy
    cannot be made responsible for not calling it.

    The bug these tests pin down was real: `_upsert` wrote every key in `defaults` on
    every run, and one of those keys was `Page.is_published = False`. A redeploy
    silently unpublished the whole public site. Nothing reported it, because the
    seeder prints "pages: 7" before and after.

    Every test here calls `seed_reference_data()` TWICE. The first call stands for the
    first install; the second stands for every redeploy afterwards, and it is the one
    that has to change nothing.
"""

from __future__ import annotations


def _seed():
    from app.seeds import seed_reference_data

    return seed_reference_data()


def _home():
    """Read the home page fresh, past the identity map.

    The seeder commits, and a cached instance would hand back pre-seed values, which
    would make these tests pass for the wrong reason.
    """
    from app.extensions import db
    from app.models import Page

    db.session.expire_all()
    return db.session.execute(
        db.select(Page).where(Page.slug == "home")
    ).scalars().first()


def test_a_second_seed_does_not_unpublish_a_live_page(app, session):
    """The exact production failure: run the deploy, lose the site."""
    from app.extensions import db

    _seed()
    page = _home()
    page.publish()
    db.session.commit()
    assert _home().is_published is True

    _seed()  # the redeploy

    assert _home().is_published is True, (
        "re-running the seeder unpublished a live page — a routine deploy would take "
        "the public site offline"
    )


def test_a_second_seed_does_not_remove_a_pages_sections(app, session):
    _seed()
    before = len(_home().sections)
    assert before, "the seeder produced a page with no sections"

    _seed()

    assert len(_home().sections) == before, "the redeploy changed the page's sections"


def test_a_second_seed_does_not_duplicate_sections(app, session):
    """The opposite failure, and the one a careless fix introduces."""
    _seed()
    before = len(_home().sections)

    _seed()

    assert len(_home().sections) == before


def test_a_second_seed_preserves_an_edited_title(app, session):
    """Content the department edited must survive the next deploy."""
    from app.extensions import db

    _seed()
    page = _home()
    page.title_bn = "সম্পাদিত শিরোনাম"
    db.session.commit()

    _seed()

    assert _home().title_bn == "সম্পাদিত শিরোনাম", (
        "the seeder overwrote content that had been edited in the CMS"
    )


def test_a_second_seed_preserves_an_edited_setting(app, session):
    """Settings are edited in the admin (§11.4). A redeploy must not revert them."""
    from app.extensions import db
    from app.models import Setting

    _seed()
    # Ordered so the test picks the same setting every run; an arbitrary row would
    # make the assertion depend on insertion order.
    setting = db.session.execute(
        db.select(Setting).order_by(Setting.key).limit(1)
    ).scalars().first()
    assert setting is not None, "the seeder produced no settings"

    setting.value = "edited-by-the-department"
    db.session.commit()

    _seed()

    db.session.expire_all()
    again = db.session.get(Setting, setting.id)
    assert again.value == "edited-by-the-department", "the seeder reverted an edited setting"


def test_the_seeder_is_still_idempotent_for_row_counts(app, session):
    """Idempotence is what the redeploy actually depends on: no duplicates."""
    from sqlalchemy import func

    from app.extensions import db
    from app.models import Page, PageSection

    first = _seed()
    second = _seed()

    assert first["pages"] == second["pages"]
    assert first["page_sections"] == second["page_sections"]

    pages = int(db.session.execute(db.select(func.count(Page.id))).scalar_one())
    sections = int(db.session.execute(db.select(func.count(PageSection.id))).scalar_one())
    assert pages == second["pages"], "a second seed created duplicate pages"
    assert sections == second["page_sections"], "a second seed duplicated sections"


def test_the_seeder_still_creates_everything_on_a_first_run(app, session):
    """The fix must not have made the seeder inert.

    `_upsert` is now create-only, so this is the test that would fail if it were
    changed to do nothing at all — which is the obvious way to make the tests above
    pass while breaking the first install.
    """
    from sqlalchemy import func

    from app.extensions import db
    from app.models import Course, Faq, Institution, Page, PageSection, Setting

    counts = _seed()

    assert counts["pages"] == 7
    assert counts["page_sections"] > 0
    for model in (Page, PageSection, Course, Institution, Faq, Setting):
        rows = int(db.session.execute(db.select(func.count(model.id))).scalar_one())
        assert rows > 0, f"the seeder created no {model.__name__} rows"
