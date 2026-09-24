#!/usr/bin/env python3
"""Assert the §9.1 layout exists. execution-plan step 2.1.

    python tools/check-tree.py

STEP 2.1'S "DONE WHEN" MADE EXECUTABLE
    "the tree matches §9.1 exactly — a later diff against the plan should be empty."

    That is a claim nobody can check by reading, and it decays silently: a directory
    that matters (uploads/, var/, public/) is exactly the kind of thing that is
    missing on a fresh clone and only discovered when a feature fails at runtime.

    Two lists, deliberately unequal in severity:

      REQUIRED — must exist NOW. Everything Phase 1 and Phase 2 deliver, plus every
                 directory in §9.1. A missing entry fails.
      DEFERRED — exists in §9.1 but belongs to a LATER phase, with the phase noted.
                 Reported as a count, never as a failure. Creating these as empty
                 placeholders to make a checklist green would be worse than the gap:
                 an empty `page_service.py` is a lie about what is implemented, and
                 it hides the real work from whoever picks the project up next.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


# ── Every directory in §9.1 ─────────────────────────────────────────────────
REQUIRED_DIRS = [
    "app",
    "app/security",
    "app/models",
    "app/sections",
    "app/routes",
    "app/routes/admin",
    "app/services",
    "app/templates",
    "app/templates/components",
    "app/templates/layouts",
    "app/templates/public",
    "app/templates/participants",
    "app/templates/admin",
    "app/templates/sections",
    "app/templates/errors",
    "app/templates/email",
    "app/static",
    "app/static/css",
    "app/static/js",
    "app/static/fonts",
    "app/static/img",
    "app/seeds",
    "assets/tailwind",
    "design-src",
    "migrations",
    "migrations/versions",
    "tests",
    "tools",
    "instance",
    "uploads",
    "var",
    "public",
    ".github/workflows",
]

# ── Files Phase 1 and Phase 2 must have delivered ───────────────────────────
REQUIRED_FILES = [
    # App factory and its collaborators (§9.2)
    "app/__init__.py",
    "app/config.py",
    "app/extensions.py",
    "app/cli.py",
    "app/constants.py",
    "app/filters.py",
    # Security
    "app/security/__init__.py",
    "app/security/audit.py",
    "app/security/crypto.py",
    "app/security/sanitize.py",
    # The 17 models (§10)
    "app/models/__init__.py",
    "app/models/base.py",
    "app/models/admin.py",
    "app/models/cms.py",
    "app/models/people.py",
    "app/models/course.py",
    "app/models/media.py",
    "app/models/ops.py",
    # The section registry (§4.2)
    "app/sections/__init__.py",
    "app/sections/registry.py",
    # The 6 blueprints (§9.2)
    "app/routes/__init__.py",
    "app/routes/public.py",
    "app/routes/participants.py",
    "app/routes/auth.py",
    "app/routes/seo.py",
    "app/routes/api.py",
    "app/routes/admin/__init__.py",
    # Layout and error pages (step 2.5)
    "app/templates/layouts/base.html",
    "app/templates/errors/404.html",
    "app/templates/errors/403.html",
    "app/templates/errors/419.html",
    "app/templates/errors/429.html",
    "app/templates/errors/500.html",
    "app/templates/errors/maintenance.html",
    # Seed data (§10.6)
    "app/seeds/__init__.py",
    "app/seeds/institution.json",
    "app/seeds/course.json",
    "app/seeds/stats.json",
    "app/seeds/faqs.json",
    "app/seeds/pages.json",
    "app/seeds/settings.json",
    # Design system (Phase 1)
    "assets/tailwind/source.css",
    "app/static/css/app.css",
    "app/static/img/roundel.svg",
    "app/static/img/sprite.svg",
    "app/static/img/contour-band-paper.svg",
    "app/static/img/contour-band-dark.svg",
    "app/static/img/favicon.ico",
    "app/static/site.webmanifest",
    # Tooling and gates
    "tools/check-css.py",
    "tools/check-bans.py",
    "tools/check-tree.py",
    "tools/gate-proof.py",
    "tools/render-design.py",
    "tools/boot-check.py",
    "tools/plan_lint.py",
    # Tests (step 2.17)
    "tests/conftest.py",
    "tests/test_schema.py",
    "tests/test_consent.py",
    "tests/test_bangla.py",
    "tests/test_filters.py",
    "tests/test_sections.py",
    "tests/test_routes.py",
    # Migrations (step 2.10)
    "migrations/env.py",
    "migrations/alembic.ini",
    # Deployment surface (steps 2.19, 2.20)
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "package.json",
    "package-lock.json",
    ".env.example",
    ".gitignore",
    ".gitattributes",
    ".htaccess",
    "public/.htaccess",
    "passenger_wsgi.py",
    "run.py",
    ".github/workflows/ci.yml",
    # Documents
    "plan.md",
    "EXECUTION-PLAN.md",
    "docs/DISCOVERY-QUESTIONNAIRE.md",
]

# ── In §9.1, but a later phase owns them. Reported, never failed on. ────────
DEFERRED: dict[str, str] = {
    "app/validators.py": "P4 — form and CSV-import validators",
    "app/security/images.py": "P4 — Pillow pipeline (upload resize, EXIF strip)",
    "app/sections/base.py": "P3 — SectionBase",
    "app/sections/hero.py + 12 more": "P3 — one module per section type (§9.3)",
    "app/services/page_service.py": "P3 — page render pipeline",
    "app/services/stats_service.py": "P3 — consented-only aggregates, <5 suppression",
    "app/services/participant_service.py": "P5 — publish rules, filtering, CSV import",
    "app/services/consent_service.py": "P5 — grant/withdraw + cache invalidation",
    "app/services/media_service.py": "P4/P6 — upload, thumbnails, signed URLs",
    "app/services/import_export_service.py": "P5 — CSV/XLSX in and out",
    "app/services/audit_service.py, backup_service.py": "P6/P8",
    "app/templates/{public,participants,admin,sections,email}/": "P3–P6",
    "app/static/js/": "P4/P5 — the only JavaScript on the site",
    "deploy.sh · rollback.sh · cron_backup.sh": "P9 — deploy & handover",
    ".github/workflows/deploy.yml": "P9",
    "README.md · DEPLOY.md · RUNBOOK.md · ADMIN_GUIDE.md": "P9",
}


def main() -> int:
    print()
    print("  §9.1 tree audit — execution-plan step 2.1")
    print("  " + "=" * 66)

    missing_dirs = [d for d in REQUIRED_DIRS if not (ROOT / d).is_dir()]
    missing_files = [f for f in REQUIRED_FILES if not (ROOT / f).is_file()]

    print(f"  required directories : {len(REQUIRED_DIRS) - len(missing_dirs)}"
          f"/{len(REQUIRED_DIRS)}")
    print(f"  required files       : {len(REQUIRED_FILES) - len(missing_files)}"
          f"/{len(REQUIRED_FILES)}")

    if missing_dirs:
        print()
        print("  MISSING DIRECTORIES")
        for item in missing_dirs:
            print(f"    - {item}/")

    if missing_files:
        print()
        print("  MISSING FILES")
        for item in missing_files:
            print(f"    - {item}")

    # Empty directories that are tracked only by a .gitkeep: worth naming, because a
    # directory git cannot see is a directory a fresh clone does not get.
    #
    # `instance/` and `uploads/` are excluded on purpose. They are created at runtime
    # by _configure_paths(), and both are gitignored — a .gitkeep inside them would
    # be ignored too, so warning about it would be advising something that cannot
    # work. The deploy pre-flight checks they exist on the server instead (§17.3).
    runtime_dirs = {"instance", "uploads", "var"}
    untracked_dirs = []
    for directory in REQUIRED_DIRS:
        if directory in runtime_dirs:
            continue
        path = ROOT / directory
        if not path.is_dir():
            continue
        if not any(path.iterdir()):
            untracked_dirs.append(directory)
    if untracked_dirs:
        print()
        print("  EMPTY DIRECTORIES (need a .gitkeep or they vanish on a fresh clone)")
        for item in untracked_dirs:
            has_keep = (ROOT / item / ".gitkeep").is_file()
            print(f"    {'ok   ' if has_keep else 'NO   '} {item}/")

    print()
    print(f"  deferred to a later phase: {len(DEFERRED)} entries")
    for item, why in DEFERRED.items():
        print(f"    · {item}  [{why}]")

    print()
    if missing_dirs or missing_files:
        print(f"  FAIL — {len(missing_dirs)} directory(ies) and "
              f"{len(missing_files)} file(s) missing")
        print()
        return 1

    print("  OK — every Phase 1 and Phase 2 artifact is present, and every §9.1 "
          "directory exists")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
