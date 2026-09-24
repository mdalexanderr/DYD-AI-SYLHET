"""Serving uploaded media. plan.md §13.1, §13.2, §6.2 route 13 — step 3.6.

WHY UPLOADS LIVE OUTSIDE THE WEBROOT
    `UPLOAD_ROOT` is deliberately not under `app/static`. A directory the web server
    will hand out directly is a directory where an uploaded file can become an
    executed one — a `.php`, a `.html`, or the `.svg` that every upload validator
    forgets is a script container. Nothing here is served by the web server; it is
    served by this route, which decides what may leave.

WHY THE URL CARRIES A SIGNATURE
    The path alone would make the media directory enumerable — and a guessable URL
    for a person's photograph is a privacy problem on a site that publishes real
    people. `itsdangerous` binds a token to the exact path, so a signature minted for
    one file cannot be replayed against another, and it carries a timestamp, so an
    old link can be expired centrally by shortening the TTL.

    This is NOT access control. Everything reachable here is public content and the
    signature is in the URL; anyone the URL reaches can use it. What it buys is that
    the URL cannot be guessed, which is the property the plan asks for.

AN UNKNOWN FILE AND AN UNSIGNED ONE ARE BOTH 404
    Not 403. A 403 confirms the file exists, which turns the route into an oracle for
    which photographs are on the server — the same reasoning as the participant
    profile route returning 404 for a non-consented slug.
"""

from __future__ import annotations

#: A year, and `immutable`. Every URL embeds the signature, and the signature is
#: derived from the path and a timestamp — so replacing a file at the same path
#: necessarily produces a new URL, and the old one can be cached forever without
#: ever serving stale bytes.
CACHE_SECONDS = 60 * 60 * 24 * 365

#: The default signature lifetime. A year, because these URLs go into pages that are
#: themselves cached for hours and into a sitemap.
DEFAULT_TTL_SECONDS = CACHE_SECONDS

SIGNATURE_PARAM = "sig"


def _serializer():
    """A serializer salted for media, keyed on SECRET_KEY.

    The salt is not decoration: without it a token minted elsewhere in the app for the
    same payload would verify here, and the separation costs nothing.
    """
    from flask import current_app
    from itsdangerous import URLSafeTimedSerializer

    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="media")


def sign(path: str) -> str:
    # Pinned to an annotated local: itsdangerous ships no stubs, so its return is
    # `Any`, and an `Any` returned from a function declaring `str` disables checking at
    # every call site.
    token: str = _serializer().dumps(path)
    return token


def verify(path: str, token: str, *, max_age: int | None = None) -> bool:
    """True when `token` is a valid, unexpired signature FOR `path`.

    Comparing `loads(token) == path` is what binds the signature to the file. Without
    that comparison a token for any known path would unlock every path, which is the
    shape of bug that looks like it works until somebody tries.
    """
    from itsdangerous import BadSignature, SignatureExpired

    if not path or not token:
        return False
    try:
        payload: str = _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return False
    return payload == path


def signed_url(path: str, *, ttl: int | None = None) -> str:
    """A ready-to-use URL for a stored media path."""
    from urllib.parse import quote

    token = sign(path)
    return f"/media/{quote(path)}?{SIGNATURE_PARAM}={quote(token)}"


def _is_safe_relative_path(path: str) -> bool:
    """Reject traversal, absolute paths and Windows drive letters before touching disk.

    `send_from_directory` does its own `safe_join`, so this is not the only guard —
    but relying on a library's internals for a traversal check is how a dependency
    upgrade becomes a security incident. Cheap, explicit, and it fails closed.

    ANY occurrence of `..` IS REJECTED, NOT JUST A WHOLE COMPONENT. Checking components
    (`".." in path.split("/")`) is the obvious implementation, and the test suite
    caught it missing `..%2F..%2Fetc%2Fpasswd`: the percent-encoded slash hides the
    boundary from the split, so the string is one component and the check passes it.
    Flask decodes escapes before the view runs, so the component form would be caught
    in practice — but a guard whose correctness depends on how far up the stack the
    decoding happened is a guard that changes behaviour on a framework upgrade.
    Strictness costs nothing here: a legitimate filename containing `..` does not
    exist.
    """
    if not path or path.startswith(("/", "\\")):
        return False

    normalised = path.replace("\\", "/").lower()
    if ".." in normalised:
        return False
    # Encoded dot and slash, in case this is ever reached before decoding.
    if "%2e" in normalised or "%2f" in normalised:
        return False
    # A colon means a drive letter or an alternate data stream on Windows.
    return ":" not in normalised


def _is_servable(path: str) -> bool:
    """Only media extensions may be served, and never the rejected ones.

    `REJECTED_UPLOAD_EXTENSIONS` is checked explicitly rather than left to the allow
    list, because the two lists are maintained in different places and an SVG that
    slipped into both would be an XSS with a cache header.
    """
    from flask import current_app

    from app.constants import REJECTED_UPLOAD_EXTENSIONS

    if "." not in path:
        return False
    extension = path.rsplit(".", 1)[-1].lower()

    if extension in REJECTED_UPLOAD_EXTENSIONS:
        return False

    allowed = tuple(
        str(e).strip().lower().lstrip(".")
        for e in (current_app.config.get("ALLOWED_UPLOAD_EXTENSIONS") or ())
        if str(e).strip()
    )
    return extension in allowed


def serve(filename: str, signature: str | None, *, max_age: int | None = None):
    """Return a `Response` for an upload, or abort 404.

    404 for every refusal — bad path, bad extension, missing or bad signature. The
    caller cannot distinguish them, and neither can anyone probing.
    """
    from flask import abort, current_app, make_response, send_from_directory

    if not _is_safe_relative_path(filename) or not _is_servable(filename):
        abort(404)

    ttl = DEFAULT_TTL_SECONDS if max_age is None else max_age
    if not signature or not verify(filename, signature, max_age=ttl):
        abort(404)

    response = make_response(
        send_from_directory(current_app.config["UPLOAD_ROOT"], filename)
    )
    # The browser is told not to second-guess the declared type. Without it, a file
    # uploaded with an image extension and HTML inside can still render as HTML in
    # some clients — which is the mechanism behind a whole class of stored XSS.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}, immutable"
    # `inline`, not `attachment`: these are images in a page, and forcing a download
    # would break the gallery. The type is constrained by the extension allow list.
    response.headers["Content-Disposition"] = "inline"
    return response


__all__ = [
    "CACHE_SECONDS",
    "DEFAULT_TTL_SECONDS",
    "SIGNATURE_PARAM",
    "serve",
    "sign",
    "signed_url",
    "verify",
]
