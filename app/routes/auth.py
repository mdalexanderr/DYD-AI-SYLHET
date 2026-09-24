"""Admin authentication — routes 14 and 15. plan.md §12.1, step 4.1.

THE ORDER OF THE CHECKS IS THE SECURITY DESIGN
    1. THE LOCKOUT IS CHECKED BEFORE THE PASSWORD. A lockout that a correct
       password can walk through is not a lockout, it is a delay. Step 4.1's
       "Done when" names this case specifically because it is the one a naive
       implementation gets wrong: verify the password first, and an attacker
       holding a leaked password is never actually stopped by the attempt counter.
    2. `login_attempts` RECORDS EVERY ATTEMPT, successes included. Recording only
       failures leaves the log unable to answer "was this account accessed from an
       address we do not recognise", which is the question anybody actually asks.
    3. THE SESSION IS CLEARED BEFORE `login_user`. Flask's default session is a
       signed cookie, so the "session id" is the cookie's contents; without a
       clear, a value planted pre-login survives into the authenticated session.
       That is session fixation, and it is a one-line fix here and nowhere else.

ONE GENERIC FAILURE MESSAGE, ONE SPECIFIC ONE
    A wrong email, a wrong password and a wrong TOTP code all produce the same
    Bangla sentence, so the response does not reveal which half was wrong. The
    lockout is the deliberate exception: it names the state and the minutes left,
    because an admin locked out of the only account cannot tell a forgotten
    password from a broken deployment, and a generic refusal is how that becomes a
    phone call at 11pm. The cost is that a locked account is distinguishable from
    an unknown one. Accepted knowingly: there is one account (§10.1), its existence
    is not a secret, and this whole surface sits behind a non-guessable prefix.
"""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func, select

from app.extensions import bcrypt, db, login_manager
from app.models import AdminUser, LoginAttempt
from app.security import audit
from app.security.crypto import SecretDecryptionError, decrypt_secret
from app.security.totp import verify_totp

auth_bp = Blueprint("auth", __name__)
URL_PREFIX = None

#: One sentence for every credential failure. See the module docstring.
BAD_CREDENTIALS_BN = "ইমেইল, পাসওয়ার্ড বা ২-ধাপের কোড সঠিক নয়।"


@login_manager.unauthorized_handler
def _unauthorized():
    """Send an anonymous visitor to the login form, remembering where they were going.

    Declared here rather than by setting `login_manager.login_view` in extensions.py
    so the destination lives next to the only login route that exists. `next` is kept
    only for a GET: replaying a POST after logging in would silently repeat whatever
    that POST was about to do, which is a worse surprise than losing the form.
    """
    if request.method != "GET":
        return redirect(url_for("auth.login"))
    return redirect(url_for("auth.login", next=request.full_path))


def _client_ip() -> str | None:
    """The client address, honouring Passenger's forwarding header.

    Same rule as `audit._current_ip`, for the same reason: the app sits behind
    Passenger and is not reachable directly, so `remote_addr` is the proxy.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return request.remote_addr or None


def _safe_next() -> str | None:
    """A same-site relative redirect target, or None.

    Rejects anything absolute and anything protocol-relative. `//evil.example` is a
    valid-looking relative URL that browsers treat as absolute, which is the version
    of this bug that survives a naive `startswith("/")` check. A leading backslash is
    the second half of the same trick, because some browsers normalise `\\` to `/`.
    """
    target = request.form.get("next") or request.args.get("next")
    if not target or not isinstance(target, str):
        return None
    if not target.startswith("/") or target.startswith(("//", "/\\")):
        return None
    return target


def _record_attempt(
    email: str | None, ip: str | None, *, successful: bool, reason: str | None = None
) -> None:
    """Write a `login_attempts` row. The caller commits — this never does.

    Kept in the same transaction as the counter update, so the attempt log and the
    lockout state can never disagree about how many attempts have been made.
    """
    user_agent = None
    if request.user_agent is not None and request.user_agent.string:
        user_agent = request.user_agent.string[:255]

    db.session.add(
        LoginAttempt(
            email=(email or None),
            ip=ip,
            user_agent=user_agent,
            was_successful=successful,
            failure_reason=reason,
        )
    )


def _find_admin(email: str):
    """The admin by email, case-insensitively.

    `func.lower` rather than trusting the stored casing: addresses are
    case-insensitive in practice, and an admin who typed a capital letter at
    enrolment would otherwise find themselves unable to log in at all.
    """
    if not email:
        return None
    stmt = select(AdminUser).where(func.lower(AdminUser.email) == email.lower())
    return db.session.execute(stmt).scalars().first()


def _verify_second_factor(admin) -> tuple[bool, str | None]:
    """(ok, error_code). Returns (True, None) when no second factor is required.

    A decryption failure is reported as its own reason rather than as a bad code,
    because the fix is completely different: one means "retype the code", the other
    means "run `flask admin-reset-2fa`". Collapsing them would hide a changed
    SECRET_KEY behind a message telling the admin to check their phone.
    """
    required = bool(admin.twofa_enabled) or bool(current_app.config["ADMIN_2FA_REQUIRED"])
    if not required:
        return True, None

    if not admin.twofa_secret:
        # Required but nothing is enrolled. Not a credential failure — there is no
        # credential to fail.
        return False, "no_secret_enrolled"

    try:
        secret = decrypt_secret(admin.twofa_secret, current_app.config["SECRET_KEY"])
    except SecretDecryptionError:
        current_app.logger.error(
            "login: could not decrypt the 2FA secret for the admin account — "
            "SECRET_KEY has probably changed"
        )
        return False, "secret_undecryptable"

    return verify_totp(secret, request.form.get("totp")), "bad_totp"


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Route 14. Password, then TOTP, behind an attempt lockout."""
    if current_user.is_authenticated:
        return redirect(_safe_next() or url_for("admin.index"))

    email = (request.form.get("email") or "").strip()
    next_target = _safe_next()

    if request.method != "POST":
        return render_template("admin/login.html", email=email, next=next_target)

    ip = _client_ip()
    admin = _find_admin(email)

    # (1) THE LOCKOUT, BEFORE ANY CREDENTIAL IS EXAMINED. See the module docstring.
    if admin is not None and admin.is_locked:
        minutes = admin.locked_minutes_remaining
        _record_attempt(email, ip, successful=False, reason="locked_out")
        db.session.commit()
        flash(
            f"অ্যাকাউন্টটি সাময়িকভাবে লক করা হয়েছে। আনুমানিক {minutes} মিনিট পর আবার "
            "চেষ্টা করুন।",
            "error",
        )
        return render_template("admin/login.html", email=email, next=next_target), 429

    password_ok = admin is not None and bool(
        bcrypt.check_password_hash(admin.password_hash, request.form.get("password") or "")
    )

    # Only spend time on the second factor when the password was right, so a wrong
    # password cannot be used to tell "no TOTP enrolled" from "wrong code".
    # Annotated because the tuple is assigned twice with different element types:
    # without the annotation `totp_reason` is pinned to `str` by its first value and
    # the `str | None` the helper returns is rejected.
    totp_ok: bool = False
    totp_reason: str | None = "bad_password"
    if password_ok:
        totp_ok, totp_reason = _verify_second_factor(admin)

    if password_ok and totp_ok:
        # Rotate, then authenticate. Reversing these two lines would leave the
        # pre-login session contents in place alongside the authenticated ones.
        session.clear()
        login_user(admin, remember=False)
        session.permanent = True

        admin.register_success(ip=ip)
        audit.record_login(email=admin.email, successful=True, ip=ip)
        _record_attempt(admin.email, ip, successful=True)
        db.session.commit()
        return redirect(next_target or url_for("admin.index"))

    # Failure. The reason is stored for the operator; the reader is told nothing
    # specific, except in the lockout branch above.
    if admin is None:
        reason = "unknown_email"
    elif not password_ok:
        reason = "bad_password"
    else:
        reason = totp_reason or "bad_totp"

    locked_now = False
    if admin is not None:
        locked_now = admin.register_failure(
            int(current_app.config["LOGIN_MAX_ATTEMPTS"]),
            int(current_app.config["LOGIN_LOCKOUT_MINUTES"]),
        )

    _record_attempt(email, ip, successful=False, reason=reason)
    db.session.commit()

    if locked_now:
        flash(
            f"পরপর {current_app.config['LOGIN_MAX_ATTEMPTS']} বার ভুল হয়েছে। "
            f"অ্যাকাউন্টটি {current_app.config['LOGIN_LOCKOUT_MINUTES']} মিনিটের জন্য "
            "লক করা হলো।",
            "error",
        )
    else:
        flash(BAD_CREDENTIALS_BN, "error")

    return render_template("admin/login.html", email=email, next=next_target), 401


@auth_bp.post("/logout")
def logout():
    """Route 15. POST only, so a link or an image cannot sign the admin out.

    A GET logout is a CSRF target: any page can embed `<img src=".../logout">` and
    the admin is signed out without touching anything. Requiring POST puts it behind
    the global CSRF protection like every other state change.
    """
    if current_user.is_authenticated:
        audit.record(
            "logout",
            entity_type="AdminUser",
            entity_id=current_user.get_id(),
            before=None,
            after={"email": current_user.email},
        )
        db.session.commit()

    logout_user()
    session.clear()
    flash("আপনি সফলভাবে প্রস্থান করেছেন।", "info")
    return redirect(url_for("auth.login"))
