"""The React frontend mount. docs/FRONTEND.md, app/routes/spa.py.

WHAT IS ACTUALLY AT RISK HERE
    Five things, none of them visible while they work:

    1. **The front page.** `/` is served from the build directory and rendered in the
       browser. If the bundle is missing or the mount is not registered, the front
       page of the site is a 404 — the most consequential page there is.

    2. **The Bangla 404 (§9.2).** This mount is the least specific rule in the app.
       Give it a catch-all and every mistyped URL answers 200 with the shell instead
       of the 404 page — for every visitor, on every path. `test_routes.py` and
       `test_public.py` assert that page separately; what is asserted here is that
       this mount did not take it away.

    2b. **Method-not-allowed.** The same greediness turns `GET /logout` into a 200 or
        a 404 where the site promises a 405, because a catch-all on GET answers
        before the POST-only route can. A security test in `test_auth.py` covers it
        from the other side.

    3. **The other Jinja pages.** `/course`, `/batch-1`, `/about`, `/privacy` and
       every participant profile are still rendered from the `pages` table. Two rules
       for one path are resolved by registration order without a warning, so a mount
       one segment too greedy deletes one silently.

    3b. **The routed pages.** `/gallery` and `/contact` are the frontend's, and they
        are the reason the mount is not just `/` any more. Each one is WITHDRAWN from
        the Jinja page table rather than shadowed, and each has to answer a direct
        request with the shell — a bookmark, a reload, a link opened in a new tab.

    4. **The asset URL.** The bundle must not be served from `/assets/`:
       `public/.htaccess` refuses that path at the Apache layer, so the default Vite
       layout works locally and 404s in production.

    5. **The security policy.** The React app loads Google Fonts and Unsplash images,
       so its shell carries a relaxed `Content-Security-Policy`. A policy set globally
       instead of on one response would apply that relaxation to every government page
       on the site.
"""

from __future__ import annotations

import re

import pytest

# The shell, as opposed to the Jinja layout. `layouts/base.html` has no #root
# element, so one string separates the two in a body assertion.
SHELL_MARKER = b'<div id="root">'

#: The pages the frontend router owns — `SPA_ROUTES` in app/config.py, route for
#: route against frontend/src/main.tsx.
SPA_PATHS = ("/", "/gallery", "/contact")

#: Every public page the Jinja site still owns (docs/FRONTEND.md). The three above are
#: not among them: the frontend holds those, and holds them exclusively.
JINJA_PATHS = ("/course", "/batch-1", "/about", "/privacy")


# ─────────────────────────────────────────────────────────────────────────────
# 1. The front page
# ─────────────────────────────────────────────────────────────────────────────


def test_the_front_page_is_the_react_shell(client):
    response = client.get("/")
    assert response.status_code == 200, (
        "app/static/spa/index.html is missing or the mount is not registered. "
        "Run `npm run build` in frontend/ — the output is committed, so a clean "
        "clone already has it."
    )
    assert SHELL_MARKER in response.data


def test_the_shell_is_never_cached_without_revalidation(client):
    """The shell names the current hashed bundle. A cached copy pins a stale build."""
    assert "no-cache" in client.get("/").headers["Cache-Control"]


def test_hashed_assets_are_served_and_immutable(client):
    body = client.get("/").data.decode()
    asset = re.search(r"/spa-assets/[A-Za-z0-9._-]+\.js", body)
    assert asset, (
        "the built index.html references no /spa-assets/ bundle. Either the build is "
        "stale, or vite.config.ts lost its assetsDir — and `/assets/` works here and "
        "404s on the server, because public/.htaccess refuses it."
    )

    response = client.get(asset.group(0))
    assert response.status_code == 200
    assert "immutable" in response.headers["Cache-Control"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. What the mount must NOT take over
# ─────────────────────────────────────────────────────────────────────────────


def test_an_unknown_path_is_still_the_404_page(client):
    """`SPA_ROUTES` is an allow-list, so an arbitrary path gets the shell only if
    somebody listed it — and answering with the shell would delete the 404 page."""
    response = client.get("/this-path-does-not-exist-8c1f")
    assert response.status_code == 404
    assert SHELL_MARKER not in response.data


def test_the_other_public_pages_are_not_shadowed(client):
    """These four are still rendered from the `pages` table. Whether each renders or
    404s depends on the page being published, which is not what this is about —
    `test_public.py` covers that. What it may never be is the React shell."""
    for path in JINJA_PATHS:
        response = client.get(path)
        assert SHELL_MARKER not in response.data, f"{path} returned the React shell"


def test_the_routed_pages_are_the_shell(client):
    """Every path in `SPA_ROUTES` must answer a DIRECT request with the shell. The
    client-side router cannot help here: a bookmark, a reload and a middle-click all
    arrive as a plain GET, and a page that only exists after a click is not a URL."""
    for path in SPA_PATHS:
        response = client.get(path)
        assert response.status_code == 200, f"{path} -> {response.status_code}"
        assert SHELL_MARKER in response.data, f"{path} did not return the shell"


def test_the_routed_pages_are_withheld_from_the_jinja_table(client, app):
    """WITHDRAWN, not shadowed. `public.gallery` must not exist at all: two rules for
    one path are resolved by registration order without a warning, and the loser
    stops existing — which is a page silently deleted by a config entry."""
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert "public.home" not in endpoints
    assert "public.gallery" not in endpoints
    assert "public.contact" not in endpoints
    assert {"spa.index", "spa.route_gallery", "spa.route_contact"} <= endpoints
    assert len([r for r in app.url_map.iter_rules() if r.rule == "/gallery"]) == 1


def test_health_and_the_admin_path_are_not_shadowed(client):
    """The same failure on paths that never consult the database: `/health` is what
    monitoring reads, and `/admin` must stay a 404 (§12.1)."""
    assert client.get("/health").status_code == 200
    assert client.get("/admin").status_code == 404
    assert SHELL_MARKER not in client.get("/admin").data


def test_a_post_only_route_still_answers_405_to_a_get(client):
    """`GET /logout` must be 405, not 404: the route exists and the method does not.

    This is the subtle half of mounting at the root. A GET catch-all matches the path
    before Werkzeug notices the POST-only rule, so the response becomes this
    blueprint's 404 instead of the site's 405 — and the 405 is the thing
    `test_auth.py` relies on to say logout cannot be CSRF'd by an `<img>` tag.
    """
    assert client.get("/logout").status_code == 405


# ─────────────────────────────────────────────────────────────────────────────
# 3. The relaxed policy stays on one route
# ─────────────────────────────────────────────────────────────────────────────


def test_the_shell_relaxes_csp_only_for_itself(client, app):
    """Google Fonts and Unsplash are what the relaxation is for. It must not appear
    anywhere else — least of all on a page carrying participant names."""
    shell_policy = client.get("/").headers["Content-Security-Policy"]
    assert "fonts.googleapis.com" in shell_policy
    assert "images.unsplash.com" in shell_policy

    site_policy = app.config["CONTENT_SECURITY_POLICY"]
    assert "fonts.googleapis.com" not in site_policy
    assert "images.unsplash.com" not in site_policy

    assert client.get("/health").headers["Content-Security-Policy"] == site_policy


# ─────────────────────────────────────────────────────────────────────────────
# 4. Missing files, missing builds, traversal
# ─────────────────────────────────────────────────────────────────────────────


def test_a_missing_asset_is_404_not_html(client):
    """Otherwise a typo'd asset URL returns HTML with a 200 and the browser reports a
    syntax error inside a file that is not JavaScript."""
    response = client.get("/spa-assets/does-not-exist.js")
    assert response.status_code == 404
    assert SHELL_MARKER not in response.data


def test_an_unbuilt_frontend_404s_instead_of_crashing(
    client, app, monkeypatch, tmp_path
):
    """A deploy that shipped without the bundle must degrade to a 404 on one route,
    not to a 500 whose traceback names the filesystem."""
    monkeypatch.setitem(app.config, "SPA_DIST_DIR", tmp_path)
    assert client.get("/").status_code == 404


def test_encoded_traversal_does_not_escape_the_build_directory(client):
    """`<path:filename>` reads from a directory named in config. Werkzeug normalises
    `..` before routing and send_from_directory resolves the remainder; this proves
    the pair holds when the caller tries harder than normal."""
    for attempt in (
        "/spa-assets/%2e%2e/run.py",
        "/spa-assets/..%2frun.py",
        "/spa-assets/%2e%2e%2f%2e%2e%2frun.py",
    ):
        response = client.get(attempt)
        assert response.status_code == 404, f"{attempt} -> {response.status_code}"
        assert b"create_app" not in response.data


# ─────────────────────────────────────────────────────────────────────────────
# 5. The mount is optional, and the path list decides ownership
# ─────────────────────────────────────────────────────────────────────────────


def _app_with(monkeypatch, **overrides):
    """A second application built with config overrides.

    The only way to exercise a decision taken while the app is being built — and it
    is deliberately one extra app, not a fixture, because building the app is the
    slow part of this suite.
    """
    from app import create_app
    from app.config import TestConfig

    for key, value in overrides.items():
        monkeypatch.setattr(TestConfig, key, value)
    return create_app("testing")


def _endpoints(app) -> set[str]:
    return {rule.endpoint for rule in app.url_map.iter_rules()}


def _owner(app, path: str) -> str | None:
    """Which endpoint answers `path`. The URL map, not a request: a second app built
    here has no migrated database, and a Jinja page reads `pages` on the way out — so
    who owns a path has to be answerable without touching the disk.
    """
    for rule in app.url_map.iter_rules():
        if str(rule) == path:
            return rule.endpoint
    return None


def test_the_mount_can_be_switched_off(monkeypatch):
    """`SPA_ENABLED=false` is the documented way to drop the frontend. A flag that has
    never been exercised is a flag that does not work — and switching it off has to
    give the front page back to the Jinja site rather than leave a hole at `/`."""
    app = _app_with(monkeypatch, SPA_ENABLED=False)
    assert "spa.index" not in _endpoints(app)
    assert _owner(app, "/") == "public.home"
    assert _owner(app, "/gallery") == "public.gallery"


def test_a_page_the_frontend_does_not_claim_stays_with_jinja(monkeypatch):
    """The list decides ownership both ways round. Drop `/gallery` from it and the
    Jinja page comes back — the mount does not quietly keep what config gave up."""
    app = _app_with(monkeypatch, SPA_ROUTES=("/",))
    assert _owner(app, "/gallery") == "public.gallery"
    assert "spa.route_gallery" not in _endpoints(app)


def test_a_prefixed_mount_takes_nothing_from_the_jinja_pages(monkeypatch):
    """`SPA_URL_PREFIX=/preview` moves the frontend's rules under the prefix. It is the
    escape hatch for rendering the React site beside the live one, so it must not
    carve `/gallery` out of the site it is parked beside."""
    app = _app_with(monkeypatch, SPA_URL_PREFIX="/preview")
    endpoints = _endpoints(app)
    assert "public.gallery" in endpoints
    assert "spa.route_gallery" in endpoints
    assert SHELL_MARKER in app.test_client().get("/preview/gallery").data


def test_a_non_root_relative_spa_route_is_refused(monkeypatch):
    """`galery` registers a rule that can never match, so the failure surfaces as a 404
    on a link in the header — several steps from the typo that caused it. Refused at
    boot, naming the setting."""
    with pytest.raises(RuntimeError, match="root-relative"):
        _app_with(monkeypatch, SPA_ROUTES=("/", "gallery"))
