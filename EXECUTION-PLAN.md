# AI Sylhet — Execution Plan

> **This is the build order.** `plan.md` defines *what* the product is and is the authority on scope,
> schema, security and design. This document defines *the sequence we build it in*, and how we know
> each step is actually finished.
>
> If the two ever disagree, **`plan.md` wins** and this file is corrected.
>
> **Scope:** documentary site + single-admin CMS for Batch 1, Sylhet. 8 public pages, 13 section
> types, 17 tables, 34 routes, one admin user. **37 developer-days.** Nothing from the old
> operational system is in scope (`plan.md` §2.2, §23.2).

---

## Table of contents

- [0. How to use this document](#0-how-to-use-this-document)
- [1. Standing rules](#1-standing-rules)
- [2. Current state](#2-current-state)
- [3. Phase map](#3-phase-map)
- [Phase 0 — Discovery & decisions](#phase-0--discovery--decisions)
- [Phase 1 — Design system](#phase-1--design-system)
- [Phase 2 — Foundation](#phase-2--foundation)
- [Phase 3 — Public read-only site](#phase-3--public-read-only-site)
- [Phase 4 — Admin: pages & sections](#phase-4--admin-pages--sections)
- [Phase 5 — Admin: participants & consent](#phase-5--admin-participants--consent)
- [Phase 6 — Admin: remaining content](#phase-6--admin-remaining-content)
- [Phase 7 — Participant browsing](#phase-7--participant-browsing)
- [Phase 8 — Hardening](#phase-8--hardening)
- [Phase 9 — Deploy & handover](#phase-9--deploy--handover)
- [Appendix A — Session checkpoints](#appendix-a--session-checkpoints)
- [Appendix B — Command reference](#appendix-b--command-reference)
- [Appendix C — Commit convention](#appendix-c--commit-convention)
- [Appendix D — Blocker register](#appendix-d--blocker-register)

---

## 0. How to use this document

**Status markers**

| Marker | Meaning |
|---|---|
| `[ ]` | Not started |
| `[~]` | In progress |
| `[x]` | Finished — the **Done when** condition is genuinely met |
| `[!]` | Blocked — see [Appendix D](#appendix-d--blocker-register) |

**Every step has three parts**

1. **What** — the artefact, with the file path.
2. **Why** — the `plan.md` section it implements, so nobody has to guess.
3. **Done when** — the observable condition. If you cannot observe it, the step is not done.

**The loop, per step**

```
read plan.md §  →  write the smallest thing that satisfies "Done when"  →  run the gates  →  tick it
```

**Never batch-tick.** A phase is not "mostly done" — an untested consent guard is exactly as
dangerous as an unwritten one. Finish, verify, tick, move on.

**Gates (run before every commit)** — from `plan.md` §8.2:

```bash
npm run css:build && npm run css:check    # CSS built and policy-clean
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy app
.venv\Scripts\python.exe -m pytest --cov=app
python tools/plan_lint.py                 # only when plan.md changed
```

**If a step turns out to be wrong**, fix `plan.md` first, then this file. Never let code and plan
drift — that is how the earlier 52-table plan happened.

---

## 1. Standing rules

These are not steps. They are constraints on **every** step, and they are the reason this plan is
short. A violation of any of these is a bug of the highest severity.

| # | Rule | Source |
|---|---|---|
| **S1** | **One user: the admin.** No student accounts, no registration, no roles, no permission matrix. `admin_users` has no `role` column. | §2.2, §10.1 |
| **S2** | **No participant photograph ever.** `participants` has no image column and the CMS form has no image field. Training photos may appear in the gallery only, never captioned with a full name. | §5.2, §13.3 |
| **S3** | **Never add** `phone`, `email`, `nid`, `dob`, `blood_group`, `address`, `guardian_name`, `signature`, marks or any government identifier to `participants`. | §5.2, §10.3 |
| **S4** | **Never publish without consent.** `is_published = 1` requires `consent_publication = 1` **and** a non-null `consent_date`. Enforced in the form, the model, **and** a DB `CHECK` constraint. | §5.3, §10.3 |
| **S5** | **Withdrawal unpublishes and invalidates cache in the SAME transaction. Never delete the row.** | §5.3, §15.1 |
| **S6** | **Any statistic from fewer than 5 records renders `—`.** | §5.4, R9 |
| **S7** | **No `district`, no `upazila`, no notices.** One institution, one cohort, no geography dimension. | §3.2, §23.3 |
| **S8** | **No app code without the owner's instruction. No commit, push or deploy without explicit instruction.** A push to `main` is a production release. | §17.5 |
| **S9** | **Never point at or deploy into the national site's app root or database.** `deploy.sh` pre-flight hard-fails on this. | §17.3 |
| **S10** | **Bangla requires `utf8mb4` / `utf8mb4_unicode_ci`.** `check-config` hard-fails otherwise. Check `NUL=` and first bytes before committing any Bangla file. | §9.4, R5 |
| **S11** | **All CSS lives in `assets/tailwind/source.css`.** No `<style>`, no `@apply` in templates, no arbitrary values (`bg-[#123456]`). `app.css` is compiled and committed. | §8.1 |
| **S12** | **No banned design pattern** — no purple/violet/indigo, no glassmorphism, no emoji icons, no stock photography, no AI-generated imagery, no "AI-powered" headlines. | §7.6 |
| **S13** | **The admin path is not `/admin`.** `ADMIN_URL_PREFIX` defaults to `ops-sylhet`; `/admin` must stay a 404. | §12.1 |

---

## 2. Current state

Verified **2026-09-24**.

| Item | State |
|---|---|
| `plan.md` | ✅ 1,797 lines, 23 sections, lint clean |
| Git | ✅ `main` == `origin/main` at `8f7ab6a` |
| Python | ✅ **3.12.10** installed (matches `plan.md` §3 and the cPanel Passenger app) |
| `.venv` | ✅ created on 3.12.10 |
| Runtime deps | ✅ 18 packages installed and verified together |
| Dev deps | ✅ pytest, pytest-cov, pytest-playwright, ruff, mypy, bandit, pip-audit, locust |
| `requirements.txt` / `requirements-dev.txt` | ✅ written, `pip check` clean, dry-run resolve clean — **untracked in git** |
| Playwright browsers | ❌ not downloaded (~150 MB) — deferred to Phase 8 |
| Node / npm | ✅ Node 24 present, but **no `package.json` yet** — that is Phase 1 step 1 |
| Application code | ❌ **none.** This is correct. |

Two findings from the dependency verification are **already folded into Phase 2 and Phase 6** below,
because they would otherwise cost a debugging day each:

- `bleach.clean(strip=True)` removes disallowed **tags** but keeps their **text**, so
  `<script>alert(1)</script>` becomes the literal text `alert(1)`. `sanitize.py` must pre-strip
  `<script|style>` blocks before handing anything to bleach.
- Flask-Limiter v4 emits **no** `X-RateLimit-*` headers unless `RATELIMIT_HEADERS_ENABLED = True`.

---

## 3. Phase map

One phase per milestone in `plan.md` §20, so there is no second numbering scheme to keep in sync.

| Phase | Builds | Days | Session | Depends on |
|---|---|---|---|---|
| **0** | Discovery & decisions | 1 | 1 | — |
| **1** | Design system | 4 | 1 | 0 |
| **2** | Foundation | 4 | 1 | 1 |
| **3** | Public read-only site | 6 | 1 | 2 |
| **4** | Admin: pages & sections | 6 | 2 | 3 |
| **5** | Admin: participants & consent | 5 | 2 | 4 |
| **6** | Admin: remaining content | 4 | 3 | 5 |
| **7** | Participant browsing | 2 | 2 | 5 |
| **8** | Hardening | 3 | 3 | 6, 7 |
| **9** | Deploy & handover | 2 | 3 | 8 |
| | **Total** | **37** | | |

> **Why Phase 7 comes after Phase 6 in the table but sits in Session 2:** it depends only on Phase 5.
> Build it in Session 2 if the participant CRUD lands early; otherwise it slots in comfortably.

---

## Phase 0 — Discovery & decisions

**Goal:** remove every unknown that would otherwise be discovered on launch week.
**Days:** 1 · **Session:** 1 · **Depends on:** —

### Steps

- [ ] **0.1 — Send the §22 questionnaire**
  All 11 questions (`plan.md` §22) to the DYD Sylhet side in one message. The two that matter most
  are **Q6** (*does written consent exist for Batch 1?*) and **Q2** (*is "Sylhet BUTTC" the correct
  legal name?*).
  **Done when:** every question has an answer or an explicit "unanswered".

- [ ] **0.2 — Record the answers in `plan.md` §22**
  Replace the "Default if unanswered" column with the actual answer and the date. Unanswered items
  keep a named owner and a date.
  **Done when:** no row in §22 says "pending" without a name against it.

- [ ] **0.3 — Confirm the three content-critical answers**
  **Q2** institution name and address · **Q3** partner JV entity · **Q1** Batch 1 dates.
  These three appear on Course, About, every participant profile and the footer.
  **Done when:** all three are written down and match what the national site says.

- [ ] **0.4 — Confirm the consent position (Q6) — ⚠ blocking for launch**
  Establish, in writing, whether consent for publication exists for this batch or must be collected.
  **Done when:** there is a written answer. If consent does **not** exist, the site launches with the
  register empty and no participant name is published until consent is recorded per person (§5.3).
  **This is the single highest-risk item in the project (R1, R4).**

- [ ] **0.5 — Confirm the hosting target (Q10)**
  Ask the host to create `sylhet.dydaiproject.com` as a **new Passenger app** with its own docroot,
  its own Python virtualenv and its own database. The national site is untouched (S9).
  **Done when:** the subdomain resolves and cPanel shows the Python app.

- [ ] **0.6 — Provision the production database**
  cPanel → MySQL Databases. Verify the collation is `utf8mb4_unicode_ci` in phpMyAdmin before
  anything is written to it (S10).
  **Done when:** `SHOW VARIABLES LIKE 'character_set_database'` returns `utf8mb4`.

- [ ] **0.7 — Collect the DYD identity assets (Q4)**
  Logo, government identity block, any supplied roundel or wordmark.
  **Done when:** either the assets are in hand, or everyone accepts the typographic wordmark plus the
  drawn roundel (§7.5) as the fallback.

- [ ] **0.8 — Obtain the Batch 1 roster shape (Q5)**
  Count, column list and format of the source spreadsheet. Use this to confirm the CSV import maps
  cleanly onto §5.1 and that **no prohibited column** (S3) is in the source.
  **Done when:** a sample file exists and every source column is mapped or dropped.

- [ ] **0.9 — Name the Bangla copy reviewer (Q11)**
  Every user-facing string needs a Bangla speaker's sign-off. Machine translation never ships.
  **Done when:** a person is named.

- [ ] **0.10 — Name the withdrawal contact (Q7)**
  The privacy page must state who to contact to withdraw consent, and the request must be actionable
  within 24 hours (§12.4).
  **Done when:** the name and contact route are recorded.

### Exit gate

- [ ] Every §22 question has an answer or a named owner
- [ ] Q2, Q3, Q6 answered — the launch-critical three
- [ ] Subdomain resolves; database created with `utf8mb4_unicode_ci`
- [ ] Bangla reviewer and withdrawal contact named

---

## Phase 1 — Design system

**Goal:** lock the visual language **before** any page is built, so no screen is ever designed twice.
**Days:** 4 · **Session:** 1 · **Depends on:** Phase 0 · **Builds `plan.md` §7, §8.1**

### Steps

- [ ] **1.1 — `package.json` + Tailwind v4 toolchain**
  Dev-only dependency. Node is already installed. Scripts exactly as specified in §8.1:
  `css:build`, `css:watch`, `css:check`, `design:build`, `design:watch`.
  **Done when:** `npm install` completes and `npm run css:build` produces a file.

- [ ] **1.2 — `tools/tailwindcss.exe` standalone binary**
  The fallback for machines without Node, and what CI can use without an install step.
  **Done when:** the binary compiles the stylesheet and is gitignored (§`.gitignore`).

- [ ] **1.3 — `assets/tailwind/source.css` — the `@theme` block**
  Transcribe §7.3 verbatim. The three wiping lines are the load-bearing part:
  `--color-*: initial`, `--radius-*: initial`, `--shadow-*: initial`.
  **Done when:** `bg-indigo-500`, `text-purple-600`, `rounded-3xl` and `shadow-lg` **fail to
  compile**. Prove it — put each in a scratch template and confirm the class is absent from the
  output. This is the anti-slop guarantee (§7.6.1); if it does not hold, the whole design system is
  a convention rather than a constraint.

- [ ] **1.4 — Bangla typography rules in `source.css`**
  The attribute-scoped global rules from §14.3: no `letter-spacing` or `text-transform` on `[lang="bn"]`,
  `.prose-bn` at 1.75 line-height and 68ch measure, bottom-border links instead of underlines,
  `.num` tabular numerals.
  **Done when:** `<h2 lang="bn" class="tracking-wide uppercase">` renders correctly anyway.

- [ ] **1.5 — Self-host the five fonts (§14.2)**
  Noto Serif Bengali (600/700), Noto Sans Bengali (400/500/600), IBM Plex Sans (400/500),
  Kalpurush, Nikosh. `font-display: swap`; `unicode-range` scoped to the Bengali block so
  Latin-only pages never fetch a Bengali face.
  **Done when:** critical-path font weight is **≤ 220 KB** and only the two above-the-fold faces are
  preloaded. No CDN, no Google Fonts.

- [ ] **1.6 — `tools/check-css.py`**
  Fails the build on a multi-hue gradient, a radius above 12px outside `--radius-pill`, a shadow blur
  over 32px, or `backdrop-filter` (§7.6.1).
  **Done when:** it exits non-zero on a deliberately bad scratch stylesheet.

- [ ] **1.7 — The kitchen-sink page**
  Every token, every component state, every Bangla text size, side by side. This is where the design
  is actually judged — not in the browser on the real site, where a bad decision hides behind
  plausible content.
  **Done when:** reviewed at 360 / 768 / 1440 and at least one token value has been **changed** as a
  result. If nothing changed, the page was not really looked at.

- [ ] **1.8 — Component macros — the 29 in §7.7**
  `SiteHeader` `SiteFooter` `Breadcrumb` `Hero` `SectionHeading` `DocumentRule` `StatStrip`
  `StatTable` `FactList` `ModuleGrid` `ParticipantCard` `ParticipantGrid` `FilterBar` `Pagination`
  `GalleryStrip` `MediaFeature` `QuoteBlock` `Timeline` `InstitutionCard` `FaqAccordion` `CtaBand`
  `RichText` `EmptyState` `ContactForm` `ConsentBadge` `Toast` `Modal` `DataTable` `KpiCard`
  **Done when:** each is on the kitchen-sink page in its real states — default, hover, focus,
  disabled, empty, error.

- [ ] **1.9 — Signature elements (§7.5)**
  `roundel.svg` (`DYD · AI · সিলেট · ব্যাচ ১`), `contour-band.svg`, `sprite.svg` (the one inlined
  icon sprite — no emoji), `favicon` set.
  **Done when:** no emoji appears anywhere in a template, and no icon is a raster image.

- [ ] **1.10 — Accessibility baseline (§7.8)**
  A 2px `--color-green-500` focus ring with 2px offset that is never removed; skip-to-content;
  44×44px minimum touch targets; `prefers-reduced-motion` honoured; Bangla `aria-label` on every
  icon-only control.
  **Done when:** the kitchen-sink page is fully keyboard-navigable with a visible focus indicator at
  every stop.

- [ ] **1.11 — Admin density skin**
  `.admin-scope` theme override: 13px base, `DataTable`-first, sticky filter bar. One stylesheet,
  two densities (§8.1 rule 6).
  **Done when:** the same components render at admin density without a second build.

### Exit gate

- [ ] `npm run css:build && npm run css:check` both pass
- [ ] Banned Tailwind classes provably do not compile
- [ ] Kitchen sink reviewed at 360 / 768 / 1440
- [ ] Font budget ≤ 220 KB; CSS under budget
- [ ] No emoji, no raster icons, no stock imagery anywhere

---

## Phase 2 — Foundation

**Goal:** the skeleton everything else hangs off — config, app factory, models, migrations, seeders, CI.
**Days:** 4 · **Session:** 1 · **Depends on:** Phase 1 · **Builds `plan.md` §9, §10, §16**

### Steps

- [ ] **2.1 — Directory skeleton (§9.1)**
  Create every directory in the layout, including empty ones with `.gitkeep`. `design-src/` is the
  design supplier's delivery area and is **never deployed**.
  **Done when:** the tree matches §9.1 exactly — a later diff against the plan should be empty.

- [ ] **2.2 — `app/config.py`**
  `Base` / `Dev` / `Test` / `Prod`. Loads `.env` via python-dotenv in dev only.
  **Done when:** `APP_ENV=production` with a missing `SECRET_KEY` refuses to boot.

- [ ] **2.3 — `.env.example`**
  Transcribe §16.1 verbatim — all six groups: Core, Database, Session & admin, Uploads & storage,
  Contact form, Cache & limits, Privacy & retention, Logging.
  **Done when:** every `os.environ` lookup in the codebase has a matching line, and no secret has a
  real value in the file.

- [ ] **2.4 — `app/extensions.py`**
  `db`, `migrate`, `login_manager`, `csrf`, `bcrypt`, `limiter`, `cache`, `mail` — instantiated but
  unbound, so the app factory stays testable.
  **Done when:** a test can build two apps with different configs in one process.

- [ ] **2.5 — `app/__init__.py` — the app factory**
  `create_app(config_name)`: load config, configure logging, register **6 blueprints**, install the
  Bangla error pages (404 / 403 / 419 / 429 / 500), add the `before_request` hooks for locale,
  maintenance mode and admin activity (§9.2).
  **Done when:** `/health` returns 200 and an unknown URL renders the Bangla 404 page.

- [ ] **2.6 — Security headers in `after_request`**
  CSP, `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`,
  HSTS in production — verbatim from §12.3.
  **Done when:** `securityheaders.com` grades **A** on a locally-served page, or every gap is
  explained.

- [ ] **2.7 — Jinja filters and globals**
  `bn_num`, `bn_date`, `bn_currency`, `mask_none`, `section_render` (§9.2).
  **Done when:** `bn_date(date(2026, 9, 23))` renders `২৩ সেপ্টেম্বর ২০২৬` and `bn_num(124)` renders
  `১২৪`.

- [ ] **2.8 — `app/constants.py`**
  Enums: outcome types, education levels, consent sources, the 13 section types, message statuses.
  **Done when:** no enum value is written as a string literal anywhere else in the codebase.

- [ ] **2.9 — `app/models/base.py`**
  `TimestampMixin` (`created_at` / `updated_at`), `SoftDeleteMixin`, and the admin-written
  `created_by` / `updated_by` pair.
  **Done when:** models inherit them rather than redeclaring the columns.

- [ ] **2.10 — The 17 models, in five files**
  `admin.py` → `admin_users` (1) · `cms.py` → `pages`, `page_sections`, `faqs`, `stats`, `settings`
  (5) · `people.py` → `participants`, `consent_events` (2) · `course.py` → `courses`,
  `course_modules`, `institutions` (3) · `media.py` → `media_items` (1).
  Plus `contact_messages`, `audit_logs`, `imports`, `login_attempts`, `backups`.
  Every column exactly as §10 specifies. Every index exactly as §10 specifies.
  **Done when:** `len(db.metadata.tables) == 17` and a test asserts it, so a table can never be
  added or lost silently.

- [ ] **2.11 — The database-level publish guard** ⚠ **highest-value step in the project**
  On `participants` (§10.3):
  ```sql
  CHECK (is_published = 0 OR (consent_publication = 1 AND consent_date IS NOT NULL))
  ```
  **Done when:** a test inserts `is_published = 1, consent_publication = 0` **directly via SQL**,
  bypassing the ORM, and the database **rejects it**. Prove it on both SQLite and MySQL — this is
  the belt in "belt and braces" (R1).

- [ ] **2.12 — `flask check-config`**
  Verifies env vars, the DB charset is `utf8mb4`, writable dirs, and that `app.css` exists (§8.2).
  Hard-fails rather than warning on the charset.
  **Done when:** it exits non-zero against a `latin1` database (S10, R5).

- [ ] **2.13 — `flask seed`**
  Idempotent. 1 institution (Sylhet BUTTC) · 1 course + 6 modules · ~10 stats · ~12 FAQs ·
  8 page records with their sections · ~40 settings · 1 admin user (§10.6). Seed data lives in
  `app/seeds/*.json` so it can be corrected without a code change.
  **Done when:** running it twice changes nothing, and a second run is proven not to duplicate rows.

- [ ] **2.14 — `flask create-admin`**
  Email + password, bcrypt cost 12, TOTP enrolment with 10 recovery codes shown **once** (§12.1).
  **Done when:** the QR renders, a valid TOTP is accepted and a recovery code works exactly once.

- [ ] **2.15 — `flask seed-demo-participants`** — required, not optional
  Bangla-named fixtures that deliberately include: consented · **non-consented** ·
  **consent-withdrawn** · **missing `consent_date`** · a single-participant outcome (to exercise the
  `<5` suppression) · zero-outcome records (§8.2, §19.3).
  **Done when:** the command runs and the consent dashboard immediately shows all four states.
  The consent rules in §5.3 **cannot** be verified against three happy-path rows.

- [ ] **2.16 — `flask render-check --all`**
  Renders every public route against fixtures, catching undefined template variables (§8.2).
  **Done when:** it runs clean, and fails loudly when a template variable is deliberately removed.

- [ ] **2.17 — `pytest` skeleton + `conftest.py`**
  App and DB fixtures, a test client, and the fixture set from §19.3: Bangla edge cases (conjunct
  names like `বিষ্ণুপ্রসাদ`, zero-width joiners, NFC/NFD, Bangla digits, 60-character names),
  the consent matrix, malformed CSVs, and the odd uploads.
  **Done when:** `pytest` runs green with a coverage report.

- [ ] **2.18 — `ruff` and `mypy` configuration**
  Add `ignore_missing_imports` for the Flask extensions that ship no stubs (Flask-Bcrypt, Flask-Mail,
  Flask-Caching, Flask-Limiter) rather than silencing whole modules.
  **Done when:** both tools run clean on the skeleton and are wired into the gates.

- [ ] **2.19 — `ci.yml` (§17.5)**
  `npm ci` → `css:build` → `git diff --exit-code app/static/css/app.css` (**the drift gate**) →
  `css:check` → `plan_lint.py` → `ruff` → `mypy` → `pytest --cov` → `pip-audit` → `bandit -r app`.
  **Done when:** a deliberately stale `app.css` fails the pipeline and names the fix command (R6).

- [ ] **2.20 — `.htaccess` + `passenger_wsgi.py` + `run.py`**
  HTTPS forced, the `public/` docroot, `passenger_wsgi.py` exposing `application`.
  **Done when:** a local run mirrors what Passenger will do.

- [ ] **2.21 — Commit the first three commits (§23.1)**
  1. `chore: project skeleton, config, check-config CLI, Tailwind v4 scaffold + CSS drift gate in CI`
  2. `feat(db): schema, migrations, and the institution + course seeder`
  3. `feat(public): home page from the design tokens with a real section renderer`
  **Done when:** commit 2 and 3 land in Phase 2/3 as written, not squashed into one.

### Exit gate

- [ ] `flask check-config` is all-green on dev
- [ ] `flask seed` is idempotent; `seed-demo-participants` produces all four consent states
- [ ] `len(db.metadata.tables) == 17`
- [ ] **The DB `CHECK` constraint rejects a non-consented publish on both engines**
- [ ] Migrations are reversible (`flask db downgrade` then `upgrade` is clean)
- [ ] CI green, including the CSS drift gate

---

## Phase 3 — Public read-only site

**Goal:** the entire public site, rendering **seeded** content. The department can read it; they
cannot edit it yet. **This is the Session 1 deliverable.**
**Days:** 6 · **Session:** 1 · **Depends on:** Phase 2 · **Builds `plan.md` §4.2, §6, §9.3, §14, §15**

### Steps

- [ ] **3.1 — `SectionBase` and the schema validator (§9.3)**
  `schema`, `validate()`, `render_context()`. Field types: `str`, `text`, `ref`, `cta`, `list`, `int`,
  `bool`, `enum`.
  **Done when:** a malformed payload raises with the field name and the reason — not a generic error.

- [ ] **3.2 — The 13 section modules + their 13 templates**
  `hero` · `rich_text` · `stat_strip` · `fact_list` · `module_list` · `participant_grid` ·
  `gallery_strip` · `media_feature` · `faq_list` · `quote` · `cta_band` · `institution_card` ·
  `timeline`.
  **Done when:** each has a unit test for a valid payload and for a rejected one, and each renders on
  the kitchen-sink page.

- [ ] **3.3 — Section render rules (§9.3)**
  An **unknown type raises** and is reported in the admin, never skipped · a section failing
  validation is **not rendered** and is flagged · sections render in `sort_order` ·
  `is_visible = false` is **skipped entirely**, not hidden with CSS.
  **Done when:** all four behaviours have a test.

- [ ] **3.4 — `app/services/page_service.py`**
  Fetch a page's sections, dispatch to the section modules, assemble the context.
  **Done when:** a page with zero visible sections renders an honest empty state, not a broken layout.

- [ ] **3.5 — Public routes 1–8 (§6.2)**
  `/` · `/course` · `/batch-1` · `/batch-1/<slug>` · `/gallery` · `/about` · `/contact` · `/privacy`.
  **Done when:** each returns 200 against seed data, and each has an integration test.

- [ ] **3.6 — `/media/<path>` — signed, expiring URLs (route 13)**
  `itsdangerous` `URLSafeTimedSerializer`. Never executable; `nosniff`; no directory listing;
  `Cache-Control: public, max-age=31536000, immutable`.
  **Done when:** an expired signature and a tampered signature are both rejected by test.

- [ ] **3.7 — SEO surface (routes 9, 10)**
  `sitemap.xml` from published pages **and consented participant profiles**, cached 1 h, regenerated
  on publish. `robots.txt` allowing public pages and participant profiles, disallowing `/admin/`
  **and the configured admin prefix**.
  **Done when:** a non-consented participant's slug is **absent** from the sitemap — this is a privacy
  test, not an SEO test.

- [ ] **3.8 — `/health` (route 11)**
  JSON: `{"db":"ok","css":"ok"}`. This is what UptimeRobot watches and what the deploy verifies.
  **Done when:** it reports `db: fail` when the database is unreachable.

- [ ] **3.9 — JSON-LD (§15.3)**
  `Organization` (DYD) · `Course` · `Person` on participant profiles · `BreadcrumbList` · `FAQPage`.
  **Done when:** the Rich Results test parses every type with no errors.

- [ ] **3.10 — Contact form (route 7)**
  Honeypot + minimum-time-on-form + Cloudflare Turnstile + 3 submissions per IP per hour. Writes
  `contact_messages`. Mail via `MAIL_PROVIDER` (`dryrun` in dev).
  **Done when:** a bot-shaped submission is rejected, a human one is stored, and the 4th submission
  in an hour is rate-limited.

- [ ] **3.11 — PWA (route 12, §15.2)**
  `manifest.json` (`lang: bn`, `theme_color: #0B4A32`, `background_color: #FAF9F4`) · `sw.js`
  (cache-first `static/**`, network-first pages, **never** cache `/admin/*` or any POST) · a Bangla
  offline page carrying the hotline.
  **Done when:** the service worker provably does not cache an admin URL, and offline renders the
  Bangla page.

- [ ] **3.12 — Privacy page content (§12.4)**
  Must state what participant data is published, that **photographs are not published**, how consent
  is recorded, **how to withdraw consent**, and the named withdrawal contact.
  **Done when:** a reviewer can answer "how do I get myself removed?" using only that page.

- [ ] **3.13 — Error pages**
  404 / 403 / 419 / 429 / 500 in Bangla, each with a route back into the site.
  **Done when:** all five are reachable in dev and none shows a stack trace.

- [ ] **3.14 — Full a11y pass on the public site (§7.8, §19.1)**
  axe-core plus manual keyboard traversal.
  **Done when:** **zero** serious or critical violations on every public page.

- [ ] **3.15 — Performance pass against the §15.1 budget**
  LCP < 2.5 s on simulated 3G · CLS < 0.05 · INP < 200 ms · JS < 30 KB gzipped · CSS < 45 KB gzipped ·
  home page < 600 KB.
  **Done when:** every metric is measured and recorded, not assumed.

- [ ] **3.16 — Participant profile template (§5.5)**
  Name largest, then ruled label-value pairs, optional pull quote, the document rule, the
  `ব্যাচ ১ · সিলেট BUTTC` footer line, and prev/next navigation.
  **Done when:** there is **no** photograph, no image placeholder and no silhouette graphic. The page
  is unmistakably complete without one.

### Exit gate — ⬅ **Session 1 deliverable**

- [ ] All 8 public pages render from seeded content at 360 / 768 / 1440
- [ ] `flask render-check --all` clean
- [ ] Zero serious/critical a11y violations
- [ ] Performance budget met and recorded
- [ ] A non-consented participant is absent from `/batch-1`, the counts, the statistics **and** the sitemap
- [ ] Deployable to staging as a read-only site

---

## Phase 4 — Admin: pages & sections

**Goal:** the admin can change every word and image without a developer.
**Days:** 6 · **Session:** 2 · **Depends on:** Phase 3 · **Builds `plan.md` §11.1, §11.2, §12**

### Steps

- [ ] **4.1 — Auth: `/login`, `/logout` (routes 14, 15)**
  Email + password at bcrypt cost 12 · **mandatory TOTP** · 3 attempts per 10 min then a 30-minute
  lock · every attempt written to `login_attempts` · session id rotated at login.
  **Done when:** each of those five behaviours has a test, including that the lockout actually blocks
  a *correct* password.

- [ ] **4.2 — Session policy (§12.1)**
  30 min idle, 8 h absolute, `Secure` + `HttpOnly` + `SameSite=Lax`.
  **Done when:** an idle session is rejected and a fresh one is not.

- [ ] **4.3 — The non-guessable admin path (S13)**
  Blueprint mounts at `ADMIN_URL_PREFIX` (`ops-sylhet`). `/admin` returns **404**, not a redirect.
  **Done when:** a test asserts `/admin` is a 404 — a redirect would leak the real path.

- [ ] **4.4 — Optional IP allowlist**
  `ADMIN_IP_ALLOWLIST` as a CIDR list; empty means off. Recommended once live.
  **Done when:** a non-matching IP is refused when the list is set, and nothing changes when it is empty.

- [ ] **4.5 — Admin shell: layout, nav, `DataTable`, sticky filter bar**
  The admin density skin from step 1.11, plus the `KpiCard` dashboard pieces.
  **Done when:** every screen has a consistent header, breadcrumb and flash-message area.

- [ ] **4.6 — Dashboard (route 16)**
  Participant counts (total / published / awaiting consent / withdrawn) · pages published vs draft ·
  recent admin activity · backup status.
  **Done when:** the four consent counts reconcile exactly with the seeded fixture states.

- [ ] **4.7 — `audit_service.py` + audit rows on every mutation (§12.1)**
  Actor, action, entity, before/after JSON, IP. Written **inside** the same transaction as the change.
  **Done when:** a test asserts that a rolled-back change leaves **no** audit row — otherwise the log
  lies.

- [ ] **4.8 — Pages list + create (route 17)**
  Draft/published state, nav reordering, soft delete.
  **Done when:** reordering the nav changes the header order on the public site.

- [ ] **4.9 — The sections editor (route 18) — the core CMS screen (§11.2)**
  Add from the 13-type picker (with a one-line description each) · type-specific forms generated from
  the section schema · Bangla field-level validation.
  **Done when:** every one of the 13 types can be added, edited and saved.

- [ ] **4.10 — Reorder with a keyboard alternative**
  Drag handle **and** move up/down buttons. Drag-only is not acceptable (§11.2, §7.8).
  **Done when:** a reorder is completed end-to-end using only the keyboard.

- [ ] **4.11 — Visibility toggle, distinct from delete**
  `is_visible = false` renders nothing. Delete confirms, then soft-deletes and is recoverable from
  the audit log.
  **Done when:** a hidden section is provably absent from the HTML, not `display:none`.

- [ ] **4.12 — Live preview in an iframe at 360 / 768 / 1440**
  The real template with the real payload.
  **Done when:** editing a field updates the preview without a full page reload.

- [ ] **4.13 — Publish gate (route 19)**
  A page cannot publish if any section fails validation **or** it has zero visible sections. The error
  **names the offending section**.
  **Done when:** both conditions block publish with a message naming the section (R7).

- [ ] **4.14 — Unsaved-changes prompt + 30 s autosave to a draft row**
  **Done when:** navigating away with unsaved edits prompts, and a browser crash loses at most 30 s.

### Exit gate

- [ ] `/admin` is a 404; the configured prefix serves the login
- [ ] Wrong password 3× locks the account, and the lockout blocks a correct password too
- [ ] Every admin mutation writes an audit row — and a rolled-back one does not
- [ ] All 13 section types can be created, reordered (by keyboard), hidden and previewed
- [ ] Publish is blocked by an invalid or empty page, naming the section
- [ ] Journey 6 of §19.2 passes: add, reorder, toggle, preview, publish, see it live

---

## Phase 5 — Admin: participants & consent

**Goal:** the highest-risk surface in the product, built defensively.
**Days:** 5 · **Session:** 2 · **Depends on:** Phase 4 · **Builds `plan.md` §5, §11.3, §11.4**

### Steps

- [ ] **5.1 — Participant list + filters (route 20)**
  Filters: outcome · consent state · published state · batch. Free-text search over `search_blob`.
  Sortable columns · 50 per page · column chooser.
  **Done when:** every filter combination is shareable as a query parameter.

- [ ] **5.2 — CSV/XLSX export of the filtered set (routes 20 → export)**
  Watermarked with requester and timestamp.
  **Done when:** the export contains **exactly** the current filter's rows and carries the watermark.

- [ ] **5.3 — Participant create/edit (routes 21, 22)**
  Exactly the §5.1 fields. **No prohibited field exists in the form** (S2, S3).
  **Done when:** a reviewer inspects the form and finds no image field and no phone/email/NID/dob
  input — because the columns do not exist either.

- [ ] **5.4 — Consent panel (route 23)**
  `consent_publication` · `consent_date` · `consent_source` · `consent_notes`, plus the separate
  `quote_consented` tick (§5.3 rule 5). Writes a `consent_events` row.
  **Done when:** publishing with a missing `consent_date` shows a **blocking Bangla message naming
  the missing field**.

- [ ] **5.5 — `consent_service.py` — grant / withdraw / audit**
  Withdrawal sets `consent_withdrawn_at`, clears `is_published`, writes the event and **invalidates
  the participant + statistics caches in the same transaction** (S5).
  **Done when:** a test withdraws consent and immediately asserts the profile is gone **without a
  manual cache clear**. This is R2 — the one place where a caching bug is also a privacy bug.

- [ ] **5.6 — Consent dashboard (route 24)**
  Consented · not consented · withdrawn · **missing `consent_date`** (§5.3).
  **Done when:** the four counts reconcile with the fixtures, and the missing-date list is the first
  thing on the screen.

- [ ] **5.7 — Bulk actions**
  Publish · unpublish · set outcome · export. **Bulk publish skips every non-consented record and
  reports how many it skipped** (§11.3).
  **Done when:** selecting "all" on a mixed set publishes only the consented rows and returns the
  skip count. It must never publish a name because someone selected everything (R4).

- [ ] **5.8 — Unpublished badge (§5.3 rule 3)**
  Records without consent are badged **"প্রকাশ করা হয়নি"** and excluded from every public query,
  count, statistic and search index — but **not** deleted, so the cohort total stays honest.
  **Done when:** the admin total and the public total differ by exactly the non-consented count.

- [ ] **5.9 — `import_export_service.py` — CSV import (route 25, §11.4)**
  Five stages: detect encoding/delimiter → map columns (saved as a reusable preset) → **dry run** →
  transactional commit → `imports` audit row with counts and file hash.
  **Done when:** all five stages work and the dry run writes **nothing**.

- [ ] **5.10 — Import tolerance**
  Bangla names from Excel-on-Windows · UTF-8 and UTF-8-BOM · semicolon delimiters · header typos ·
  zero-width joiners in conjuncts · duplicate names · consent recorded as `ha` / `হ্যাঁ` / `yes` / `1`.
  **Done when:** the §19.3 import fixtures pass, including 500 rows with 40 deliberate errors.

- [ ] **5.11 — Import defaults to unpublished**
  Import never publishes. Publishing is a separate, explicit action (R4).
  **Done when:** a commit leaves every imported row unpublished, whatever the CSV said about consent.

- [ ] **5.12 — The consent-matrix test suite (§19.3)**
  granted · absent · withdrawn · **missing date** · **date in the future**.
  **Done when:** each state has an explicit test asserting visibility on the public site. This suite
  is the project's safety net; write it before you believe the feature works.

### Exit gate

- [ ] Journey 2 of §19.2 passes: a non-consented participant is invisible — direct slug 404, absent from lists, counts and statistics
- [ ] Journey 3 passes: withdrawal propagates **immediately**, cache included
- [ ] Journey 4 passes: the publish guard holds at the form, the model **and** the database
- [ ] Journey 7 passes: dry run writes nothing; commit writes only valid rows + an error report
- [ ] Bulk publish skips non-consented rows and reports the count
- [ ] The admin total and the public total differ by exactly the non-consented count

---

## Phase 6 — Admin: remaining content

**Goal:** everything the admin needs that is not pages or participants.
**Days:** 4 · **Session:** 3 · **Depends on:** Phase 5 · **Builds `plan.md` §11.1, §13, §16.2**

### Steps

- [ ] **6.1 — Course + modules (route 26)**
  Course record, module list with drag-to-reorder and inline edit (§11.1).
  **Done when:** reordering modules changes the public Course page order.

- [ ] **6.2 — Institutions (route 27)**
  Sylhet BUTTC and the partner JV record. `name_bn`, `role_bn`, `address_bn`, contact fields,
  `logo_id` (Q2, Q3 → R11).
  **Done when:** the Course, About and every participant profile footer show the confirmed names.

- [ ] **6.3 — Media library + upload pipeline (route 28, §13.1)**
  `upload → size check (≤6 MB) → magic-byte sniff (NOT extension) → Pillow open → EXIF strip →
  sRGB → resize to 2000px long edge → re-encode (JPEG q82 / WebP q80) → thumbs 640 & 320 →
  random filename → write to UPLOAD_ROOT outside the webroot → MediaItem row`.
  **Done when:** each stage is individually tested, not just the happy path.

- [ ] **6.4 — Upload constraints (§13.2)**
  JPEG/PNG/WebP only — **no SVG** (SVG can carry script) · ≥ 640px wide · `alt_bn` **required on
  save** · video by **link only**, never a hosted file.
  **Done when:** an SVG upload is refused and an upload with no `alt_bn` cannot be saved.

- [ ] **6.5 — Upload hostile cases (§19.3)**
  A 12 MB JPEG · a `.jpg` that is really a PDF · a `.png` with EXIF GPS · a CMYK JPEG · a 1×1px image ·
  a filename containing a null byte.
  **Done when:** all six are handled and each has a test. EXIF GPS must be **gone** after processing.

- [ ] **6.6 — `used_count` + delete protection (§13.2)**
  An image in use cannot be deleted. Blocks are prevented, not broken (R15).
  **Done when:** deleting an in-use image is refused with a message naming where it is used.

- [ ] **6.7 — Stats (route 29)**
  Manual or computed. `stats_service` computes consented-only aggregates, cached 300 s.
  **Done when:** a computed stat equals a hand-count of the consented fixture rows.

- [ ] **6.8 — The `<5` suppression rule (§5.4)** ⚠
  Any cell derived from **fewer than 5 records** renders `—`. Driven by
  `STATS_SUPPRESS_BELOW`, default 5.
  **Done when:** a fixture with a 2-person outcome category renders `—` in that cell, and the raw
  value **never reaches the template context** — suppressing in the template is not suppressing.
  (S6, R9, journey 5 of §19.2.)

- [ ] **6.9 — FAQs (route 30)**
  Grouped question/answer list, ordering, `is_active`.
  **Done when:** the FAQPage JSON-LD reflects exactly the active FAQs.

- [ ] **6.10 — Settings (route 31, §16.2)**
  All 15 CMS-editable settings. Secrets stay in `.env`, are shown **write-only**, and are **never**
  stored in the database.
  **Done when:** saving a secret writes nothing to the `settings` table — assert this in a test.

- [ ] **6.11 — Feature flags (§16.3)**
  `maintenance_mode` · `contact_form_enabled` · `participant_pages_enabled` ·
  `participant_search_enabled` · `gallery_enabled` · `stats_published`. Checked server-side.
  **Done when:** each flag off renders the Bangla **"সাময়িকভাবে বন্ধ"** state — never a broken page.

- [ ] **6.12 — Messages (route 32)**
  Contact submissions with status workflow `new → read → replied → closed`.
  **Done when:** a reply marks the message and the status survives a reload.

- [ ] **6.13 — Audit viewer (route 33)**
  Every admin write with a before/after diff, filterable by actor, entity and date.
  **Done when:** editing a page and then viewing the audit shows exactly which field changed.

- [ ] **6.14 — Backups screen (route 34) + `backup_service.py`**
  List and trigger. `cron_backup.sh` writes `mysqldump --single-transaction` plus an uploads tar with
  the 7 daily / 4 weekly / 3 monthly rotation (§17.6).
  **Done when:** a backup is produced and **one restore is rehearsed onto staging**. An untested
  backup is not a backup.

- [ ] **6.15 — `cron_retention.sh` (§17.6)**
  Purge contact messages older than 12 months and audit rows older than 36 months.
  **Done when:** it runs against fixtures with known ages and deletes exactly the right rows.

- [ ] **6.16 — `cron_stats.sh`**
  Hourly statistics cache refresh.
  **Done when:** the cache timestamp advances on schedule.

### Exit gate

- [ ] Every admin screen in §11.1 exists and is usable
- [ ] Media pipeline complete, with all six hostile upload cases handled
- [ ] `<5` suppression proven at the service layer, not the template
- [ ] Settings can never store a secret in the database
- [ ] A restore has been rehearsed
- [ ] `used_count` prevents deleting an in-use image

---

## Phase 7 — Participant browsing

**Goal:** the one genuinely interactive public surface.
**Days:** 2 · **Session:** 2 · **Depends on:** Phase 5 · **Builds `plan.md` §6.4, §5.4**

### Steps

- [ ] **7.1 — `/batch-1` search**
  Bangla **or** Latin substring over `name_bn` / `name_en`, normalised: NFC, zero-width characters
  stripped for matching (but **preserved** in display fields).
  **Done when:** searching `বিষ্ণু` and a zero-width-joined variant return the same person, and the
  name still renders with its joiner intact.

- [ ] **7.2 — Outcome filter + sort**
  Filter: employment · freelancing · further_study · business · teaching. Sort: Bangla collation by
  name, and recently added.
  **Done when:** Bangla name sorting is correct — `অ` sorts before `ক`, not by code point.

- [ ] **7.3 — Pagination + result count**
  24 per page (`PARTICIPANTS_PER_PAGE`). Count reads `"১২৪ জন প্রশিক্ষণার্থী"` in Bangla numerals and
  always reflects the **active** filters.
  **Done when:** the count matches the filtered result set, not the total.

- [ ] **7.4 — Every filter is a query parameter**
  Shareable and back-button-safe. No JavaScript required. JS only enhances (debounced search, no
  full reload).
  **Done when:** with JavaScript disabled, filtering, sorting and paging all still work.

- [ ] **7.5 — Print stylesheet**
  The register prints as a clean document (§8.1 rule 5).
  **Done when:** printing `/batch-1` produces a readable ruled list with no nav, no buttons and no
  clipped columns.

- [ ] **7.6 — Enumeration hardening (§12.2)**
  Rate-limit the filter endpoint · **no incremental IDs anywhere in a public URL** — slugs only.
  **Done when:** `/batch-1/1` is a 404 and `/batch-1/rupa-akter` is a 200.

- [ ] **7.7 — Empty, loading and error states (§19.4)**
  **Done when:** a filter matching nobody shows a Bangla empty state with a way to clear it.

### Exit gate

- [ ] Journey 1 of §19.2 passes: filter by outcome, search by name in Bangla, open a profile
- [ ] Filtering, sorting and paging work with **JavaScript disabled**
- [ ] Bangla collation is correct
- [ ] `/batch-1/<integer>` is a 404
- [ ] Print output is usable

---

## Phase 8 — Hardening

**Goal:** prove the security, privacy and performance claims rather than asserting them.
**Days:** 3 · **Session:** 3 · **Depends on:** Phases 6, 7 · **Builds `plan.md` §12, §19**

### Steps

- [ ] **8.1 — Work the §12 checklist**
  CSRF on every POST · no `|safe` on any user content · SQLAlchemy parameterised queries only ·
  uploads outside the webroot with magic-byte sniffing · `secure_filename` + allowlist + `realpath`
  containment (path traversal) · clickjacking · HSTS.
  **Done when:** each is verified, not assumed, and each has a test or a written manual check.

- [ ] **8.2 — **The bleach pre-strip — apply the verified finding** ⚠
  `bleach.clean(strip=True)` **removes disallowed tags but keeps their text**: `<p>ok</p><script>alert(1)</script>`
  becomes `<p>ok</p>alert(1)`. Inert once Jinja escapes it, but it renders as junk on a government
  page. `app/security/sanitize.py` must pre-strip before bleaching:
  ```python
  html = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
  ```
  Applied on save **and** on render (§9.3 rule 3).
  **Done when:** a fixture containing `<script>`, `<style>` and a `javascript:` href renders as clean
  Bangla prose with no residue and no injected attribute.

- [ ] **8.3 — **`RATELIMIT_HEADERS_ENABLED = True`** — apply the verified finding** ⚠
  Flask-Limiter v4 emits **no** `X-RateLimit-*` headers by default, which makes §12's limits
  invisible to clients and untestable in the suite.
  **Done when:** `X-RateLimit-Limit` and friends appear on a limited route.

- [ ] **8.4 — Reach the coverage gate**
  70% on `app/services` (§19.1), with the §19.2 journeys covered end to end.
  **Done when:** the report shows ≥70% on `app/services` **and** every route in §6.2 has an
  integration test asserting status, auth, filters and pagination.

- [ ] **8.5 — Install Playwright browsers and write the E2E suite**
  `.venv\Scripts\python.exe -m playwright install chromium` (~150 MB, deferred from setup).
  Then the 8 journeys of §19.2.
  **Done when:** all 8 journeys pass. Journeys 2, 3, 4 and 5 are the ones that protect real people —
  they are not optional.

- [ ] **8.6 — Visual regression baselines**
  5 public pages at 360 / 768 / 1440, screenshot-tracked (§19.1).
  **Done when:** a deliberate 4px padding change fails the visual diff.

- [ ] **8.7 — Security scanners**
  `bandit -r app` and `pip-audit` over the pinned set.
  **Done when:** **zero high** findings. Each remaining medium/low is either fixed or written down
  with a reason.

- [ ] **8.8 — Load test with locust**
  300 concurrent reader sessions.
  **Done when:** no 5xx and p95 < 1.5 s. Record the number; do not round it.

- [ ] **8.9 — Performance budget re-verification on real content**
  Not fixtures. Real participant count, real gallery.
  **Done when:** the §15.1 budget still holds with realistic data volumes — pagination and search are
  where this usually breaks.

- [ ] **8.10 — XSS and traversal probes**
  Crafted `rich_text` payloads · a filename with `../` · a signed media URL with a tampered payload.
  **Done when:** all are refused, each with a test.

- [ ] **8.11 — The §19.4 Definition of Done sweep**
  Walk all 14 checkboxes across every screen built so far. Empty/loading/error/403/404 states are the
  ones normally skipped.
  **Done when:** every screen has all four states implemented.

### Exit gate

- [ ] All 8 journeys of §19.2 pass
- [ ] Zero high security findings; ≥70% coverage on `app/services`
- [ ] Every route in §6.2 has an integration test
- [ ] Performance budget holds on realistic data volumes
- [ ] The bleach and rate-limit-header findings are fixed and tested
- [ ] No screen is missing its empty, loading, error or 404 state

---

## Phase 9 — Deploy & handover

**Goal:** get it live, and make sure it stays live without us.
**Days:** 2 · **Session:** 3 · **Depends on:** Phase 8 · **Builds `plan.md` §17, §18**

### Steps

- [ ] **9.1 — One-time server setup (§17.2)**
  Subdomain → AutoSSL → MySQL with `utf8mb4_unicode_ci` → Setup Python App (3.12, `passenger_wsgi.py`)
  → upload root **outside the webroot** with `chmod 750` → `.env` with `chmod 600` → `pip install
  -r requirements.txt` → `flask db upgrade && flask seed && flask create-admin` → `flask check-config`
  all-green → `touch tmp/restart.txt`.
  **Done when:** `check-config` is green on the server.

- [ ] **9.2 — `deploy.sh` (§17.3)**
  ssh-agent for the passphrase key, rsync → tar fallback. Flags: `--setup --install-deps --with-db
  --setup-cron --migrate --seed --build-css --check-css --allow-stale-css --backup --full`.
  **Done when:** every flag does what it says. Host credentials come from environment variables and
  are **never** written into the script or this repo (§17.1).

- [ ] **9.3 — The seven pre-flight aborts**
  1. SSH key present / agent loaded · 2. auth succeeds · 3. remote app root exists, >500 MB free ·
  4. local tree clean (warn + 5 s) · 5. **hard guard: the remote path is NOT the national app root**
  (S9) · 6. **CSS freshness** — `app.css` newer than `source.css` and every template ·
  7. optional build/check.
  **Done when:** each abort is triggered deliberately and returns its documented exit code. Pre-flight
  #5 is the one that protects a live government site.

- [ ] **9.4 — Sync excludes** (§17.3)
  `.env*` · `instance/*.db` · `Keys/` · `PEM/` · `var/` · `uploads/` · `.git/` · `.htaccess` ·
  `assets/` · `design-src/` · `node_modules` · `package*.json` · `tests/` · `docs/` · `*.css.map`.
  **`app/static/css/app.css` IS synced** — it is the shipped artefact.
  **Done when:** a post-deploy listing of the app root contains no test, no source CSS and no secret.

- [ ] **9.5 — The 12 deploy smoke tests (§17.3)**
  Including: `GET /admin → 404` · `robots.txt` disallows the configured prefix · `sitemap.xml` is
  valid XML · `/health` returns `{"db":"ok","css":"ok"}` · and the privacy one —
  **a non-consented participant slug returns 404**.
  **Done when:** a deliberate failure in any one of them fails the deploy.

- [ ] **9.6 — `deploy.sh` exit codes**
  `0` ok · `1` pre-flight · `2` auth · `3` sync · `4` remote · `5` smoke · `6` config · `7` stale CSS.
  **Done when:** each is reproducible on demand.

- [ ] **9.7 — `rollback.sh` (§17.4)**
  Lists the last 10 releases; restores one over the app root excluding `.env` and `.htaccess`;
  optional `flask db downgrade` behind `--db` with a loud data-loss warning; restarts Passenger;
  re-runs the same smoke tests.
  **Done when:** **a rollback is rehearsed on staging** and the smoke tests pass afterwards.

- [ ] **9.8 — `deploy.yml` (§17.5)**
  Triggered by a push to `main` or manual dispatch, gated by **blocking job 1**: `css:build` with the
  drift check, `flask render-check --all`, and the ban-list check. A `concurrency` group prevents
  racing deploys. Secrets: `DEPLOY_SSH_KEY`, `DEPLOY_SSH_PASSPHRASE`, `DEPLOY_HOST`, `DEPLOY_USER`,
  `DEPLOY_PORT`, `DEPLOY_APP_PATH`, `DEPLOY_URL`.
  **Done when:** a failing job 1 blocks the deploy outright.
  > **A push to `main` is a production release (S8).** Never push without explicit instruction.

- [ ] **9.9 — Cron (§17.6)**
  `cron_backup.sh` 02:15 daily · `cron_retention.sh` 03:30 Sunday · `cron_stats.sh` hourly.
  **Done when:** all three have run at least once on the server and their output is in `var/logs/`.

- [ ] **9.10 — Monitoring**
  UptimeRobot on `/health` every 5 min, alerting to a **real** inbox. Optional `sentry-sdk[flask]`.
  Rotating `var/logs/app.log` at 10 MB × 5. Admin email on 5xx or a failed backup.
  **Done when:** a deliberately stopped app produces an alert in a real inbox.

- [ ] **9.11 — Admin account hardening**
  TOTP enrolled, 10 recovery codes stored safely off the machine, optional IP allowlist enabled,
  admin prefix confirmed non-guessable.
  **Done when:** a recovery code works exactly once and a second use is refused.

- [ ] **9.12 — Import the real Batch 1 roster (§18.2 workflow 1)**
  Prepare the CSV with the §5.1 columns only — **no phone, email or ID numbers** · upload and map ·
  **dry run** · fix the source for missing fields, absent consent and duplicate names · commit ·
  open the consent dashboard · bulk publish (non-consented rows are skipped and counted) · spot-check
  5 profiles, including on a phone.
  **Done when:** the consented count on the dashboard equals the number of profiles visible publicly.

- [ ] **9.13 — The go-live checklist (§17.7)** — all 18 boxes
  Including: a non-consented participant returns 404 · a withdrawn consent disappears **immediately**
  with the cache invalidated · the privacy page names the published field set and the withdrawal
  route · securityheaders.com grade **A** · ssllabs **A** · renders correctly in Bangla at 360px on a
  real phone · one restore rehearsed · rollback rehearsed · DYD Sylhet project director sign-off.

- [ ] **9.14 — `ADMIN_GUIDE.md` — in Bangla, screenshot-annotated**
  Pages and sections · participants and consent · media · institution and course · plus the two
  workflows from §18.2. This is what stops the CMS becoming shelfware (R13).

- [ ] **9.15 — `RUNBOOK.md` — §18 in operational form**
  Regular tasks (daily/weekly/monthly/quarterly) · the two workflows · the escalation table with
  first action and fix · the escalation contact.
  **Done when:** someone who has never seen the project can handle a 500 and a withdrawal request
  using only this file.

- [ ] **9.16 — `DEPLOY.md`**
  Server setup, DNS, SSL, cron, environment variables.
  **Done when:** the whole deployment can be repeated from scratch on a new host.

- [ ] **9.17 — The 60-minute recorded Bangla training session (§18.4)**
  For the DYD Sylhet team, covering the two workflows end to end.
  **Done when:** recorded, and the admin has completed one full dry run unassisted.

- [ ] **9.18 — Post-launch watch**
  First week: `/health` daily, the consent dashboard weekly, the messages inbox daily, backup status
  weekly, disk usage monthly.
  **Done when:** the first week passes with no unresolved 5xx and no backup failure.

### Exit gate

- [ ] `flask check-config` green on the server
- [ ] All 12 smoke tests pass; each can fail the deploy on demand
- [ ] A rollback has been rehearsed and smoke-tested
- [ ] A restore has been rehearsed
- [ ] Monitoring alerts reach a real inbox
- [ ] Batch 1 imported; public count == consented count
- [ ] `ADMIN_GUIDE.md`, `RUNBOOK.md`, `DEPLOY.md` written and the training recorded
- [ ] All 18 go-live checklist boxes ticked
- [ ] DYD Sylhet project director sign-off

---

## Appendix A — Session checkpoints

From `plan.md` §20.1. Each session ends with something the department can **look at**, not a status
report.

| Session | Phases | Days | Elapsed | Ends with |
|---|---|---|---|---|
| **1 — Public site** | 0, 1, 2, 3 | **15** | ~3 weeks | The full public site rendering seeded content. Readable, not editable. |
| **2 — Real CMS** | 4, 5, 7 | **+13** | ~6 weeks | The admin can enter real participants and real content. |
| **3 — Complete** | 6, 8, 9 | **+9** | ~8 weeks | Live, hardened, backed up, documented, handed over. |

> **If the department needs to enter participants before Session 2**, pull the participant CRUD
> forward from Phase 5 (+3 days), making Session 1 ~3½ weeks. This is the one schedule lever worth
> taking — it moves the consent gate earlier, which is where the risk lives.

**Scope levers if time runs short (§20.2).** Recommended cut: the section editor (−4 days), because
fixed templates plus editable content records still let the admin change every word and image.

| Lever | Days | Cost |
|---|---|---|
| Skip the section editor | −4 | Layout changes need a developer |
| Skip CSV import | −3 | Painful past ~50 records |
| Skip the gallery | −2 | Fewer visuals |
| Skip PWA | −1 | No install prompt, no offline page |
| Inline the media library | −2 | No central alt-text or usage tracking |

**Never lever away:** the consent guard (S4), the cache-invalidation-on-withdrawal (S5), the `<5`
suppression (S6), or the privacy smoke test in `deploy.sh`. These are the reason the project exists in
this shape.

---

## Appendix B — Command reference

```bash
# ── Environment ───────────────────────────────────────────────────────────
.venv\Scripts\Activate.ps1                       # or: .venv\Scripts\activate.bat
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt

# ── CSS (must be run and committed after any template change) ─────────────
npm run css:build                                # compile + minify → app/static/css/app.css
npm run css:watch                                # during development
npm run css:check                                # policy gate (tools/check-css.py)

# ── Database ──────────────────────────────────────────────────────────────
flask db migrate -m "…"                          # generate
flask db upgrade                                 # apply
flask db downgrade                               # must be clean — test it

# ── Seed and admin ────────────────────────────────────────────────────────
flask seed                                       # idempotent reference data
flask seed-demo-participants --count 120 --consent-rate 0.8
flask create-admin --email you@example.com       # TOTP + 10 recovery codes

# ── Verification ──────────────────────────────────────────────────────────
flask check-config                               # env, DB charset, writable dirs, app.css
flask render-check --all                         # every public route with fixtures

# ── The gates, before every commit ────────────────────────────────────────
npm run css:build && npm run css:check
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy app
.venv\Scripts\python.exe -m pytest --cov=app
python tools/plan_lint.py                        # when plan.md changed

# ── Applicaton run (two terminals) ────────────────────────────────────────
npm run css:watch
flask run --debug

# ── Security and load (Phase 8) ───────────────────────────────────────────
.venv\Scripts\python.exe -m bandit -r app
.venv\Scripts\python.exe -m pip_audit
.venv\Scripts\python.exe -m playwright install chromium      # ~150 MB, Phase 8
.venv\Scripts\locust.exe -f tests/load/locustfile.py

# ── Deploy (Phase 9) ──────────────────────────────────────────────────────
./deploy.sh --full
./deploy.sh --migrate --restart --verify
./rollback.sh                                    # lists the last 10 releases
```

---

## Appendix C — Commit convention

One commit per completed step or coherent group. The first three are specified in `plan.md` §23.1.

| Prefix | Use |
|---|---|
| `chore:` | tooling, config, CI, dependencies |
| `feat(db):` | models, migrations, seeders |
| `feat(public):` | public routes and templates |
| `feat(admin):` | CMS screens |
| `feat(sections):` | section types and templates |
| `fix(privacy):` | anything touching consent, publication or PII — **flagged for review** |
| `docs(plan):` | changes to `plan.md` |
| `docs:` | README, guides |

**Before every commit:** the gates in Appendix B pass, and `app.css` is rebuilt and staged if any
template changed.

**Never commit:** `.env`, `instance/`, `uploads/`, `var/`, keys, `*.db`, exports.
Never `git add -A` on a tree containing derived files, and always check the file's encoding before
committing Bangla content (S10).

---

## Appendix D — Blocker register

Open questions from `plan.md` §22, ordered by what they block.

| Blocker | Question | Blocks | Risk |
|---|---|---|---|
| **Q6** | Does written consent for publication already exist for Batch 1? | **Launching with any participant name at all** | R1, R4 — critical |
| **Q2** | Is **Sylhet BUTTC** the correct full legal name and address? | Course, About, every profile, the footer | R11 |
| **Q3** | Confirm the partner JV entity for Sylhet | Course and About legal accuracy | R11 |
| **Q1** | Real Batch 1 dates | Course and Batch 1 status | — |
| **Q5** | Participant count and roster format | Pagination tuning, import shape | R10 |
| **Q4** | DYD / government logo assets | Header, footer, OG image | — |
| **Q7** | Who owns the data; the withdrawal contact | The privacy page cannot ship without this | §12.4 |
| **Q11** | Is a Bangla copy reviewer available? | Every user-facing string | — |
| **Q10** | Confirm the domain | Deploy topology, canonical URL | — |
| **Q8** | Training photographs for the gallery | Visual load — the design has no portraits | — |
| **Q9** | Is outcome tracking wanted, and who maintains it? | Participant field set and a standing commitment | — |

> **Q6 is the gate on the whole project.** Everything else can be answered late or corrected in the
> CMS. Q6 decides whether the site launches with a cohort register or with an empty one — and if
> consent does not exist, the answer is an empty register, not a hopeful one (S4).
