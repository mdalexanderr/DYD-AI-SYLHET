"""Replace ONE page's sections from `app/seeds/pages.json`.

    ~/venv/bin/python deploy/apply_page.py about

WHY THIS EXISTS
    `seeds.seed_reference_data` refuses to touch a page that already has sections — and
    that is correct, because `flask seed` runs on every deploy (§20) and a redeploy must
    never overwrite a page the department has edited. The consequence is that changing a
    seeded page's layout on a LIVE site needs a deliberate act.

    This is that act, and it is deliberately narrow: it writes the named page's sections
    and the page's own title/meta description, and it writes NOTHING ELSE. Participants,
    consent records, media, settings, other pages and their edits are not read, not
    changed and not re-created.

SAFETY ORDER
    Every section is validated against the real registry schema BEFORE anything is
    deleted, so a typo in the payload fails with an error and the live page keeps its
    current content. The replacement itself is one transaction.

    The page's cache is cleared afterwards because the rendered HTML is cached for
    CACHE_DEFAULT_TIMEOUT seconds; without that the new sections would be invisible for
    five minutes and look like a failed deploy.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

#: Injected here rather than stored in pages.json: the primary keys do not exist until
#: the database assigns them (§4.3), so the JSON cannot carry them.
REFERENCE_KEYS = ("institution_id", "course_id")


def _load_definition(slug: str) -> dict:
    path = BASE_DIR / "app" / "seeds" / "pages.json"
    definitions = json.loads(path.read_text(encoding="utf-8"))
    match = next((item for item in definitions if item.get("slug") == slug), None)
    if match is None:
        known = ", ".join(sorted(item.get("slug", "?") for item in definitions))
        raise SystemExit(f"apply_page: no page {slug!r} in pages.json. Known: {known}")
    return match


def _prepare(sections: list[dict], *, institution_id, course_id) -> list[dict]:
    from app.sections.registry import SECTIONS
    from app.security.sanitize import sanitize_html

    prepared: list[dict] = []
    for order, section in enumerate(sections, start=1):
        section_type = section["type"]
        implementation = SECTIONS.get(section_type)
        if implementation is None:
            raise SystemExit(
                f"apply_page: section {order} has unknown type {section_type!r}. "
                f"Known: {', '.join(sorted(SECTIONS))}"
            )

        payload = dict(section.get("content") or {})
        missing = [
            key
            for key, spec in implementation.schema.items()
            if spec.get("required") and key not in payload and key not in REFERENCE_KEYS
        ]
        if missing:
            raise SystemExit(
                f"apply_page: section {order} ({section_type}) is missing {missing}"
            )

        if section_type == "institution_card":
            payload["institution_id"] = institution_id
        if section_type == "module_list":
            payload["course_id"] = course_id
        if "body_bn" in payload:
            payload["body_bn"] = sanitize_html(payload["body_bn"])

        prepared.append(
            {
                "type": section_type,
                "sort_order": order,
                "is_visible": section.get("is_visible", True),
                "content": payload,
            }
        )
    return prepared


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: apply_page.py <slug>")
        return 2
    slug = argv[1]

    definition = _load_definition(slug)

    from app import create_app
    from app.extensions import db
    from app.models import Course, Institution, Page, PageSection

    app = create_app()
    with app.app_context():
        page = db.session.execute(db.select(Page).where(Page.slug == slug)).scalar_one_or_none()
        if page is None:
            print(f"apply_page: no page {slug!r} in the database")
            return 2

        institution = db.session.execute(
            db.select(Institution).order_by(Institution.id)
        ).scalars().first()
        course = db.session.execute(db.select(Course).order_by(Course.id)).scalars().first()
        if institution is None or course is None:
            print("apply_page: no institution or course row to reference")
            return 2

        # Validate FIRST — a rejected payload must not leave the page empty.
        prepared = _prepare(
            definition.get("sections", []),
            institution_id=institution.id,
            course_id=course.id,
        )

        replaced = len(page.sections)
        for existing in list(page.sections):
            db.session.delete(existing)
        db.session.flush()

        for item in prepared:
            db.session.add(PageSection(page_id=page.id, **item))

        page.title_bn = definition["title_bn"]
        if definition.get("meta_description_bn"):
            page.meta_description_bn = definition["meta_description_bn"]

        db.session.commit()
        print(f"apply_page: {slug} -> {replaced} section(s) replaced by {len(prepared)}")
        print(f"apply_page: published={page.is_published} nav={page.show_in_nav}")

    try:
        from app.extensions import cache

        cache.clear()
        print("apply_page: cache cleared")
    except Exception as error:  # the cache is a performance layer, not data
        print(f"apply_page: cache not cleared ({error}) — the page may be stale for a few minutes")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
