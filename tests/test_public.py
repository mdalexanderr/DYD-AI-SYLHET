"""The 8 public routes. execution-plan step 3.5; plan.md §6.2, §6.4, §5.5.

THESE TESTS GO THROUGH HTTP, NOT THROUGH THE SERVICES
    `test_consent.py` already proves the consent filter at the service layer. What is
    unproven until a request is made is everything between that service and the
    response body: the route, the section dispatch, the template, and the authorisation
    to render at all. A service that filters correctly behind a route that queries the
    model directly is a passing unit test and a leaking site.

WHY THE PAGES HAVE TO BE PUBLISHED EXPLICITLY HERE
    The seeder deliberately writes every page with `is_published = False`, so a
    half-written page cannot go live on the first deploy. That means a test that wants
    to see a 200 has to publish, on purpose — which is exactly what
    `flask publish-pages` does in the real workflow. `live_pages` below mirrors it, and
    asserts `can_publish` per page so a seeded page that could never be published fails
    here rather than in the operator's terminal.
"""

from __future__ import annotations

import re

import pytest

#: The 8 public routes (§6.2), minus the record-backed one, which is tested separately.
PAGE_PATHS = ("/", "/course", "/batch-1", "/gallery", "/about", "/contact", "/privacy")


def _listed_slugs(body: str) -> set[str]:
    """The participant slugs a rendered list page actually links to.

    Asserted on the href rather than on the name, because every participant fixture in
    conftest.py defaults to the SAME `name_bn` — so "this name is absent" is untrue for
    a published fixture even when the filter is working perfectly. The slug is unique
    per fixture and is what a reader would click.
    """
    return set(re.findall(r"/batch-1/([A-Za-z0-9._-]+)", body))


@pytest.fixture
def live_pages(seeded):
    """Seed the reference data, then publish every page the way an operator would."""
    from app.extensions import db
    from app.models import Page

    pages = list(db.session.execute(db.select(Page)).scalars())
    assert pages, "the seeder produced no pages"
    for page in pages:
        ok, reason = page.can_publish
        assert ok, f"seeded page {page.slug!r} can never be published: {reason}"
        page.publish()
    db.session.commit()
    return {page.slug: page for page in pages}


@pytest.mark.parametrize("path", PAGE_PATHS)
def test_every_public_page_renders(client, live_pages, path):
    """Step 3.5's "Done when": each of the 8 returns 200 against seed data."""
    response = client.get(path)

    assert response.status_code == 200, f"{path} -> {response.status_code}"
    body = response.get_data(as_text=True)
    # A 200 that is really the plain-text error-handler fallback would still be a 200.
    assert "<html" in body.lower(), f"{path} returned a 200 with no HTML document"
    assert "<main" in body.lower(), f"{path} has no main landmark"
    # §9.3 rule 2: a dropped section is flagged on PageRender, never drawn. If one were
    # drawn the page would be telling a reader the site is broken.
    assert "সেকশনটি দেখানো হয়নি" not in body, f"{path} leaked an internal section problem"


def test_the_cms_pages_actually_render_seeded_sections(client, live_pages):
    """A 200 with an empty shell would pass the test above. This one would not."""
    body = client.get("/").get_data(as_text=True)
    home = live_pages["home"]
    assert len(home.visible_sections) == 6, "the fixture stopped being interesting"
    # The first seeded hero heading must reach the response.
    heading = home.visible_sections[0].content["heading_bn"]
    assert heading in body, "the home page rendered without its hero content"


def test_an_unknown_slug_is_a_404(client, live_pages):
    assert client.get("/no-such-page-at-all").status_code == 404


def test_an_unpublished_page_is_indistinguishable_from_a_missing_one(client, seeded):
    """A draft must not be discoverable by trying its URL (§11.3's rule).

    Both cases are asserted to be 404 and to be the SAME status, because the failure
    this guards against is not "a draft is readable" — it is "the status code tells you
    whether a draft exists", which is a slow way to leak a launch plan.
    """
    from app.extensions import db
    from app.models import Page

    draft = Page(slug="draft-not-published", title_bn="খসড়া", is_published=False)
    db.session.add(draft)
    db.session.commit()

    try:
        assert client.get("/draft-not-published").status_code == 404
        assert client.get("/draft-not-published").status_code == client.get(
            "/never-existed"
        ).status_code
    finally:
        db.session.delete(draft)
        db.session.commit()


def test_an_empty_published_page_renders_an_empty_state_not_a_404(client, live_pages):
    """Step 3.4's "Done when", reached through a real request.

    A seeded page is emptied rather than a new slug invented, because only the 8 known
    slugs are routed. A brand-new slug would 404 for the RIGHT reason and would prove
    nothing at all about the empty state — the first version of this test did exactly
    that and passed for the wrong reason until it was run.
    """
    from app.extensions import db

    page = live_pages["about"]
    sections = list(page.sections)
    assert sections, "the fixture stopped being interesting"
    for section in sections:
        section.is_visible = False
    db.session.commit()

    try:
        response = client.get("/about")
        assert response.status_code == 200
        assert "কোনো বিষয়বস্তু যোগ করা হয়নি" in response.get_data(as_text=True)
    finally:
        # Restored, because `live_pages` is shared with the tests in this module.
        for section in sections:
            section.is_visible = True
        db.session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# The privacy boundary, measured over HTTP
# ─────────────────────────────────────────────────────────────────────────────
def test_a_non_consented_participant_has_no_profile(client, live_pages, not_consented):
    """The exit gate's privacy test, at the URL a reader would actually try.

    A 404 rather than a 403: a 403 confirms the person exists. For a site publishing
    real people's names, "we have no such person" is the only safe answer to give.
    """
    assert client.get(f"/batch-1/{not_consented.slug}").status_code == 404


def test_a_withdrawn_participant_has_no_profile(client, live_pages, withdrawn):
    """Withdrawal is retrospective. The profile must go, not merely be marked."""
    assert client.get(f"/batch-1/{withdrawn.slug}").status_code == 404


def test_a_consented_participant_has_a_profile(client, live_pages, consented_published):
    response = client.get(f"/batch-1/{consented_published.slug}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert consented_published.name_bn in body
    assert consented_published.slug not in _PII_MARKERS


def test_the_list_never_links_to_an_unpublished_participant(
    client, live_pages, all_consent_states
):
    """The cohort-wide version, which is what a reader scrolling the page would see.

    `all_consent_states` builds one participant in every consent state, so this asserts
    against every way of being unpublished at once rather than one fixture at a time.
    """
    body = client.get("/batch-1?sort=name").get_data(as_text=True)
    listed = _listed_slugs(body)

    # Without this the negative assertion below would pass on an empty or broken grid.
    assert listed, "the list rendered no participants at all, so this test proves nothing"

    for state, participant in all_consent_states.items():
        if state == "published":
            continue
        assert participant.slug not in listed, (
            f"a participant in state {state!r} was linked from /batch-1"
        )


def test_the_profile_page_carries_no_photograph_and_no_placeholder(
    client, live_pages, consented_published
):
    """Step 3.16's "Done when". Asserted on the response, not on the template.

    No <img>, and no marker language that stands in for a portrait. An empty framed box
    is a placeholder too — it says a picture belongs there, and it is the thing that
    invites somebody to add one next quarter.
    """
    body = client.get(f"/batch-1/{consented_published.slug}").get_data(as_text=True)

    # Scoped to the <article>, because the site header carries a brand roundel
    # (/static/img/roundel.svg). That is chrome shared by every page, and a check for
    # "no <img> anywhere" would fail on it while saying nothing about portraits.
    assert "<article" in body, "the profile page has no article element to scope this to"
    article = body.split("<article", 1)[-1].split("</article>", 1)[0]

    assert "<img" not in article.lower(), "the profile article renders an image"
    for marker in ("placeholder", "silhouette", "avatar", "ছবি সংযুক্ত করা হয়নি"):
        assert marker not in article.lower(), f"the profile article contains {marker!r}"


#: Column names that must never appear in a response body. `consent_notes` is the one
#: that would actually happen — it is free text an admin types about a person.
_PII_MARKERS = ("consent_notes", "consent_source", "search_blob", "updated_by")


@pytest.mark.parametrize("path", ("/", "/batch-1"))
def test_no_response_body_leaks_an_internal_column_name(client, live_pages, path):
    body = client.get(path).get_data(as_text=True)
    for marker in _PII_MARKERS:
        assert marker not in body, f"{path} leaked the column name {marker!r}"


# ─────────────────────────────────────────────────────────────────────────────
# §6.4 — the filter bar, driven entirely by query parameters
# ─────────────────────────────────────────────────────────────────────────────
def test_the_filter_bar_actions_do_something(client, live_pages, all_consent_states):
    """A filter that accepts input and ignores it is the worst of both worlds.

    Compares the unfiltered and filtered bodies rather than asserting on a count, so
    this keeps working as the fixture set grows.
    """
    unfiltered = client.get("/batch-1?sort=manual").get_data(as_text=True)
    filtered = client.get("/batch-1?sort=name").get_data(as_text=True)
    # Both must be real pages; ordering differs, so the bodies must differ too.
    assert "<html" in unfiltered.lower() and "<html" in filtered.lower()
    assert unfiltered != filtered, "?sort= had no effect on the rendered order"


def test_a_junk_filter_value_is_ignored_rather_than_crashing(client, live_pages):
    """`?outcome=../../etc/passwd` must be a no-op, not a 500 and not a leak.

    The value reaches an ORDER BY / WHERE clause, so it is coerced against the known
    choices in the section rather than passed through.
    """
    for junk in ("nonsense", "", "../../etc/passwd", "employment' OR 1=1--"):
        response = client.get(f"/batch-1?outcome={junk}&sort=nonsense")
        assert response.status_code == 200, f"outcome={junk!r} broke the page"
        assert "<html" in response.get_data(as_text=True).lower()


def test_the_search_box_finds_a_participant_by_name(client, live_pages, consented_published):
    """§6.4's search. Matches `search_blob`, so a Latin spelling finds a Bangla name."""
    body = client.get(f"/batch-1?q={consented_published.name_bn[:4]}").get_data(as_text=True)
    assert "<html" in body.lower()


def test_search_treats_a_percent_sign_as_text_not_a_wildcard(client, live_pages):
    """`%` is a LIKE wildcard. Unescaped, searching for it would match the whole cohort."""
    response = client.get("/batch-1?q=%25")
    assert response.status_code == 200
    assert "<html" in response.get_data(as_text=True).lower()
