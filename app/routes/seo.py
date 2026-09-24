"""sitemap.xml and robots.txt — routes 9 and 10. plan.md §6.2, §15.3, step 3.7.

THE SITEMAP IS A PRIVACY CONTROL, NOT AN SEO FEATURE
    Step 3.7's "Done when" says it plainly: "a non-consented participant's slug is
    ABSENT from the sitemap — this is a privacy test, not an SEO test." A sitemap is a
    list of everything a crawler should fetch, so one that is built from `Participant`
    rather than from `participant_service.list_published` is a published list of
    people who never agreed to be listed. It goes through the same consent boundary as
    every other public surface, for the same reason.

THE ROUTES ARE DERIVED, NOT WRITTEN OUT
    Page URLs come from `public.PAGE_ROUTES`, the same table the public routes are
    registered from. A hand-written list here would be a second place that knows which
    slugs are public, and the failure is a sitemap advertising a URL that 404s — or,
    worse, one that stays silent about a page nobody then ever finds.

CACHED FOR AN HOUR
    §3.7 asks for it, and it is the one public surface whose cost grows with the size
    of the cohort rather than the size of the page.
"""

from __future__ import annotations

import contextlib
from xml.sax.saxutils import escape

from flask import Blueprint, Response, current_app, request

from app.routes.public import PAGE_ROUTES
from app.services import page_service, participant_service

seo_bp = Blueprint("seo", __name__)
URL_PREFIX = None

#: One hour, per step 3.7.
SITEMAP_CACHE_SECONDS = 3600
SITEMAP_CACHE_KEY = "seo:sitemap"


def sitemap_payload() -> str:
    """The sitemap XML. Every URL in it comes from a consent-checked source."""
    root = request.url_root.rstrip("/")
    rule_for_slug = {slug: rule for rule, slug in PAGE_ROUTES}

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

    def _add(location: str, lastmod: str | None = None, priority: str = "0.5") -> None:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(location)}</loc>")
        if lastmod:
            lines.append(f"    <lastmod>{escape(lastmod)}</lastmod>")
        lines.append(f"    <priority>{priority}</priority>")
        lines.append("  </url>")

    # ── published pages ──
    for page in page_service.nav_pages() or []:
        rule = rule_for_slug.get(page.slug)
        if rule is None:
            # A published page with no route. Skipped rather than guessed at: a sitemap
            # entry for a URL that 404s is worse than a missing entry, because a
            # crawler will keep asking.
            continue
        lastmod = page.published_at.date().isoformat() if page.published_at else None
        _add(f"{root}{rule}", lastmod, "1.0" if page.slug == "home" else "0.7")

    # The home page is published and `show_in_nav` — but a home page that is published
    # while `show_in_nav` is false would be missing from `nav_pages`, so it is added
    # explicitly. The site root is the one URL a sitemap must never omit.
    home_rule = rule_for_slug.get("home")
    if home_rule and not any(f"<loc>{root}{home_rule}</loc>" in line for line in lines):
        home_page = page_service.get_page("home")
        if home_page is not None:
            lastmod = (
                home_page.published_at.date().isoformat() if home_page.published_at else None
            )
            _add(f"{root}{home_rule}", lastmod, "1.0")

    # ── consented participants only ──
    # `list_published` applies all four consent conditions. This is the line that
    # makes step 3.7's "Done when" true, and it is why the sitemap never queries the
    # model directly.
    for card in participant_service.list_published(sort="manual"):
        _add(f"{root}{card['href']}", None, "0.6")

    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def robots_payload() -> str:
    """robots.txt. Disallows the admin surface and the credential routes.

    BOTH `/admin/` AND THE CONFIGURED PREFIX ARE LISTED. §6.2 asks for both, and the
    reason is that `/admin/` is the guess somebody makes and `ops-sylhet` is the one
    that actually exists — listing only the first would be security theatre.

    A SITEMAP IS ADVERTISED. A robots file that hides the sitemap makes the crawl
    slower and tells a crawler nothing it could not learn by asking.
    """
    root = request.url_root.rstrip("/")
    prefix = "/" + str(current_app.config["ADMIN_URL_PREFIX"]).strip("/")

    return "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "# The admin surface. `/admin/` is the guess; the prefixed path is the real",
            "# one. Neither is linked from anywhere public.",
            "Disallow: /admin/",
            f"Disallow: {prefix}/",
            "Disallow: /login",
            "Disallow: /logout",
            "",
            "# Uploads are signature-gated and carry a year of immutable caching; there",
            "# is nothing here for a crawler to index.",
            "Disallow: /media/",
            "",
            f"Sitemap: {root}/sitemap.xml",
            "",
        ]
    )


@seo_bp.get("/sitemap.xml")
def sitemap():
    """Route 9. Cached for an hour; rebuilt on publish (step 4.13 invalidates it)."""
    from app.extensions import cache

    xml: str | None = None
    # A cache that is unavailable costs speed, not a page — the same reasoning as
    # stats_service. The failure is suppressed rather than raised, and the sitemap is
    # simply rebuilt.
    with contextlib.suppress(Exception):
        xml = cache.get(SITEMAP_CACHE_KEY)

    if not xml:
        xml = sitemap_payload()
        with contextlib.suppress(Exception):
            cache.set(SITEMAP_CACHE_KEY, xml, timeout=SITEMAP_CACHE_SECONDS)

    return Response(xml, mimetype="application/xml")


@seo_bp.get("/robots.txt")
def robots():
    """Route 10. Not cached: it is tiny, and it is the file a crawler reads first."""
    return Response(robots_payload(), mimetype="text/plain")


def invalidate_cache() -> None:
    """Drop the cached sitemap. Call from the publish and withdrawal paths.

    A withdrawn participant whose slug survives an hour in the sitemap is a privacy
    failure that nothing would report — the page is gone, the list of URLs is not.
    """
    from app.extensions import cache

    with contextlib.suppress(Exception):
        cache.delete(SITEMAP_CACHE_KEY)

