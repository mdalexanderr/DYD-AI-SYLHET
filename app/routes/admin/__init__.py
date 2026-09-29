"""Admin CMS — routes 16–34. plan.md §6.2, §11.

A package rather than a module because it is 19 routes across 15 screens. Each
screen is its own module — ``pages.py``, ``participants.py``, ``media.py``, ``ops.py``
— and they all hang off this blueprint.

THE PANEL IS ENGLISH AND THE SITE IS BANGLA
    §14.1 makes the public site Bangla-first; §11.1's panel is the operator's tool
    and is English. Every string in this package is English for that reason, and
    content values that happen to be Bangla (a page title, a person's name) carry
    ``lang="bn"`` where they are rendered.

The URL prefix is set by the app factory from ``ADMIN_URL_PREFIX`` (§12.1), not
here — a prefix declared in two places is a prefix that will disagree, and the
disagreement would be a guessable admin path.
"""

from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import login_required

admin_bp = Blueprint("admin", __name__)
URL_PREFIX = None  # set by create_app from ADMIN_URL_PREFIX


@admin_bp.get("/")
@login_required
def index():
    """Route 16 — the dashboard.

    WHAT THIS SCREEN IS FOR
        It answers three questions in order, and the layout is that order: *is
        anything blocked?* (the tiles), *what changed recently?* (the activity
        table), and *what is waiting on me?* (the message queue). A dashboard that
        opens with a chart answers none of them.

    THE CONSENT COUNTS ARE THE POINT
        Total, published, ready-but-unpublished, consented-with-no-date, awaiting
        consent, withdrawn. They come from `participant_service.consent_breakdown`
        rather than being queried here, because that module is the consent boundary —
        a second place that decides what "consented" means is a second place it can
        drift, and the consequence of drift here is a count that tells an operator
        the wrong number of people are waiting.

    `ready_unpublished` AND `consent_missing_date` ARE NOT IN THE PLAN'S FOUR NAMES
        They exist so the buckets sum to the total. Without them the dashboard would
        silently omit anyone who consented without a recorded date — the exact state
        §5.3 rule 3 forbids and §5.6 asks to be shown first.

    AN EMPTY DATABASE RENDERS COUNTS OF ZERO, NOT AN ERROR
        Every query is a COUNT, and a COUNT over nothing is 0. A dashboard that
        breaks on a fresh install is a dashboard nobody sees before they need it.

    THE BLOCKED COUNT IS THE ONE NUMBER THAT IS ALLOWED TO SHOUT
        `consent_missing_date` is a person who believes they consented while nothing
        publishes them. It is the only state that is both invisible and blocking, so
        it gets the alert tile and its own line rather than being one of six equal
        figures.
    """
    from sqlalchemy import func, select

    from app.constants import MessageStatus
    from app.extensions import db
    from app.models import (
        AuditLog,
        Backup,
        ContactMessage,
        CourseModule,
        Faq,
        Institution,
        MediaItem,
        Page,
        PageSection,
        Stat,
    )
    from app.routes.admin._nav import quick_actions
    from app.services import participant_service

    def _count(model, *criteria) -> int:
        stmt = select(func.count(model.id))
        for criterion in criteria:
            stmt = stmt.where(criterion)
        return int(db.session.execute(stmt).scalar_one())

    counts = participant_service.consent_breakdown()

    content = {
        "pages": _count(Page),
        "pages_published": _count(Page, Page.is_published.is_(True)),
        "sections": _count(PageSection),
        "media": _count(MediaItem),
        "faqs": _count(Faq),
        "stats": _count(Stat),
        "modules": _count(CourseModule),
        "institutions": _count(Institution),
    }

    open_messages = list(
        db.session.execute(
            select(ContactMessage)
            .where(ContactMessage.status.in_((MessageStatus.NEW, MessageStatus.READ)))
            .order_by(ContactMessage.id.desc())
            .limit(5)
        ).scalars()
    )
    messages_open = _count(
        ContactMessage,
        ContactMessage.status.in_((MessageStatus.NEW, MessageStatus.READ)),
    )

    # Newest first, by id rather than by `created_at`: two rows written in the same
    # transaction can share a timestamp, and `created_at` alone would order them
    # arbitrarily. The id is monotonic.
    recent_activity = list(
        db.session.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(8)).scalars()
    )

    latest_backup = db.session.execute(
        select(Backup).order_by(Backup.id.desc()).limit(1)
    ).scalars().first()

    # Quick actions, chosen for what the rail cannot do (see `_nav.py`).
    quick = quick_actions()

    return render_template(
        "admin/index.html",
        counts=counts,
        buckets_total=participant_service.breakdown_totals(counts),
        content=content,
        open_messages=open_messages,
        messages_open=messages_open,
        recent_activity=recent_activity,
        latest_backup=latest_backup,
        quick=quick,
    )


# ─────────────────────────────────────────────────────────────────────────────
# The screens. Imported at the END, after `admin_bp` exists, because each module
# does `from app.routes.admin import admin_bp` and attaches its routes to it. An
# import at the top of this file would be circular.
#
# Importing them here rather than from a list in the app factory is deliberate: a
# screen that is written but not imported is a screen that 404s, and the failure is
# silent in exactly the way the shell's nav warns about — it looks like a missing
# feature rather than a missing import. `tests/test_admin_cms.py` walks the URL map
# and fails if any of them stops resolving.
# ─────────────────────────────────────────────────────────────────────────────
from app.routes.admin import media  # noqa: E402,F401
from app.routes.admin import ops  # noqa: E402,F401
from app.routes.admin import pages  # noqa: E402,F401
from app.routes.admin import participants  # noqa: E402,F401
from app.routes.admin import records  # noqa: E402,F401

# The six records screens are declared as data (`records.py`) rather than as twenty
# functions, so their routes only exist once `register_all` runs. Called here, next to
# the imports, so that "written" and "reachable" are the same condition.
records.register_all()
