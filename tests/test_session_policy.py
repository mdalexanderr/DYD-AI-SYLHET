"""Session policy (4.2) and the admin IP allowlist (4.4). plan.md §12.1, §12.3.

THE ONE THAT MATTERS MOST
    `test_the_absolute_limit_ends_an_active_session`. Flask's cookie expiry is
    recomputed on every write to the session, and the server writes on every
    authenticated request — so `PERMANENT_SESSION_LIFETIME` on its own gives 8 hours
    of INACTIVITY, not 8 hours absolute. An admin who clicked something every few
    hours would never be signed out. That test keeps the session warm (idle = 0) so
    only the absolute limit can end it.
"""

from __future__ import annotations

import time

import pytest

PASSWORD = "correct-horse-battery-staple"
ADMIN_URL = "/ops-sylhet/"
LOGIN_URL = "/login"


@pytest.fixture
def no_csrf(app):
    previous = app.config.get("WTF_CSRF_ENABLED")
    app.config["WTF_CSRF_ENABLED"] = False
    yield
    app.config["WTF_CSRF_ENABLED"] = previous


@pytest.fixture
def admin_user(session):
    from app.extensions import bcrypt
    from app.models import AdminUser

    user = AdminUser(
        email="admin@example.test",
        password_hash=bcrypt.generate_password_hash(PASSWORD).decode("utf-8"),
        full_name_bn="প্রশাসক",
        is_active=True,
        twofa_enabled=False,
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture
def allowlist(app):
    """Set `ADMIN_IP_ALLOWLIST`, restoring the previous value afterwards."""
    previous = app.config.get("ADMIN_IP_ALLOWLIST")

    def _set(value):
        app.config["ADMIN_IP_ALLOWLIST"] = value

    yield _set
    app.config["ADMIN_IP_ALLOWLIST"] = previous


def _login(client):
    return client.post(LOGIN_URL, data={"email": "admin@example.test", "password": PASSWORD})


def _age(client, *, idle=None, alive=None):
    """Backdate the session stamps — the only way to age a session in a test.

    `alive` sets when the session STARTED; `idle` sets when it was last used. They are
    separate so a test can hold one constant while moving the other, which is exactly
    the distinction between the two limits.
    """
    with client.session_transaction() as sess:
        if idle is not None:
            sess["last_seen"] = time.time() - idle
        if alive is not None:
            sess["session_started_at"] = time.time() - alive


# ─────────────────────────────────────────────────────────────────────────────
# 4.2 — the idle limit
# ─────────────────────────────────────────────────────────────────────────────
def test_a_fresh_session_is_allowed(client, admin_user, no_csrf):
    _login(client)

    assert client.get(ADMIN_URL).status_code == 200


def test_a_session_inside_the_idle_limit_survives(client, admin_user, no_csrf):
    _login(client)
    _age(client, idle=60)

    assert client.get(ADMIN_URL).status_code == 200


def test_an_idle_session_is_ended(client, admin_user, no_csrf):
    """Step 4.2's "Done when": an idle session is rejected."""
    _login(client)
    _age(client, idle=2000)  # past the 1800 s default

    response = client.get(ADMIN_URL)

    assert response.status_code == 302
    assert LOGIN_URL in response.headers["Location"]


def test_an_ended_session_really_is_anonymous(client, admin_user, no_csrf):
    """A redirect is not proof of anything — the session must actually be gone."""
    _login(client)
    _age(client, idle=2000)
    client.get(ADMIN_URL)  # triggers the expiry

    assert client.get(ADMIN_URL).status_code == 302


def test_the_idle_limit_is_read_from_config(client, admin_user, no_csrf, app):
    """Hard-coding 30 minutes would pass every test above and ignore the setting."""
    _login(client)
    _age(client, idle=120)

    previous = app.config["SESSION_IDLE_SECONDS"]
    app.config["SESSION_IDLE_SECONDS"] = 60
    try:
        assert client.get(ADMIN_URL).status_code == 302
    finally:
        app.config["SESSION_IDLE_SECONDS"] = previous


# ─────────────────────────────────────────────────────────────────────────────
# 4.2 — the absolute limit
# ─────────────────────────────────────────────────────────────────────────────
def test_the_absolute_limit_ends_an_active_session(client, admin_user, no_csrf):
    """THE ONE A NAIVE IMPLEMENTATION MISSES.

    The session is kept perfectly warm (idle = 0), so the idle check can never fire.
    Only the absolute limit, taken once at login and never refreshed, can end it.
    Without a separate timestamp this request would return 200 and the "8 hours
    absolute" claim in §12.1 would be false.
    """
    _login(client)
    _age(client, idle=0, alive=30000)  # past the 28800 s default

    response = client.get(ADMIN_URL)

    assert response.status_code == 302
    assert LOGIN_URL in response.headers["Location"]


def test_a_session_inside_the_absolute_limit_survives(client, admin_user, no_csrf):
    _login(client)
    _age(client, idle=0, alive=60)

    assert client.get(ADMIN_URL).status_code == 200


def test_a_session_predating_the_policy_is_adopted_not_ended(client, admin_user, no_csrf):
    """Deploying the policy must not sign the admin out mid-task.

    A session created before this code existed has no `session_started_at`. Adopting
    it on first sight is one line, and the alternative is that shipping this feature
    logs the only admin out of whatever they were halfway through.
    """
    _login(client)
    with client.session_transaction() as sess:
        assert "session_started_at" not in sess
        sess.pop("last_seen", None)

    assert client.get(ADMIN_URL).status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 4.4 — the optional IP allowlist
# ─────────────────────────────────────────────────────────────────────────────
def test_an_empty_allowlist_leaves_everything_alone(client, admin_user, allowlist):
    """EMPTY MEANS OFF. Reading it as "deny everything" would lock an admin out of any
    deployment that never configured the setting, fixable only from a shell."""
    allowlist([])

    assert client.get(LOGIN_URL, environ_overrides={"REMOTE_ADDR": "203.0.113.7"}).status_code == 200


def test_a_non_matching_ip_is_refused(client, admin_user, allowlist):
    allowlist(["10.0.0.0/8"])

    response = client.get(LOGIN_URL, environ_overrides={"REMOTE_ADDR": "203.0.113.7"})

    assert response.status_code == 403


def test_a_matching_ip_is_allowed(client, admin_user, allowlist):
    allowlist(["203.0.113.0/24"])

    response = client.get(LOGIN_URL, environ_overrides={"REMOTE_ADDR": "203.0.113.7"})

    assert response.status_code == 200


def test_a_bare_address_without_a_prefix_is_accepted(client, admin_user, allowlist):
    """`203.0.113.7` is how people write a single host. It must not raise."""
    allowlist(["203.0.113.7"])

    assert client.get(LOGIN_URL, environ_overrides={"REMOTE_ADDR": "203.0.113.7"}).status_code == 200


def test_a_malformed_entry_denies_without_a_500(client, admin_user, allowlist):
    """A typo in .env must not break the surface used to fix it."""
    allowlist(["10.0.0.0/8", "not-an-ip"])

    response = client.get(LOGIN_URL, environ_overrides={"REMOTE_ADDR": "203.0.113.7"})

    assert response.status_code == 403
    assert response.status_code != 500


def test_the_public_site_is_never_blocked_by_the_allowlist(client, allowlist):
    """The allowlist guards the admin surface, not the website.

    The 40 KB of public pages have no reason to be unavailable because the admin
    forgot to add their home address.
    """
    allowlist(["10.0.0.0/8"])

    assert client.get("/health", environ_overrides={"REMOTE_ADDR": "203.0.113.7"}).status_code == 200
