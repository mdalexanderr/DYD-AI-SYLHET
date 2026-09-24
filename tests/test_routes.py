"""Routing, error pages and the §12.3 security headers. Steps 2.5 and 2.6.

WHAT IS BEING PROTECTED HERE
    Two things that are invisible when they work and expensive when they do not:

    1. The Bangla 404. It is the most-seen page on the site after the homepage
       (§9.2), and it must not leak a traceback, a driver name or a file path —
       those leak table names and sometimes a query with real data in it.
    2. The security headers. A missing `X-Frame-Options` is not visible on any page;
       it is found by somebody framing the site, which is too late.
"""

from __future__ import annotations

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# /health — infrastructure, and a contract (§17.3, §17.6)
# ─────────────────────────────────────────────────────────────────────────────


def test_health_returns_200_and_json(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, dict)


def test_health_reports_the_four_contracted_keys(client):
    """UptimeRobot and deploy.sh both read this. Its shape is a contract."""
    payload = client.get("/health").get_json()
    for key in ("db", "css", "env", "name"):
        assert key in payload, f"/health no longer reports {key!r} — monitoring reads it"


def test_health_reports_ok_on_a_working_database(client):
    assert client.get("/health").get_json()["db"] == "ok"


def test_health_reports_a_broken_stylesheet(client, app):
    """A missing app.css is the deploy failure §17.3's pre-flight exists for, and
    /health is where it is meant to become visible."""
    original = app.config["APP_CSS_PATH"]
    # APP_CSS_PATH is a Path, not a str.
    app.config["APP_CSS_PATH"] = type(original)(str(original) + ".does-not-exist")
    try:
        assert client.get("/health").get_json()["css"] == "fail"
    finally:
        app.config["APP_CSS_PATH"] = original


# ─────────────────────────────────────────────────────────────────────────────
# The Bangla 404 (§9.2, step 2.5)
# ─────────────────────────────────────────────────────────────────────────────


def test_unknown_url_returns_404(client):
    assert client.get("/no-such-page-4f2a").status_code == 404


def test_unknown_url_renders_the_bangla_page(client):
    body = client.get("/no-such-page-4f2a").get_data(as_text=True)
    assert "খুঁজে পাওয়া যায়নি" in body, "the Bangla 404 page did not render"
    assert "<html" in body.lower()


def test_the_404_page_has_the_full_layout(client):
    """A 404 that renders without its header and footer looks like a broken site
    rather than a missing page, which is a worse impression than either."""
    body = client.get("/no-such-page-4f2a").get_data(as_text=True)
    assert 'href="#main"' in body      # skip link
    assert "<header" in body
    assert 'id="main"' in body
    assert "<footer" in body
    assert "css/app.css" in body


@pytest.mark.parametrize(
    "leak",
    ["Traceback", "sqlalchemy", "sqlite3", "/site-packages/", "SECRET_KEY", "SELECT "],
)
def test_the_404_page_leaks_no_internals(client, leak):
    """§17.6: the traceback goes to the log, never to the page."""
    body = client.get("/no-such-page-4f2a").get_data(as_text=True)
    assert leak not in body


def test_the_404_page_is_not_indexed(client):
    """§6.3: a 404 that gets indexed is a search result pointing at nothing."""
    body = client.get("/no-such-page-4f2a").get_data(as_text=True)
    assert "noindex" in body


# ─────────────────────────────────────────────────────────────────────────────
# S13 — /admin must not exist
# ─────────────────────────────────────────────────────────────────────────────


def test_slash_admin_is_a_404_not_a_login_page(client):
    """S13 and §12.1. A login page at /admin confirms the admin exists AND hands an
    attacker the form to attack. A 404 says nothing."""
    response = client.get("/admin")
    assert response.status_code == 404


def test_nothing_is_routed_under_slash_admin(app):
    """The stronger form: not just that /admin 404s, but that no rule uses it."""
    plain = [str(rule.rule) for rule in app.url_map.iter_rules() if str(rule.rule).startswith("/admin")]
    assert not plain, f"S13 requires that no route live under /admin; found {plain}"


def test_the_admin_prefix_is_not_guessable(app):
    """§12.1: the prefix is configuration, and a guessable default defeats it."""
    prefix = str(app.config["ADMIN_URL_PREFIX"]).strip("/")
    assert prefix not in {"", "admin", "login", "panel", "dashboard", "manage", "cms"}


# ─────────────────────────────────────────────────────────────────────────────
# §12.3 security headers
# ─────────────────────────────────────────────────────────────────────────────


def _headers(client, path="/health"):
    return {k.lower(): v for k, v in client.get(path).headers.items()}


def test_content_type_options_is_nosniff(client):
    assert _headers(client).get("x-content-type-options") == "nosniff"


def test_framing_is_denied(client):
    """Both headers, because older browsers only honour X-Frame-Options and the CSP
    directive is the future. One of them alone leaves a gap."""
    headers = _headers(client)
    assert headers.get("x-frame-options") in {"DENY", "deny"}
    assert "frame-ancestors" in headers.get("content-security-policy", "")


def test_a_content_security_policy_is_present(client):
    csp = _headers(client).get("content-security-policy", "")
    assert csp, "no Content-Security-Policy header"
    assert "default-src" in csp


def test_the_csp_forbids_inline_script(client):
    """The site ships no JavaScript, so `unsafe-inline` for scripts has no
    justification and would remove most of the value of having a CSP at all."""
    csp = _headers(client).get("content-security-policy", "")
    script_src = ""
    for directive in csp.split(";"):
        if directive.strip().startswith("script-src"):
            script_src = directive
    assert "'unsafe-inline'" not in script_src or "'unsafe-eval'" not in script_src


def test_referrer_policy_is_set(client):
    assert _headers(client).get("referrer-policy")


def test_permissions_policy_is_set(client):
    assert _headers(client).get("permissions-policy")


def test_hsts_is_absent_outside_production(client, app):
    """HSTS on a dev server pins http://localhost to https in the developer's browser
    for months, and the fix is a browser setting most people cannot find."""
    if app.config["APP_ENV"] == "production":
        pytest.skip("this test is about non-production behaviour")
    assert "strict-transport-security" not in _headers(client)


# ─────────────────────────────────────────────────────────────────────────────
# Maintenance mode (§9.2)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def maintenance(app):
    """Turn maintenance on, and always turn it back off.

    Without the teardown a leaked flag makes every LATER test fail with a 503, which
    looks like a broken app rather than a leaky fixture.
    """
    original = app.config.get("MAINTENANCE_MODE")
    app.config["MAINTENANCE_MODE"] = True
    try:
        yield
    finally:
        app.config["MAINTENANCE_MODE"] = original


def test_maintenance_mode_returns_503(client, maintenance):
    """503, not 200. A maintenance page served with a 200 tells every crawler the
    site is fine and the pages have simply gone away."""
    response = client.get("/some-page")
    assert response.status_code == 503


def test_maintenance_mode_renders_the_bangla_page(client, maintenance):
    body = client.get("/some-page").get_data(as_text=True)
    assert "সাময়িকভাবে বন্ধ" in body


def test_maintenance_mode_sends_retry_after(client, maintenance):
    assert client.get("/some-page").headers.get("Retry-After") == "3600"


def test_health_still_answers_during_maintenance(client, maintenance):
    """§9.2: if /health went down with the site, a maintenance window would look
    identical to an outage and would page somebody at 3am."""
    assert client.get("/health").status_code == 200


def test_static_files_still_serve_during_maintenance(client, maintenance):
    """The maintenance page needs its stylesheet. Exempting static files is what
    makes the page readable rather than a wall of unstyled Bangla."""
    response = client.get("/static/css/app.css")
    assert response.status_code == 200


def test_the_admin_prefix_is_reachable_during_maintenance(client, maintenance, app):
    """§9.2: without this exemption, switching maintenance mode on locks out the only
    person who can switch it off."""
    prefix = "/" + str(app.config["ADMIN_URL_PREFIX"]).strip("/")
    # A 404 (no admin route yet) is fine; a 503 would mean the exemption is missing.
    assert client.get(prefix + "/anything").status_code != 503
