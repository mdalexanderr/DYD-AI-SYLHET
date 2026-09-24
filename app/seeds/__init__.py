"""Seed data and seeding logic. plan.md §10.6, execution-plan steps 2.13 and 2.15.

WHY THE DATA IS JSON AND NOT PYTHON
    §10.6 and the §9.1 layout put seed content in ``app/seeds/*.json`` so that a
    wrong module name or hotline number is a one-line file edit, not a code change
    and a redeploy. The department will notice a typo in the course summary long
    before anyone wants to open a pull request.

WHY EVERY FUNCTION HERE IS IDEMPOTENT
    Step 2.13's requirement is "running it twice changes nothing". ``flask seed``
    runs on every deploy that passes ``--seed``, and a seeder that appends would
    duplicate the whole curriculum on the second run. Everything is an upsert by
    natural key: ``slug`` for pages, institutions and courses, ``key`` for settings
    and stats, ``question_bn`` for FAQs.

WHAT IS DELIBERATELY NOT SEEDED
    • No participants. Real names enter through the CSV import (§11.4) with consent
      recorded per person; a seeder that invented them would be a way to publish a
      name nobody consented to (§5.3, R4). ``seed_demo_participants`` exists for
      development and refuses to run when APP_ENV is production.
    • No second institution and no second course (§3.2, S7).
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.constants import (
    ConsentAction,
    ConsentSource,
    Education,
    OutcomeType,
    SectionType,
    SettingValueType,
    StatSource,
)
from app.extensions import db
from app.models import (
    AdminUser,
    ConsentEvent,
    Course,
    CourseModule,
    Faq,
    Institution,
    Page,
    PageSection,
    Participant,
    Setting,
    Stat,
)
from app.models.base import utcnow
from app.security.crypto import (
    encrypt_secret,
    generate_recovery_codes,
    hash_recovery_code,
)
from app.security.sanitize import sanitize_html

SEEDS_DIR = Path(__file__).resolve().parent


def load_json(name: str) -> Any:
    """Read one seed file. Fails loudly: a missing seed file is a broken deploy."""
    path = SEEDS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"seed data missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _public(data: dict[str, Any]) -> dict[str, Any]:
    """Drop documentation keys before they reach a model constructor.

    The seed JSON carries `_note` fields recording WHY a value is a placeholder —
    Q1 and Q2 in §22 are still unanswered, and the note is the only place that
    says so. Those keys are not columns, and SQLAlchemy raises TypeError on an
    unknown keyword, so they are stripped here rather than deleted from the JSON,
    because the explanation is worth more than the tidiness.
    """
    return {key: value for key, value in data.items() if not key.startswith("_")}


def _upsert(
    model,
    key_field: str,
    key_value: Any,
    defaults: dict[str, Any],
    *,
    refresh: tuple[str, ...] = (),
):
    """Find by natural key, CREATING THE ROW IF IT IS MISSING AND LEAVING IT ALONE IF NOT.

    EXISTING ROWS ARE NOT OVERWRITTEN, AND THAT IS THE POINT OF THIS FUNCTION.
        The previous version wrote every key in `defaults` on every run. Among those
        keys was `Page.is_published = False`, so re-running `flask seed` UNPUBLISHED
        EVERY PAGE AND TOOK THE PUBLIC SITE OFFLINE.

        That is not a theoretical hazard. The deploy runs `flask seed` (§20), so the
        bug meant a routine redeploy silently removed the entire site — and it would
        have been found by a reader, not by CI, because seeding exits 0 either way and
        "pages: 7" is the same number before and after.

    SEEDING IS A FIRST-INSTALL STEP, NOT A RESET.
        Its job is to make sure the reference rows exist. A field that genuinely has
        to track its source file on every run is named explicitly in `refresh`, so
        destructive behaviour is opt-in per field. The failure mode of forgetting to
        opt in is a stale seed value; the failure mode of the old default was that the
        site disappears. Those two are not comparable, so the default is the safe one.

    `refresh` exists rather than being omitted so the next person has an obvious place
    to put a field that really must be re-applied, instead of reaching for `setattr`.
    """
    column = getattr(model, key_field)
    existing = db.session.execute(select(model).where(column == key_value)).scalar_one_or_none()
    if existing is None:
        obj = model(**{key_field: key_value, **defaults})
        db.session.add(obj)
        return obj

    for name in refresh:
        if name in defaults:
            setattr(existing, name, defaults[name])
    return existing


# ─────────────────────────────────────────────────────────────────────────────
def seed_reference_data() -> dict[str, int]:
    """Every §10.6 reference record. Safe to run repeatedly."""
    counts: dict[str, int] = {}

    # ── Institution (§3.2). One, and its name is Q2 — used verbatim. ─────────
    institution_data = load_json("institution.json")
    institution = _upsert(Institution, "slug", institution_data["slug"],
                          _public(institution_data))
    db.session.flush()
    counts["institutions"] = 1

    # ── Course + modules ────────────────────────────────────────────────────
    course_data = load_json("course.json")
    modules_data = course_data.pop("modules", [])
    course = _upsert(Course, "slug", course_data["slug"], _public(course_data))
    db.session.flush()

    # Modules are replaced rather than merged: the syllabus is a list where order
    # is meaningful, and merging would leave a removed module behind forever.
    for existing in list(course.modules):
        db.session.delete(existing)
    db.session.flush()
    for index, module in enumerate(modules_data, start=1):
        db.session.add(CourseModule(
            course_id=course.id,
            title_bn=module["title_bn"],
            description_bn=module.get("description_bn"),
            hours=module.get("hours"),
            icon_slug=module.get("icon_slug"),
            sort_order=index,
        ))
    counts["courses"] = 1
    counts["course_modules"] = len(modules_data)

    # ── Stats ───────────────────────────────────────────────────────────────
    for item in load_json("stats.json"):
        _upsert(Stat, "key", item["key"], {
            "label_bn": item["label_bn"],
            "value_bn": item.get("value_bn"),
            "value_num": item.get("value_num"),
            "unit_bn": item.get("unit_bn"),
            "source": StatSource(item.get("source", "manual")),
            "display_order": item.get("display_order", 0),
        })
    counts["stats"] = len(load_json("stats.json"))

    # ── FAQs ────────────────────────────────────────────────────────────────
    for index, item in enumerate(load_json("faqs.json"), start=1):
        _upsert(Faq, "question_bn", item["question_bn"], {
            "answer_bn": item["answer_bn"],
            "category": item.get("category"),
            "sort_order": item.get("sort_order", index),
            "is_active": item.get("is_active", True),
        })
    counts["faqs"] = len(load_json("faqs.json"))

    # ── Settings ────────────────────────────────────────────────────────────
    for item in load_json("settings.json"):
        _upsert(Setting, "key", item["key"], {
            "value": item.get("value"),
            "value_type": SettingValueType(item.get("value_type", "string")),
            "group": item.get("group", "general"),
            "label_bn": item.get("label_bn", ""),
            "is_secret": item.get("is_secret", False),
        })
    counts["settings"] = len(load_json("settings.json"))

    # ── Pages and their sections (§4.3) ─────────────────────────────────────
    page_count = 0
    section_count = 0
    for index, item in enumerate(load_json("pages.json"), start=1):
        page = _upsert(Page, "slug", item["slug"], {
            "title_bn": item["title_bn"],
            "title_en": item.get("title_en"),
            "nav_label_bn": item.get("nav_label_bn"),
            "show_in_nav": item.get("show_in_nav", False),
            "meta_description_bn": item.get("meta_description_bn"),
            "sort_order": item.get("sort_order", index),
            # Seeded pages are NOT published. A half-written page going live on
            # the first deploy is exactly what the draft state exists to prevent,
            # and the admin publishes deliberately (§11.2).
            "is_published": False,
        })
        db.session.flush()
        page_count += 1

        # SECTIONS ARE SEEDED ONLY INTO A PAGE THAT HAS NONE.
        #
        # The earlier version deleted every section and rebuilt them from the JSON on
        # every run. That is right for a first install and destructive on a redeploy,
        # because the deploy runs `flask seed` (§20): any section the department had
        # edited, reordered or added would be destroyed and silently replaced by the
        # seed copy. The command exits 0 either way, so nothing would report it.
        #
        # Harmless today — there is no admin yet, so no section has ever been edited —
        # and it becomes data loss the moment Phase 4 lands. Guarding it now costs one
        # level of indentation.
        if not page.sections:
            for order, section in enumerate(item.get("sections", []), start=1):
                payload = dict(section.get("content") or {})
                # The registry marks these two references REQUIRED, and pages.json
                # cannot contain them: the primary keys do not exist until the
                # database assigns them. They are injected here instead of being
                # omitted, because an omitted required ref fails validation and the
                # section is then rejected at seed time rather than at render time.
                if section["type"] == SectionType.MODULE_LIST.value:
                    payload["course_id"] = course.id
                if section["type"] == SectionType.INSTITUTION_CARD.value:
                    payload["institution_id"] = institution.id
                if "body_bn" in payload:
                    payload["body_bn"] = sanitize_html(payload["body_bn"])
                db.session.add(PageSection(
                    page_id=page.id,
                    type=section["type"],
                    sort_order=order,
                    is_visible=section.get("is_visible", True),
                    content=payload,
                ))

        # COUNT WHAT THE PAGE HAS, NOT WHAT THIS RUN CREATED.
        #
        # `section_count` used to increment inside the creation loop. Once sections
        # stopped being rebuilt on every run, the second run reported 0 — so `flask
        # seed` would print "page_sections: 0" against a perfectly healthy database,
        # and boot-check's "seed pass 2 is identical" assertion, which is the whole
        # idempotence proof, would have failed. Reporting the resulting state keeps the
        # number meaningful whether the sections were just created or already there.
        #
        # The expire is required: `page.sections` was already loaded (as empty) by the
        # `if not page.sections` test above, and without it the collection is served
        # from the identity map and still reads as empty.
        db.session.flush()
        db.session.expire(page, ["sections"])
        section_count += len(page.sections)

    counts["pages"] = page_count
    counts["page_sections"] = section_count
    counts["institution_id"] = institution.id
    counts["course_id"] = course.id

    db.session.commit()
    return counts


# ─────────────────────────────────────────────────────────────────────────────
def seed_admin(email: str, password: str, *, enable_2fa: bool = True,
               secret_key: str = "") -> dict[str, Any]:
    """Create the single admin account, enrolling TOTP if asked (§12.1).

    Returns the recovery codes in plaintext, ONCE. They are stored hashed and can
    never be read back — which is the point, and also why the caller must print
    them immediately.
    """
    from app.extensions import bcrypt

    admin = db.session.execute(
        select(AdminUser).where(AdminUser.email == email)
    ).scalar_one_or_none()
    created = admin is None
    if admin is None:
        admin = AdminUser(email=email)
        db.session.add(admin)

    admin.password_hash = bcrypt.generate_password_hash(
        password, rounds=12
    ).decode("ascii")
    admin.full_name_bn = admin.full_name_bn or "প্রশাসক"
    admin.is_active = True
    admin.failed_attempts = 0
    admin.locked_until = None
    admin.password_changed_at = utcnow()

    result: dict[str, Any] = {
        # This is the ADMINISTRATOR's own address, not a participant field. The ban
        # checker matches the bare token, so the marker is required; the reason is
        # the point of the marker.
        "email": email,  # check-bans:ignore admin login, not participant PII
        "created": created,
        "recovery_codes": [],
    }

    if enable_2fa:
        import pyotp

        secret = pyotp.random_base32()
        admin.twofa_secret = encrypt_secret(secret, secret_key) if secret_key else secret
        admin.twofa_enabled = True

        codes = generate_recovery_codes()
        admin.recovery_codes = json.dumps([hash_recovery_code(c) for c in codes])

        result["recovery_codes"] = codes
        result["totp_secret"] = secret
        result["provisioning_uri"] = pyotp.TOTP(secret).provisioning_uri(
            name=email, issuer_name="DYD AI Sylhet"
        )
    else:
        admin.twofa_enabled = False
        admin.twofa_secret = None

    db.session.commit()
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Development fixtures. §8.2: "deliberately generates consented, non-consented,
# consent-withdrawn, missing-consent_date, single-participant outcome and
# zero-outcome records. The consent rules cannot be verified against three
# happy-path rows."
# ─────────────────────────────────────────────────────────────────────────────
_DEMO_NAMES_BN = [
    "রূপা আক্তার", "বিষ্ণুপ্রসাদ দাশ", "সাইফুল ইসলাম চৌধুরী", "নুসরাত জাহান",
    "মোঃ আব্দুল করিম", "তানজিলা আক্তার", "শাহিদা বেগম", "অমিতাভ রায়",
    "জাহাঙ্গীর আলম", "সুমাইয়া ইসলাম", "কাজী নাজমুল হাসান", "লতা রানী দাস",
    "মাহবুবুর রহমান", "ফারজানা ইয়াসমিন", "দেবাশীষ কর", "রুবিনা পারভীন",
]
_DEMO_SLUGS = [
    "rupa-akter", "bishnuprasad-das", "saiful-islam-chowdhury", "nusrat-jahan",
    "abdul-karim", "tanjila-akter", "shahida-begum", "amitava-ray",
    "jahangir-alam", "sumaiya-islam", "kazi-nazmul-hasan", "lata-rani-das",
    "mahbubur-rahman", "farzana-yasmin", "debasis-kar", "rubina-parvin",
]
_OCCUPATIONS = ["শিক্ষার্থী", "কৃষি", "গৃহিণী", "ছোট ব্যবসা", "বেকার", "দিনমজুর"]


def seed_demo_participants(count: int = 120, *, consent_rate: float = 0.8,
                           batch: int = 1, seed: int = 20260924) -> dict[str, int]:
    """Development-only fixtures with every consent state represented.

    Refuses to run in production: these are invented people, and an invented name
    on a public government page is a consent incident, not a fixture.
    """
    from flask import current_app

    if current_app.config["APP_ENV"] == "production":
        raise RuntimeError(
            "refusing to seed demo participants in production — these are invented "
            "names and publishing one would be a consent incident (§5.3, R4)"
        )

    rng = random.Random(seed)
    outcomes = list(OutcomeType)
    education = list(Education)

    created = {"total": 0, "consented": 0, "not_consented": 0, "withdrawn": 0,
               "missing_date": 0, "suppressed_outcome": 0}

    for index in range(count):
        slug = f"demo-{index + 1:04d}-{_DEMO_SLUGS[index % len(_DEMO_SLUGS)]}"
        if db.session.execute(
            select(Participant).where(Participant.slug == slug)
        ).scalar_one_or_none():
            continue

        name_bn = _DEMO_NAMES_BN[index % len(_DEMO_NAMES_BN)]
        roll = rng.random()

        # A deliberate 2-person `teaching` bucket, so the `<5` suppression rule
        # has something to suppress (step 6.8 / journey 5).
        if index < 2:
            outcome = OutcomeType.TEACHING
        elif index < 8:
            outcome = None
        else:
            outcome = rng.choice(outcomes)

        participant = Participant(
            slug=slug,
            name_bn=name_bn,
            name_en=None,
            education=rng.choice(education),
            occupation_before=rng.choice(_OCCUPATIONS),
            outcome_type=outcome,
            batch=batch,
            quote_bn=None,
            quote_consented=False,
            consent_publication=False,
            consent_date=None,
            consent_source=None,
        )

        if roll < consent_rate:
            # Consented. Some are published, some are not — both are normal.
            participant.consent_publication = True
            participant.consent_source = rng.choice(list(ConsentSource))
            if index % 7 == 0:
                # Consented but with NO DATE. §5.3 rule 3: the consent dashboard
                # must surface these, and the publish guard must refuse them.
                participant.consent_date = None
                created["missing_date"] += 1
            else:
                participant.consent_date = date(2026, 3, 1) + timedelta(days=index % 40)
                if index % 3 != 0:
                    participant.is_published = True
                    participant.published_at = utcnow()
                created["consented"] += 1
        elif roll < consent_rate + 0.12:
            # Withdrawn: consented once, then removed. Unpublished, row kept.
            participant.consent_publication = True
            participant.consent_date = date(2026, 3, 1)
            participant.consent_withdrawn_at = utcnow()
            participant.is_published = False
            created["withdrawn"] += 1
        else:
            created["not_consented"] += 1

        if outcome == OutcomeType.TEACHING:
            created["suppressed_outcome"] += 1

        # search_blob is set by the model's before_flush hook.
        db.session.add(participant)
        db.session.flush()

        action = ConsentAction.WITHDRAWN if participant.consent_withdrawn_at else (
            ConsentAction.GRANTED if participant.consent_date else ConsentAction.UPDATED
        )
        db.session.add(ConsentEvent(
            participant_id=participant.id,
            action=action,
            source=participant.consent_source,
            notes="seeded development fixture",
        ))
        created["total"] += 1

    db.session.commit()
    return created


def stats_by_key() -> dict[str, Stat]:
    return {row.key: row for row in db.session.execute(select(Stat)).scalars()}


def participant_counts() -> dict[str, int]:
    """Totals used by the dashboard and by the seeding report.

    Counted in SQL rather than in Python so a large cohort does not load into
    memory to be counted (§11.3).
    """
    total = db.session.execute(select(func.count(Participant.id))).scalar_one()
    published = db.session.execute(
        select(func.count(Participant.id)).where(Participant.is_published.is_(True))
    ).scalar_one()
    consenting = db.session.execute(
        select(func.count(Participant.id)).where(
            Participant.consent_publication.is_(True),
            Participant.consent_date.is_not(None),
            Participant.consent_withdrawn_at.is_(None),
        )
    ).scalar_one()
    withdrawn = db.session.execute(
        select(func.count(Participant.id)).where(
            Participant.consent_withdrawn_at.is_not(None)
        )
    ).scalar_one()
    missing_date = db.session.execute(
        select(func.count(Participant.id)).where(
            Participant.consent_publication.is_(True),
            Participant.consent_date.is_(None),
        )
    ).scalar_one()
    return {
        "total": total,
        "published": published,
        "consenting": consenting,
        "withdrawn": withdrawn,
        "missing_consent_date": missing_date,
        "not_consented": total - consenting - withdrawn,
    }


__all__ = [
    "SEEDS_DIR",
    "load_json",
    "participant_counts",
    "seed_admin",
    "seed_demo_participants",
    "seed_reference_data",
    "stats_by_key",
]
