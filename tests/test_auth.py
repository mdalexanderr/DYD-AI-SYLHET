"""Admin authentication — steps 4.1 and 4.3. plan.md §12.1.

ONE TEST PER BEHAVIOUR STEP 4.1 NAMES, and the two cases its "Done when" insists on:
that the lockout blocks a CORRECT password, and that /admin is a 404 rather than a
redirect. Both of those are the failure a first implementation actually ships.

WHY CSRF IS SWITCHED OFF HERE
    Not because CSRF is optional — it is app-wide and the framework tests it. It is
    switched off so these tests are about authentication: scraping a token into every
    POST would make them fail for the wrong reason the day the token rendering
    changes, and a helper that silently stopped fetching a valid token would hide a
    real CSRF failure somewhere else. `WTF_CSRF_ENABLED` is restored afterwards.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func

PASSWORD = "correct-horse-battery-staple"
ADMIN_EMAIL = "Admin@Example.Test"  # deliberately mixed case — see _find_admin
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
    """The single admin account, 2FA off so the password path is testable alone."""
    from app.extensions import bcrypt
    from app.models import AdminUser

    user = AdminUser(
        email=ADMIN_EMAIL,
        password_hash=bcrypt.generate_password_hash(PASSWORD).decode("utf-8"),
        full_name_bn="প্রশাসক",
        is_active=True,
        twofa_enabled=False,
    )
    session.add(user)
    session.commit()
    return user


def _fresh(email: str = ADMIN_EMAIL):
    """Re-read the row, because a request commits in its own session.

    Without this the identity map hands back the pre-request values and the lockout
    tests pass or fail depending on fixture ordering.
    """
    from app.extensions import db
    from app.models import AdminUser

    db.session.expire_all()
    return db.session.execute(
        db.select(AdminUser).where(AdminUser.email == email)
    ).scalars().first()


def _attempt_count(*, successful: bool | None = None) -> int:
    from app.extensions import db
    from app.models import LoginAttempt

    stmt = db.select(func.count(LoginAttempt.id))
    if successful is not None:
        stmt = stmt.where(LoginAttempt.was_successful.is_(successful))
    return int(db.session.execute(stmt).scalar_one())


def _login(client, password: str = PASSWORD, email: str = "admin@example.test", **extra):
    return client.post(LOGIN_URL, data={"email": email, "password": password, **extra})


def _is_anonymous(client) -> bool:
    return client.get(ADMIN_URL).status_code == 302


# ─────────────────────────────────────────────────────────────────────────────
# 4.3 — the non-guessable path
# ─────────────────────────────────────────────────────────────────────────────
def test_admin_is_a_404_and_not_a_redirect(client, admin_user):
    """Step 4.3's "Done when". A redirect CONFIRMS the real path.

    A 302 to /ops-sylhet/login would hand an attacker the prefix S13 exists to
    hide — the whole point of a non-guessable path is that probing the obvious one
    tells you nothing.
    """
    response = client.get("/admin")

    assert response.status_code == 404
    assert "Location" not in response.headers, "a redirect leaked the real admin path"


def test_the_admin_surface_requires_a_login(client, admin_user):
    response = client.get(ADMIN_URL)

    assert response.status_code == 302
    assert LOGIN_URL in response.headers["Location"]


# ─────────────────────────────────────────────────────────────────────────────
# 4.1 — the five named behaviours
# ─────────────────────────────────────────────────────────────────────────────
def test_correct_credentials_log_in(client, admin_user, no_csrf):
    response = _login(client)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(ADMIN_URL)
    assert client.get(ADMIN_URL).status_code == 200


def test_a_wrong_password_is_refused(client, admin_user, no_csrf):
    response = _login(client, password="not-the-password")

    assert response.status_code == 401
    assert _is_anonymous(client), "a bad password produced an authenticated session"


def test_an_unknown_email_is_refused_and_indistinguishable(client, admin_user, no_csrf):
    """Same status and same message, so the form cannot be used to enumerate accounts.

    Compared on the FAILURE MESSAGE rather than on the raw document. The form echoes
    the submitted address back into the `value` attribute, which is the reader's own
    input and therefore differs by definition — comparing whole bodies would fail on a
    correct implementation, and the obvious way to make it pass would be to stop
    echoing the address, which makes the form worse to use. Normalising that one field
    out of the comparison is what keeps the test about account enumeration.
    """
    from app.routes.auth import BAD_CREDENTIALS_BN

    unknown = _login(client, email="nobody@example.test")
    wrong = _login(client, password="not-the-password")

    assert unknown.status_code == wrong.status_code == 401

    for response in (unknown, wrong):
        body = response.get_data(as_text=True)
        assert BAD_CREDENTIALS_BN in body, "a credential failure did not show the generic message"
        # The lockout sentence would confirm the account exists, so it must not appear
        # for either case.
        assert "লক করা হয়েছে" not in body


def test_every_attempt_is_recorded_including_successes(client, admin_user, no_csrf):
    _login(client, password="wrong")
    _login(client, password="wrong")
    _login(client)

    assert _attempt_count(successful=False) == 2
    assert _attempt_count(successful=True) == 1, (
        "successes were not recorded, so the log cannot answer 'was this account "
        "accessed from an address we do not recognise'"
    )


def test_three_failures_lock_the_account(client, admin_user, no_csrf):
    for _ in range(3):
        _login(client, password="wrong")

    assert _fresh().is_locked is True
    assert _fresh().locked_until is not None


def test_the_lockout_blocks_a_correct_password(client, admin_user, no_csrf):
    """Step 4.1's explicit "Done when", and the case a naive implementation misses.

    If the password were verified before the lockout, three failures would only
    slow an attacker down: the fourth attempt with the right password would succeed
    and the counter would never have stopped anything.
    """
    for _ in range(3):
        _login(client, password="wrong")

    response = _login(client)  # the CORRECT password

    assert response.status_code == 429
    assert _is_anonymous(client), "the lockout let a correct password through"


def test_a_locked_attempt_is_itself_recorded(client, admin_user, no_csrf):
    for _ in range(3):
        _login(client, password="wrong")
    before = _attempt_count()

    _login(client)

    assert _attempt_count() == before + 1


def test_a_successful_login_clears_the_failure_counter(client, admin_user, no_csrf):
    """Otherwise two failures today plus one next month would lock the account."""
    _login(client, password="wrong")
    _login(client, password="wrong")
    assert _fresh().failed_attempts == 2

    _login(client)

    assert _fresh().failed_attempts == 0
    assert _fresh().is_locked is False


def test_the_login_form_asks_for_a_totp_code(client, admin_user):
    body = client.get(LOGIN_URL).get_data(as_text=True)

    assert 'name="totp"' in body
    assert 'name="password"' in body
    # The form must be noindexed: a URL that exists only to accept credentials has
    # no business in a search result.
    assert "noindex" in body


# ─────────────────────────────────────────────────────────────────────────────
# 4.1 — the second factor
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def admin_with_2fa(session, app):
    """A second account enrolled in TOTP. Returns (email, secret)."""
    import pyotp

    from app.extensions import bcrypt
    from app.models import AdminUser
    from app.security.crypto import encrypt_secret

    secret = pyotp.random_base32()
    session.add(
        AdminUser(
            email="2fa@example.test",
            password_hash=bcrypt.generate_password_hash(PASSWORD).decode("utf-8"),
            full_name_bn="২এফএ প্রশাসক",
            is_active=True,
            twofa_enabled=True,
            twofa_secret=encrypt_secret(secret, app.config["SECRET_KEY"]),
        )
    )
    session.commit()
    return "2fa@example.test", secret


def test_a_correct_password_alone_is_not_enough_when_2fa_is_enrolled(
    client, admin_with_2fa, no_csrf
):
    email, _ = admin_with_2fa

    response = _login(client, email=email)

    assert response.status_code == 401
    assert _is_anonymous(client)


def test_a_wrong_totp_code_is_refused(client, admin_with_2fa, no_csrf):
    email, _ = admin_with_2fa

    response = _login(client, email=email, totp="000000")

    assert response.status_code == 401
    assert _is_anonymous(client)


def test_the_right_totp_code_completes_the_login(client, admin_with_2fa, no_csrf):
    import pyotp

    email, secret = admin_with_2fa

    response = _login(client, email=email, totp=pyotp.TOTP(secret).now())

    assert response.status_code == 302
    assert client.get(ADMIN_URL).status_code == 200


def test_a_corrupt_2fa_secret_refuses_rather_than_500s(client, session, no_csrf):
    """A changed SECRET_KEY must not turn the login route into a 500.

    The login route is the one that has to stay up; failing closed with a message
    the operator can act on is the whole job.
    """
    from app.extensions import bcrypt
    from app.models import AdminUser

    session.add(
        AdminUser(
            email="broken@example.test",
            password_hash=bcrypt.generate_password_hash(PASSWORD).decode("utf-8"),
            full_name_bn="ভাঙা",
            twofa_enabled=True,
            twofa_secret="not-a-fernet-token",
        )
    )
    session.commit()

    response = _login(client, email="broken@example.test", totp="123456")

    assert response.status_code == 401
    assert _is_anonymous(client)


# ─────────────────────────────────────────────────────────────────────────────
# Logout, and the redirect target
# ─────────────────────────────────────────────────────────────────────────────
def test_logout_ends_the_session(client, admin_user, no_csrf):
    _login(client)
    assert client.get(ADMIN_URL).status_code == 200

    client.post("/logout")

    assert _is_anonymous(client)


def test_logout_is_not_reachable_by_get(client, admin_user, no_csrf):
    """A GET logout is a CSRF target: `<img src=".../logout">` signs the admin out."""
    _login(client)

    assert client.get("/logout").status_code == 405
    assert client.get(ADMIN_URL).status_code == 200, "the GET logout still worked"


@pytest.mark.parametrize(
    "hostile",
    ("//evil.example/steal", "/\\evil.example", "https://evil.example", "http://evil.example"),
)
def test_an_offsite_next_target_is_ignored(client, admin_user, no_csrf, hostile):
    """An open redirect on a login form is how credential phishing gets a trusted URL."""
    response = client.post(
        LOGIN_URL, data={"email": "admin@example.test", "password": PASSWORD, "next": hostile}
    )

    assert response.status_code == 302
    location = response.headers["Location"]
    assert "evil.example" not in location
    assert location.endswith(ADMIN_URL)


def test_a_relative_next_target_is_honoured(client, admin_user, no_csrf):
    response = client.post(
        LOGIN_URL, data={"email": "admin@example.test", "password": PASSWORD, "next": "/x/y"}
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/x/y")


def test_a_logged_in_admin_visiting_login_is_sent_on(client, admin_user, no_csrf):
    _login(client)

    response = client.get(LOGIN_URL)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(ADMIN_URL)
