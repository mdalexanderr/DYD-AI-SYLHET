"""Public pages — routes 1–8. plan.md §6.2, §6.4, §5.5, step 3.5.

SEVEN ROUTES, ONE VIEW
    `/`, `/course`, `/batch-1`, `/gallery`, `/about`, `/contact` and `/privacy` are all
    "a `pages` row and its ordered sections". They are registered from one table rather
    than written out seven times: seven near-identical view functions is seven places
    for the 404 rule below to be forgotten in one of them.

`/` AND THE FRONTEND'S PAGES ARE REGISTERED ELSEWHERE OR NOT AT ALL
    The React frontend is the site's front page and now also owns `/gallery` and
    `/contact` (docs/FRONTEND.md), so those three routes are withheld from this table
    while the frontend holds them — `SPA_ROUTES` in app/config.py is the list. The
    rest of the pages, and every participant profile, are unaffected.

A MISSING PAGE AND AN UNPUBLISHED PAGE MUST LOOK IDENTICAL
    `render_page_by_slug` returns None for both, and both 404. If they were
    distinguishable, `/privacy` would answer "exists but not published" and the URL
    would become an oracle for which drafts are sitting in the CMS (§11.3's rule,
    applied to the public side).

`/batch-1/<slug>` IS THE ONLY ROUTE BACKED BY A ROW RATHER THAN A PAGE
    A participant has a profile page but no `pages` row, so it is dispatched
    separately. It goes through `participant_service.get_published`, which returns None
    for a non-consented slug AND for a slug that never existed — the same
    indistinguishability, for the same reason, about a person rather than a page.
"""

from __future__ import annotations

from collections.abc import Iterable

from flask import Blueprint, abort, render_template, request

from app.services import media_service, page_service, participant_service

#: The app factory supplies the prefix via `register_blueprint`. Kept at None here so
#: the default lives in one place — config.py.
URL_PREFIX = None

#: Routes 1–8 (§6.2), minus the one that needs a record. Order is the order a reader
#: meets them, which is the same order `HEADER_NAV` uses.
PAGE_ROUTES: tuple[tuple[str, str], ...] = (
    ("/", "home"),
    ("/course", "course"),
    ("/batch-1", "batch-1"),
    ("/gallery", "gallery"),
    ("/about", "about"),
    ("/contact", "contact"),
    ("/privacy", "privacy"),
)


def _render_cms_page(slug: str):
    """Build the view for one seeded `pages` row.

    A closure rather than a single view reading the slug from `request.path`: deriving
    the slug from the URL would make `/privacy` and `/Privacy` two code paths, and
    would let a trailing newline in a template turn into a fifth lookup.
    """

    def view():
        result = page_service.render_page_by_slug(slug, request)
        if result is None:
            abort(404)
        # `problems` is passed through for the test client and for `render-check`, but
        # public/page.html deliberately does not draw it. See the note in that file.
        return render_template(
            "public/page.html",
            page=result.page,
            sections=result.sections,
            problems=result.problems,
            is_empty=result.is_empty,
        )

    view.__name__ = f"page_{slug.replace('-', '_')}"
    return view


def participant_profile(slug: str):
    """Route 4 — one participant's profile (§5.5, step 3.16).

    404s for a withdrawn, unconsented or unknown slug. `to_profile` is an allowlist, so
    even if this view passed the wrong object the template could not reach a consent
    note or an audit field.
    """
    participant = participant_service.get_published(slug)
    if participant is None:
        abort(404)

    prev, next_ = participant_service.neighbours(participant)
    return render_template(
        "public/profile.html",
        p=participant_service.to_profile(participant, prev=prev, next_=next_),
        batch_line=participant_service.batch_line(participant),
    )


def media(filename: str):
    """Route 13 — serve an upload from outside the webroot, behind a signature.

    The work is in `media_service.serve`, which owns the traversal check, the
    extension allow list, the signature check and the response headers. This view
exists only to bind the URL shape to that function — there is no policy here to
    drift away from the policy there.

    Every refusal is a 404, never a 403: see the module docstring of media_service.
    """
    return media_service.serve(
        filename, request.args.get(media_service.SIGNATURE_PARAM)
    )


def _normalise(rule: str) -> str:
    """`/gallery/` and `/gallery` are the same path, and `PAGE_ROUTES` has no slash.

    Both halves of the comparison go through this, so a trailing slash in
    `SPA_ROUTES` cannot withhold nothing while looking like it withheld something.
    """
    return "/" + str(rule).strip().strip("/")


def create_blueprint(*, withheld: Iterable[str] = ()) -> Blueprint:
    """Build the public blueprint with its routes attached.

    A FACTORY RATHER THAN A MODULE-LEVEL `public_bp`, for two reasons:

    1. Whether a path is ours to register is a configuration decision — the React
       frontend owns `/`, `/gallery` and `/contact` (`SPA_ROUTES` in
       app/config.py) — and a rule can only be added to a blueprint BEFORE it is
       first registered. A module-level blueprint would answer for the first
       application built in a process and raise AssertionError for the second, which
       is exactly what the test suite does.
    2. Endpoints are unchanged by the move: `public.participant_profile` and
       `public.media` are still what `url_for` resolves to.

    `withheld` is a set of paths the frontend holds. A withheld path is SKIPPED, not
    overridden: two rules for one path are resolved by registration order without a
    warning, and the loser silently stops existing. `PAGE_ROUTES` keeps listing all
    of them either way, and should — the sitemap is built from that table, and each
    is a real URL on this site whichever half serves it.
    """
    bp = Blueprint("public", __name__)
    held = {_normalise(rule) for rule in withheld}

    for rule, slug in PAGE_ROUTES:
        if _normalise(rule) in held:
            continue
        bp.add_url_rule(
            rule,
            endpoint=slug.replace("-", "_"),
            view_func=_render_cms_page(slug),
        )

    bp.add_url_rule("/batch-1/<slug>", view_func=participant_profile)
    bp.add_url_rule("/media/<path:filename>", view_func=media)
    return bp
