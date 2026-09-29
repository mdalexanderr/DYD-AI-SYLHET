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

from typing import Any

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
    that comparison a token for any known path would be accepted for every path, which
    is the shape of bug that looks like it works until somebody tries.
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


def signed_url_for_item(item: Any) -> str | None:
    """A servable URL for a `MediaItem` ROW, or None.

    THE NARROW FORM OF `signed_url`, and the one templates get. A template global that
    signed an arbitrary string would let a template — or anything that can influence one
    — mint a signature for any path, which is the enumerability the signature exists to
    remove (§13.1). This can only sign a row that is already stored, and it handles the
    two kinds of media with one answer each: an uploaded file (signed, because uploads
    live outside the webroot) and an external link (a video, §10.5).
    """
    if item is None:
        return None
    external = getattr(item, "external_url", None)
    if external:
        return str(external)
    path = getattr(item, "path", None)
    return signed_url(str(path)) if path else None


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


# ─────────────────────────────────────────────────────────────────────────────
# Upload (§13.1, route 28)
# ─────────────────────────────────────────────────────────────────────────────
#: Pillow names an image's FORMAT — "JPEG", "PNG", "WEBP" — while `ALLOWED_IMAGE_MIME`
#: in app.constants names its MIME TYPE — "image/png". They are different
#: vocabularies, and comparing one against the other rejects every valid file. The
#: first version of `store_upload` did exactly that: it built `{"IMAGE/JPEG", …}`
#: from the MIME tuple and looked up `"PNG"` in it.
PIL_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})

#: What the stored file is, keyed by the extension chosen for it. `image/jpg` is not
#: a MIME type, and `f"image/{extension}"` produces exactly that for a JPEG.
STORED_MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


class UploadRejected(ValueError):
    """An upload that will not be stored, with a Bangla reason for the operator.

    A rejected upload is an editor's mistake — the wrong file, a phone's HEIC, a
    40 MB scan — so it is reported and never raised as a 500.
    """


def store_upload(upload: Any, *, alt_bn: str = "", caption_bn: str | None = None) -> Any:
    """Validate, re-encode and store one uploaded image. Returns a `MediaItem`.

    FOUR THINGS HAPPEN, IN THIS ORDER, AND THE ORDER IS THE POINT (§13.1):

    1. **The extension is checked against an allow list.** Cheap, and it rejects the
       obvious before anything is decoded.
    2. **The bytes are sniffed.** An extension is a claim, not a fact: `logo.png`
       containing a PHP script is the oldest trick there is. Pillow opening it and
       reporting its real format is what makes the claim true.
    3. **The image is RE-ENCODED through Pillow.** This is the step that removes an
       embedded payload — EXIF, a trailing zip, a polyglot header — because what is
       written out is pixels, not the file that arrived.
    4. **The stored name is random and the path is outside the webroot.** A filename
       from a browser is attacker-controlled; `UPLOAD_ROOT` is outside `app/static`
       so nothing stored here is ever executed.

    THE ORIGINAL IS NOT KEPT. Storing both the original and the re-encode would leave
    the untrusted file on disk, which is the half that carries the payload.
    """
    import secrets
    from pathlib import Path

    from werkzeug.utils import secure_filename

    from app.constants import ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_MIME
    from app.extensions import db
    from app.models import MediaItem

    from flask import current_app

    if upload is None or not getattr(upload, "filename", ""):
        raise UploadRejected("No file was selected.")

    safe_name = secure_filename(upload.filename) or "upload"
    extension = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise UploadRejected(
            "That kind of file is not accepted. Allowed: "
            + ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
        )

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover — Pillow is a hard requirement
        raise UploadRejected("The image library is not available on this server.") from exc

    raw = upload.read()
    if not raw:
        raise UploadRejected("The file is empty.")

    limit_mb = int(current_app.config.get("MAX_CONTENT_LENGTH_MB") or 6)
    if len(raw) > limit_mb * 1024 * 1024:
        raise UploadRejected(f"The file cannot be larger than {limit_mb} MB.")

    import io

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
        sniffed = (image.format or "").upper()
    except (UnidentifiedImageError, OSError) as exc:
        # The extension claimed an image and the bytes disagree. This is the case the
        # sniffing exists for, and it is reported rather than stored.
        raise UploadRejected("That file is not actually an image.") from exc

    if sniffed not in PIL_FORMATS:
        raise UploadRejected(f"{sniffed} images are not accepted.")

    max_dimension = int(current_app.config.get("IMAGE_MAX_DIMENSION") or 2000)
    if max(image.size) > max_dimension:
        image.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

    # Alpha-aware: a PNG with transparency re-encoded as JPEG silently becomes a
    # black rectangle, which is a design bug nobody notices until it is on the site.
    has_alpha = image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    )
    if sniffed == "JPEG":
        image = image.convert("RGB")
        save_format, out_extension = "JPEG", "jpg"
    elif has_alpha:
        image = image.convert("RGBA")
        save_format, out_extension = "PNG", "png"
    else:
        image = image.convert("RGB")
        save_format, out_extension = "WEBP", "webp"

    root = Path(current_app.config["UPLOAD_ROOT"])
    bucket = root / "images"
    bucket.mkdir(parents=True, exist_ok=True)

    # The name is OURS: 16 random bytes, and nothing from the uploaded filename
    # survives into a path or a URL.
    stored_name = f"{secrets.token_hex(16)}.{out_extension}"
    target = bucket / stored_name

    buffer = io.BytesIO()
    if save_format == "JPEG":
        image.save(buffer, format=save_format, quality=88, optimize=True, progressive=True)
    elif save_format == "WEBP":
        image.save(buffer, format=save_format, quality=88, method=6)
    else:
        image.save(buffer, format=save_format, optimize=True)
    data = buffer.getvalue()

    # `image.exif` is deliberately NOT carried over, and neither is any other block:
    # a photograph straight from a phone carries GPS coordinates, and §13.2 forbids
    # publishing more about a person than the four consented facts.
    target.write_bytes(data)

    item = MediaItem(
        path=f"images/{stored_name}",
        original_name=safe_name,
        mime=STORED_MIME[out_extension],
        size_bytes=len(data),
        width=image.size[0],
        height=image.size[1],
        kind="image",
        alt_bn=(alt_bn or "").strip() or safe_name,
        caption_bn=(caption_bn or "").strip() or None,
    )
    db.session.add(item)
    return item


__all__ = [
    "CACHE_SECONDS",
    "DEFAULT_TTL_SECONDS",
    "PIL_FORMATS",
    "SIGNATURE_PARAM",
    "STORED_MIME",
    "UploadRejected",
    "serve",
    "signed_url_for_item",
    "sign",
    "signed_url",
    "store_upload",
    "verify",
]
