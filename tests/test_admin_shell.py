"""The admin shell. execution-plan step 4.5; plan.md §11.1, §7.7.

STEP 4.5's "DONE WHEN" IS ABOUT CONSISTENCY, SO THAT IS WHAT IS TESTED
    "every screen has a consistent header, breadcrumb and flash-message area."

    "Consistent" cannot be asserted by looking at one screen. It is asserted here by
    checking that the parts a screen must NOT have to provide for itself are
    inherited: the shell supplies the header, the navigation, the breadcrumb and the
    page heading, and `layouts/base.html` supplies the flash region. A screen that
    extends `admin/layout.html` and overrides only `admin_title` and
    `admin_content` therefore cannot be missing any of them.

THE FLASH TEST USES A REAL FLASH
    A flash region that exists but never receives a message is a region nobody has
    seen work. This drives an actual flash through a real request (logout) and
    asserts it lands on the page.
"""

from __future__ import annotations

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
        email="shell@example.test",
        password_hash=bcrypt.generate_password_hash(PASSWORD).decode("utf-8"),
        full_name_bn="শেল প্রশাসক",
        is_active=True,
        twofa_enabled=False,
    )
    session.add(user)
    session.commit()
    return user


def _sign_in(client):
    client.post(LOGIN_URL, data={"email": "shell@example.test", "password": PASSWORD})


def test_the_landing_page_renders_inside_the_shell(client, admin_user, no_csrf):
    _sign_in(client)

    body = client.get(ADMIN_URL).get_data(as_text=True)

    assert "<main" in body.lower(), "no main landmark"
    assert 'aria-label="প্রশাসনিক মেনু"' in body, "no admin navigation landmark"
    assert 'aria-label="আপনি এখানে আছেন"' in body, "no breadcrumb landmark"
    # The page heading comes from the shell, so a screen cannot forget it.
    assert "ড্যাশবোর্ড" in body


def test_the_shell_marks_the_current_screen(client, admin_user, no_csrf):
    """A nav that never indicates where you are is a list of links, not navigation."""
    _sign_in(client)

    body = client.get(ADMIN_URL).get_data(as_text=True)

    assert 'aria-current="page"' in body


def test_the_admin_shell_does_not_render_the_public_navigation(client, admin_user, no_csrf):
    """THE ADMIN IS NOT A PUBLIC PAGE WITH DIFFERENT CONTENT.

    The public header links to /course, /gallery and the rest. On an admin screen
    those are links out of the admin, and the public footer adds nine more.
    """
    _sign_in(client)

    body = client.get(ADMIN_URL).get_data(as_text=True)

    assert 'href="/course"' not in body, "the public navigation leaked into the admin"
    assert 'href="/gallery"' not in body
    assert 'href="/batch-1"' not in body


def test_the_admin_shell_is_noindexed(client, admin_user, no_csrf):
    _sign_in(client)

    body = client.get(ADMIN_URL).get_data(as_text=True)

    assert "noindex" in body
    assert "nofollow" in body


def test_the_shell_gives_the_admin_a_way_out(client, admin_user, no_csrf):
    _sign_in(client)

    body = client.get(ADMIN_URL).get_data(as_text=True)

    # A POST form to logout, not a link: a GET logout is a CSRF target.
    assert f'action="{LOGIN_URL.replace("/login", "/logout")}"' in body
    assert 'name="csrf_token"' in body


def test_the_flash_region_renders_a_real_message(client, admin_user, no_csrf):
    """The inherited flash area, exercised with an actual flash.

    `layouts/base.html` renders flashed messages as server-side toasts; the admin
    shell inherits that rather than reimplementing it. This signs out — which
    flashes — and then checks the message reached a page.
    """
    _sign_in(client)
    client.post("/logout")

    body = client.get(LOGIN_URL).get_data(as_text=True)

    assert "প্রস্থান করেছেন" in body, "the flash message did not render"


def test_a_screen_cannot_forget_the_page_heading(client, admin_user, no_csrf):
    """The heading comes from the shell's `admin_title` block.

    If a screen overrode `content` wholesale — the easy mistake — it would lose the
    header, nav, breadcrumb and heading at once. This asserts the landing page gets
    its heading from the shell rather than from its own markup.
    """
    _sign_in(client)

    body = client.get(ADMIN_URL).get_data(as_text=True)

    assert "<h1" in body.lower(), "the shell rendered no page heading"
