"""The media route and the SEO surface. Steps 3.6 and 3.7; plan.md §13.1, §15.3.

3.6's "DONE WHEN" NAMES THE TWO REFUSALS, NOT THE SUCCESS
    "an expired signature and a tampered signature are both rejected by test."
    A signing scheme that serves the happy path and accepts anything else is worse than
    no signing, because it looks like a control. Both refusals are asserted, and so is
    a signature minted for a DIFFERENT file — the case a naive implementation gets
    wrong by checking that the token is valid rather than that it is valid FOR THIS
    PATH.

3.7's "DONE WHEN" IS A PRIVACY TEST
    "a non-consented participant's slug is ABSENT from the sitemap — this is a privacy
    test, not an SEO test." So the sitemap is asserted against every way of being
    unpublished at once, not one fixture at a time.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _app_context(app):
    """An application context for the whole module.

    `media_service.sign` and `verify` read `SECRET_KEY` from `current_app`, and the
    unit tests call them directly rather than through a request. Without this they
    raise "Working outside of application context" — which is correct behaviour, and
    a property of the test rather than of the code.
    """
    with app.app_context():
        yield


@pytest.fixture
def media_root(app, tmp_path):
    """A throwaway upload root, with one good file and one hostile one.

    `UPLOAD_ROOT` and the allow list are pinned explicitly. The base config reads them
    from the environment, and a developer with them set in `.env` would otherwise see
    these tests fail for reasons that have nothing to do with the route.
    """
    good = tmp_path / "classroom.jpg"
    good.write_bytes(b"\xff\xd8\xff\xe0not-a-real-jpeg-but-a-real-file")

    # An SVG is a script container. It is in REJECTED_UPLOAD_EXTENSIONS, and serving it
    # with a one-year immutable cache would be a stored XSS with a long tail.
    hostile = tmp_path / "payload.svg"
    hostile.write_text("<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>",
                       encoding="utf-8")

    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "deep.jpg").write_bytes(b"\xff\xd8\xff\xe0nested")

    previous_root = app.config["UPLOAD_ROOT"]
    previous_ext = app.config.get("ALLOWED_UPLOAD_EXTENSIONS")
    app.config["UPLOAD_ROOT"] = str(tmp_path)
    app.config["ALLOWED_UPLOAD_EXTENSIONS"] = ("jpg", "jpeg", "png", "webp")
    yield tmp_path
    app.config["UPLOAD_ROOT"] = previous_root
    app.config["ALLOWED_UPLOAD_EXTENSIONS"] = previous_ext


def _url(path: str) -> str:
    from app.services import media_service

    return media_service.signed_url(path)


# ─────────────────────────────────────────────────────────────────────────────
# 3.6 — the signed media route
# ─────────────────────────────────────────────────────────────────────────────
def test_a_signed_url_serves_the_file(client, media_root):
    response = client.get(_url("classroom.jpg"))

    assert response.status_code == 200
    assert response.data.startswith(b"\xff\xd8\xff\xe0")


def test_a_signed_url_is_immutable_and_not_sniffable(client, media_root):
    """The two headers that matter.

    `nosniff` stops a client second-guessing the declared type — which is the
    mechanism behind stored XSS via an uploaded file. `immutable` is safe PRECISELY
    because the signature is in the URL: new bytes at the same path produce a new URL.
    """
    response = client.get(_url("classroom.jpg"))

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "immutable" in response.headers["Cache-Control"]
    assert "max-age=31536000" in response.headers["Cache-Control"]


def test_an_unsigned_request_is_a_404(client, media_root):
    """404, not 403. A 403 confirms the file exists — an oracle for what is on disk."""
    response = client.get("/media/classroom.jpg")

    assert response.status_code == 404


def test_a_tampered_signature_is_rejected(client, media_root):
    from app.services import media_service

    token = media_service.sign("classroom.jpg")
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")

    assert client.get(f"/media/classroom.jpg?sig={tampered}").status_code == 404


def test_an_expired_signature_is_rejected(app, media_root):
    """3.6's "Done when", first half."""
    from app.services import media_service

    token = media_service.sign("classroom.jpg")

    # `max_age=-1` makes every token older than -1 seconds, i.e. all of them.
    assert media_service.verify("classroom.jpg", token, max_age=-1) is False
    # Control: the same token is valid without the expiry, so the test is about
    # expiry and not about a token that was never valid.
    assert media_service.verify("classroom.jpg", token) is True


def test_a_signature_for_one_file_does_not_unlock_another(client, app, media_root):
    """THE BUG A NAIVE IMPLEMENTATION SHIPS.

    Checking that `loads(token)` succeeds rather than that it equals the requested
    path means any valid token opens every file — which looks like a working signature
    scheme right up until somebody tries.
    """
    from app.services import media_service

    token_for_good = media_service.sign("classroom.jpg")

    assert media_service.verify("nested/deep.jpg", token_for_good) is False
    assert client.get(f"/media/nested/deep.jpg?sig={token_for_good}").status_code == 404


def test_an_svg_is_never_served(client, media_root):
    """Even correctly signed. SVG is a script container, not an image."""
    from app.services import media_service

    token = media_service.sign("payload.svg")

    assert client.get(f"/media/payload.svg?sig={token}").status_code == 404


@pytest.mark.parametrize(
    "hostile",
    ("../instance/ai_sylhet.db", "..%2F..%2Fetc%2Fpasswd", "/etc/passwd", "C:/windows/win.ini"),
)
def test_a_traversal_attempt_is_refused(app, media_root, hostile):
    """Refused by the route's own check, not only by `send_from_directory`."""
    from app.services import media_service

    assert media_service._is_safe_relative_path(hostile) is False


def test_a_nested_path_still_works(client, media_root):
    """The traversal guard must not have broken legitimate subdirectories."""
    response = client.get(_url("nested/deep.jpg"))

    assert response.status_code == 200


def test_two_signatures_for_the_same_path_are_both_valid(app, media_root):
    """A signed URL must keep working when the page that carries it is re-rendered.

    NOT asserted as byte-equality: `itsdangerous` embeds the signing time, so two
    calls a second apart legitimately differ. What matters is that both verify — a
    scheme that produced one valid and one invalid token for the same file would
    break every cached page on a rebuild.
    """
    from app.services import media_service

    first = media_service.sign("classroom.jpg")
    second = media_service.sign("classroom.jpg")

    assert media_service.verify("classroom.jpg", first) is True
    assert media_service.verify("classroom.jpg", second) is True


# ─────────────────────────────────────────────────────────────────────────────
# 3.7 — robots.txt
# ─────────────────────────────────────────────────────────────────────────────
def test_robots_disallows_both_the_guess_and_the_real_prefix(client):
    """`/admin/` is what somebody tries; `ops-sylhet` is what exists.

    Listing only the first would be security theatre — the real path would stay
    crawlable while the file looked thorough.
    """
    body = client.get("/robots.txt").get_data(as_text=True)

    assert client.get("/robots.txt").status_code == 200
    assert "Disallow: /admin/" in body
    assert "Disallow: /ops-sylhet/" in body
    assert "Disallow: /login" in body


def test_robots_advertises_the_sitemap(client):
    body = client.get("/robots.txt").get_data(as_text=True)

    assert "Sitemap: " in body
    assert body.rstrip().endswith("sitemap.xml")


def test_robots_uses_the_configured_prefix_not_a_hardcoded_one(client, app):
    """A hardcoded prefix is a prefix that will disagree with the real one."""
    previous = app.config["ADMIN_URL_PREFIX"]
    app.config["ADMIN_URL_PREFIX"] = "not-the-default"
    try:
        body = client.get("/robots.txt").get_data(as_text=True)
    finally:
        app.config["ADMIN_URL_PREFIX"] = previous

    assert "Disallow: /not-the-default/" in body


# ─────────────────────────────────────────────────────────────────────────────
# 3.7 — the sitemap
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def published_pages(seeded):
    from app.extensions import db
    from app.models import Page

    pages = list(db.session.execute(db.select(Page)).scalars())
    for page in pages:
        page.publish()
    db.session.commit()
    return {page.slug: page for page in pages}


def _sitemap(client) -> str:
    from app.routes.seo import SITEMAP_CACHE_KEY, invalidate_cache

    # The cache would otherwise serve the first test's sitemap to every later one.
    invalidate_cache()
    _ = SITEMAP_CACHE_KEY
    return client.get("/sitemap.xml").get_data(as_text=True)


def test_the_sitemap_is_well_formed_and_lists_published_pages(client, published_pages):
    # `S314` wants defusedxml for parsing untrusted input. This parses OUR OWN response
    # body in a test, which is the opposite of untrusted — and the point of parsing it
    # rather than string-matching is that a malformed sitemap is rejected wholesale by
    # every crawler, which a substring check would not notice.
    import xml.etree.ElementTree as ET

    body = _sitemap(client)

    root = ET.fromstring(body)  # noqa: S314
    locations = [el.text for el in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]

    assert locations, "the sitemap is empty"
    assert any("/course" in loc for loc in locations), "published pages are missing"


def test_the_sitemap_omits_an_unpublished_page(client, seeded):
    from app.extensions import db
    from app.models import Page

    page = db.session.execute(db.select(Page).where(Page.slug == "about")).scalars().first()
    was = page.is_published
    page.is_published = False
    db.session.commit()
    try:
        body = _sitemap(client)
    finally:
        page.is_published = was
        db.session.commit()

    assert "/about" not in body, "a draft page was advertised to crawlers"


def test_a_non_consented_participant_is_absent_from_the_sitemap(
    client, published_pages, all_consent_states
):
    """THE "DONE WHEN" OF STEP 3.7 — a privacy test, not an SEO test.

    A sitemap is a list of everything a crawler should fetch. One built from the model
    rather than through `participant_service.list_published` is a published list of
    people who never agreed to be listed, and every one of those slugs would be
    discovered, fetched and indexed.
    """
    body = _sitemap(client)

    for state, participant in all_consent_states.items():
        if state == "published":
            continue
        assert participant.slug not in body, (
            f"a participant in state {state!r} appeared in the sitemap — their slug "
            "would be crawled and indexed"
        )


def test_a_consented_participant_appears_in_the_sitemap(
    client, published_pages, consented_published
):
    """The control for the test above. Without it, an empty sitemap would pass.

    `consented_published` is published and consented, so it must be present — otherwise
    the privacy assertion would be satisfied by a sitemap that lists nobody.
    """
    body = _sitemap(client)

    assert consented_published.slug in body
    assert "/batch-1/" in body
