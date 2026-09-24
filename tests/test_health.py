"""`/health` must be able to report failure. execution-plan step 3.8.

3.8's "DONE WHEN" IS ABOUT THE FAILURE, NOT THE SUCCESS
    "/health — JSON: {"db":"ok","css":"ok"}. This is what UptimeRobot watches and what
    the deploy verifies. Done when: it reports `db: fail` when the database is
    unreachable."

    An endpoint that only ever returns "ok" is an endpoint that cannot fail, which is
    the same as having no monitoring at all — and the failure branch is the half that
    is written and never executed. Both halves are asserted here.
"""

from __future__ import annotations


def test_health_reports_ok_when_the_database_answers(client):
    body = client.get("/health").get_json()

    assert body["db"] == "ok"
    assert body["css"] == "ok"


def test_health_still_answers_200_when_the_database_is_unreachable(client, monkeypatch):
    """A 503 would be indistinguishable from the process being down.

    The contract in `app/routes/api.py` is deliberate: a 200 with `"db": "fail"` means
    "the app is alive and something underneath it is wrong", so an uptime probe sees
    it and a human reads the body. 503 would look identical to a dead server, which is
    the less useful of the two answers.
    """
    from sqlalchemy.exc import OperationalError

    from app.extensions import db

    def _unreachable(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(db.session, "execute", _unreachable)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json()["db"] == "fail"


def test_health_reports_the_environment_and_the_name(client):
    """The shape is a contract, not an accident — the deploy asserts on it."""
    body = client.get("/health").get_json()

    assert set(body) >= {"db", "css", "env", "name"}
    assert body["env"] == "testing" or isinstance(body["env"], str)


def test_health_is_not_blocked_by_the_admin_allowlist(client, app):
    """Monitoring must not depend on the admin being reachable.

    `/health` is not under the admin prefix and is deliberately excluded from the
    allowlist, so an operator who locks the admin down to one office address does not
    also blind their monitoring.
    """
    previous = app.config.get("ADMIN_IP_ALLOWLIST")
    app.config["ADMIN_IP_ALLOWLIST"] = ("10.0.0.0/8",)
    try:
        response = client.get("/health", environ_overrides={"REMOTE_ADDR": "203.0.113.7"})
    finally:
        app.config["ADMIN_IP_ALLOWLIST"] = previous

    assert response.status_code == 200
    assert response.get_json()["db"] == "ok"


def test_health_reports_a_missing_stylesheet_as_a_failure(client, app, tmp_path):
    """§17.3 step 5 — the deploy pre-flight exists because of this failure mode.

    A truncated or missing `app.css` is not a database problem, but it is the other
    thing that makes the site look broken while the process reports healthy.
    """
    previous = app.config["APP_CSS_PATH"]
    app.config["APP_CSS_PATH"] = str(tmp_path / "not-a-stylesheet.css")
    try:
        body = client.get("/health").get_json()
    finally:
        app.config["APP_CSS_PATH"] = previous

    assert body["css"] == "fail"
    assert body["db"] == "ok", "a missing stylesheet must not be reported as a database fault"
