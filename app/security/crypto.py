"""Secret encryption for the TOTP seed, and the recovery codes. plan.md §12.1.

WHAT IS ENCRYPTED AND WHY
    ``admin_users.twofa_secret`` is Fernet-encrypted with a key derived from
    ``SECRET_KEY``. A plaintext TOTP seed in a database dump hands an attacker the
    second factor, which is the whole reason the second factor exists — and a
    database dump is easier to obtain than the server.

    This is deliberately NOT a claim of strong protection. An attacker with both
    the database and ``SECRET_KEY`` has both factors. It removes the case where a
    dump leaks on its own, which is the realistic one.

RECOVERY CODES ARE HASHED, NOT ENCRYPTED
    A recovery code only ever needs to be *verified*, never read back, so it is
    bcrypt-hashed like a password. Encrypting it would mean the application could
    print it, and something eventually would.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_BYTES = 5  # 10 hex-ish characters, ~40 bits — single use only


class SecretDecryptionError(RuntimeError):
    """The stored secret could not be decrypted.

    Almost always means SECRET_KEY changed. The recovery path is a documented
    `flask admin-reset-2fa`, not a silent failure — a silent failure here would
    lock the single admin out of the site with no explanation.
    """


def _fernet(secret_key: str) -> Fernet:
    """Derive a stable Fernet key from SECRET_KEY.

    SECRET_KEY is a hex string of arbitrary length; Fernet needs exactly 32 bytes,
    urlsafe-base64 encoded. Deriving with sha256 means changing SECRET_KEY
    invalidates every stored secret — which is the correct behaviour, and is why
    the failure above names the cause.
    """
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str, secret_key: str) -> str:
    return _fernet(secret_key).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str, secret_key: str) -> str:
    try:
        return _fernet(secret_key).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise SecretDecryptionError(
            "could not decrypt the stored 2FA secret. SECRET_KEY has probably "
            "changed. Run `flask admin-reset-2fa --email <admin>` to re-enrol."
        ) from exc


# ── Recovery codes ───────────────────────────────────────────────────────────
def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Human-transcribable single-use codes.

    Base32-ish alphabet with the ambiguous characters removed (0/O, 1/I/L), because
    these get read off a printed page over a phone.
    """
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def hash_recovery_code(code: str, bcrypt_rounds: int = 12) -> str:
    """Hash one code the way a password is hashed.

    Imported lazily so this module can be used by a script without a Flask app.
    """
    from app.extensions import bcrypt

    normalised = code.strip().upper().replace(" ", "")
    # Bound to an annotated local: Flask-Bcrypt ships no stubs, so its return is
    # `Any`, and `Any` leaking out of a function declared to return `str` is how a
    # typing hole spreads. The annotation pins it at the boundary.
    hashed: str = bcrypt.generate_password_hash(
        normalised, rounds=bcrypt_rounds
    ).decode("ascii")
    return hashed


def verify_recovery_code(code: str, hashes: list[str]) -> int | None:
    """Return the index of the matching code, or None. Caller removes it.

    Returning the index rather than a boolean is what makes a code SINGLE USE: the
    caller must delete that entry, and it cannot do that from a True.
    """
    from app.extensions import bcrypt

    normalised = code.strip().upper().replace(" ", "")
    for index, hashed in enumerate(hashes or []):
        try:
            if bcrypt.check_password_hash(hashed, normalised):
                return index
        except (ValueError, TypeError):
            continue  # a malformed stored hash must not 500 the login form
    return None


def constant_time_equals(a: str, b: str) -> bool:
    """Compare two secrets without leaking length or position through timing."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


__all__ = [
    "RECOVERY_CODE_COUNT",
    "SecretDecryptionError",
    "constant_time_equals",
    "decrypt_secret",
    "encrypt_secret",
    "generate_recovery_codes",
    "hash_recovery_code",
    "verify_recovery_code",
]
