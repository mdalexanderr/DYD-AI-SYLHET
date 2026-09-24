"""TOTP verification. plan.md §12.1, step 4.1.

WHY THIS IS A MODULE AND NOT TWO LINES IN THE ROUTE
    `pyotp` is used in three places — enrolment in the seeder, the CLI reset, and
    now verification — and the drift window is the one parameter that has to agree
    between them. Enrolling with one window and verifying with another produces an
    authenticator that works intermittently, which is the worst possible failure
    mode for a second factor: it gets switched off.

WHY A DRIFT WINDOW AT ALL
    TOTP codes are derived from the clock. One step either side accepts a code for
    ±30 s, which absorbs the ordinary case of a phone whose clock is slightly slow
    and a user who types the code as it is about to roll over. Zero drift means
    regularly rejecting correct codes; a wide window would mean an intercepted code
    stays valid for minutes. One step is the conventional compromise.

    A REPLAYED CODE IS NOT BLOCKED HERE. Within the ±30 s window the same code can
    be presented twice. Blocking that needs per-account state (the last accepted
    step), which is worth adding when there is a login audit trail to check it
    against — and there now is, so `login_attempts` is the evidence if this ever
    matters. Recorded here rather than silently assumed.
"""

from __future__ import annotations

#: Steps either side of now, i.e. ±30 s with the standard 30-second period.
VALID_WINDOW = 1

#: The issuer shown in the authenticator app. Must match the seeder and the CLI, or
#: the same account appears twice in somebody's app.
ISSUER = "DYD AI Sylhet"


def verify_totp(
    secret: str | None, code: str | None, *, valid_window: int = VALID_WINDOW
) -> bool:
    """True when `code` is the current TOTP for `secret`.

    Returns False rather than raising for every malformed input. This is reached
    from a login form, so "the user typed a letter" and "the secret is corrupt" both
    have to end in a refused login, not a 500 — a 500 on the login route is an
    availability bug in the one route that has to stay up.
    """
    if not secret or not code:
        return False

    # Authenticator apps display codes as "123 456" and users paste the space.
    normalised = "".join(str(code).split())
    if not normalised.isdigit():
        return False

    try:
        import pyotp
    except ImportError:  # pragma: no cover — pyotp is a pinned dependency
        return False

    try:
        return bool(pyotp.TOTP(secret).verify(normalised, valid_window=valid_window))
    except Exception:  # noqa: BLE001
        # pyotp raises binascii.Error on a secret that is not valid base32, which is
        # what a truncated or hand-edited `twofa_secret` column looks like. A refused
        # login is the correct outcome; the cause is visible via `flask admin-reset-2fa`.
        return False


def provisioning_uri(secret: str, *, email: str, issuer: str = ISSUER) -> str:
    """The `otpauth://` URI an authenticator app scans.

    Lives here rather than in the CLI that first needed it, so the issuer string has
    exactly one definition — two definitions would mean the same admin account
    showing up as two entries in somebody's app.
    """
    import pyotp

    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


__all__ = ["ISSUER", "VALID_WINDOW", "provisioning_uri", "verify_totp"]
