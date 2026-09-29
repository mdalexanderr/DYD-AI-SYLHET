"""The content API the React half reads. plan.md §11.3, §6.2.

    GET /api/v1/content            the whole payload, in one response
    GET /api/v1/participants       just the register, consent-filtered
    GET /api/v1/version            what the payload is keyed on (for a cheap poll)

WHY A VERSION ENDPOINT EXISTS AT ALL
    The panel writes to the database and the front end reads a payload that depends on
    it. An operator who fixes a typo wants to see it, and asking them to rebuild a
    bundle is not an answer. So the payload carries a `version` — the newest
    `updated_at` across the tables it reads — and the front end keeps it: a page can
    compare its cached version against `/api/v1/version` on focus and refetch only when
    it actually changed. That is one indexed MAX() query, and it is what makes "edit in
    the admin, see it on the site" true without polling 30 KB every thirty seconds.

CACHING IS `no-cache` PLUS AN ETAG, NOT `max-age`
    `max-age=600` means a change is invisible for ten minutes with no way to ask. With
    `no-cache` the browser revalidates on every load, and the ETag turns the answer into
    a 304 with no body — the same saving, but the data is never stale. `no-cache` here
    means "revalidate", NOT "do not store", which is the distinction that matters.
"""

from __future__ import annotations

import hashlib
import json

from flask import Blueprint, Response, jsonify, make_response, request

api_content_bp = Blueprint("content", __name__)
#: The app factory looks for `content_bp` (or `bp`) on the module named in
#: `BLUEPRINT_MODULES`. The longer name is kept as an alias so an import elsewhere does
#: not break, but this is the one that gets registered.
content_bp = api_content_bp
URL_PREFIX = "/api/v1"


def _version() -> str:
    """What the payload is keyed on: the newest write across the tables it reads.

    `max(updated_at)` rather than a hash of every row: one indexed aggregate instead of
    a full scan of six tables on every request. It is a VERSION, not a proof — two
    writes in the same second collide — and that is enough, because the only thing it
    is used for is deciding whether to refetch something a reader is looking at.
    """
    from sqlalchemy import func

    from app.extensions import db
    from app.models import (
        BatchWork,
        CourseModule,
        CoursePhase,
        Instructor,
        Participant,
        Stat,
        TrainingTool,
    )

    newest = None
    for model in (
        Participant,
        CourseModule,
        CoursePhase,
        TrainingTool,
        BatchWork,
        Instructor,
        Stat,
    ):
        value = db.session.execute(db.select(func.max(model.updated_at))).scalar()
        if value is not None and (newest is None or value > newest):
            newest = value
    return newest.isoformat() if newest else "empty"


def _payload_response(payload: dict) -> Response:
    """Serialize once, hash the bytes, and answer 304 when nothing changed.

    The ETag is computed from the RESPONSE BODY rather than from the version, because
    two different versions can produce the same body (a write that changed a row the
    payload does not expose) and a body hash cannot be wrong about that.
    """
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()[:32]

    if request.if_none_match and digest in request.if_none_match:
        response = make_response("", 304)
    else:
        response = make_response(body, 200)
        response.headers["Content-Type"] = "application/json; charset=utf-8"

    response.headers["ETag"] = f'"{digest}"'
    # `no-cache` = revalidate before use. NOT `no-store`: the body is cached, and the
    # 304 above is what makes revalidating cheap.
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    # The API is same-origin in both dev and production, so no CORS header is set.
    # Adding `*` would be a licence for any page to read the register.
    return response


@api_content_bp.get("/content")
def content():
    """Everything the React half renders, in one response. See `content_service`."""
    from app.services import content_service

    payload = content_service.build_content()
    payload["version"] = _version()
    return _payload_response(payload)


@api_content_bp.get("/participants")
def participants():
    """Just the register, already filtered by the consent rule.

    The filter is applied SERVER-SIDE by `content_service`, which calls
    `participant_service.list_published`. There is no query parameter here that can
    widen the result: a browser cannot ask for a name that has not consented, because
    there is no argument that expresses the request.
    """
    from app.services import content_service

    rows = content_service.build_content()["participants"]
    return _payload_response({"participants": rows, "version": _version()})


@api_content_bp.get("/version")
def version():
    """The version string alone — a few bytes, for checking whether to refetch."""
    response = jsonify({"version": _version()})
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


__all__ = ["api_content_bp", "content_bp"]
