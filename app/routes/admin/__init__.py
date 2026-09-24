"""Admin CMS — routes 16–34. plan.md §6.2, §11.

A package rather than a module because it is 19 routes across 10 screens. Each
screen becomes its own module in Phase 4–6 (``pages.py``, ``participants.py``,
``media.py``, …) and they all hang off this blueprint.

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
    """Route 16 — the dashboard. plan.md §11.1, step 4.6.

    THE CONSENT COUNTS ARE THE POINT OF THIS SCREEN
        Total, published, ready-but-unpublished, consented-with-no-date, awaiting
        consent, and withdrawn. They come from `participant_service.consent_breakdown`
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
    """
    from sqlalchemy import func, select

    from app.extensions import db
    from app.models import AuditLog, Backup, Page
    from app.services import participant_service

    def _count(stmt) -> int:
        return int(db.session.execute(stmt).scalar_one())

    counts = participant_service.consent_breakdown()

    pages_published = _count(
        select(func.count(Page.id)).where(Page.is_published.is_(True))
    )
    pages_draft = _count(
        select(func.count(Page.id)).where(Page.is_published.is_(False))
    )

    # Newest first, by id rather than by `created_at`: two rows written in the same
    # transaction can share a timestamp, and `created_at` alone would order them
    # arbitrarily. The id is monotonic.
    recent_activity = list(
        db.session.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(10)).scalars()
    )

    latest_backup = db.session.execute(
        select(Backup).order_by(Backup.id.desc()).limit(1)
    ).scalars().first()

    return render_template(
        "admin/index.html",
        counts=counts,
        buckets_total=participant_service.breakdown_totals(counts),
        pages_published=pages_published,
        pages_draft=pages_draft,
        recent_activity=recent_activity,
        latest_backup=latest_backup,
    )
