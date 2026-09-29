# AI Sylhet

**A documentary website for Batch 1 of the Sylhet Division AI training programme** — the
Government of Bangladesh project *"তথ্যপ্রযুক্তি জ্ঞানসম্পন্ন যুবদের কৃত্রিম বুদ্ধিমত্তা (এআই) প্রযুক্তির
মাধ্যমে দক্ষতা উন্নয়ন"*, implemented by **যুব উন্নয়ন অধিদপ্তর (Department of Youth Development)**,
Ministry of Youth & Sports.

The site documents the course as delivered in Sylhet and the cohort who took it: who they are, where
they came from, what they learned, and what they have done since.

Companion to the national site: <https://www.dydaiproject.com> · Delivered in Sylhet by
**Bholananda-Uttaran Technical Training Center** (BUTTC), Chouhatta, Sylhet Sadar
(`plan.md` §22 Q2 — resolved 2026-09-29).

---

## Status

> ✅ **Built, tested and deployable.** See [`DEPLOY.md`](DEPLOY.md) for the runbook.

| Item | State |
|---|---|
| Master plan | ✅ [`plan.md`](plan.md) — 1,797 lines, 23 sections, 109 indexed headings |
| Application | ✅ Flask + Jinja pages, the React front end, and the admin CMS |
| Database | ✅ 21 tables, migrations applied, consent enforced by two `CHECK` constraints |
| Tests | ✅ `python -m pytest -q --no-cov` |
| Gates | ✅ `npm run gates` — CSS budget, ban list, §9.1 tree audit |
| Deployment | ✅ [`DEPLOY.md`](DEPLOY.md) — alwaysdata (free plan), plus `deploy.sh`, `rollback.sh`, `cron_backup.sh` |
| Batch 1 dates, institution, roster, consent records | ⏳ pending (`plan.md` §22) |
| **Next step** | **Import the real trainees and trainers, then go live** |

---

## Running it, and deploying it

```bash
# local
.\.venv\Scripts\python.exe -m flask db upgrade      # create the tables
.\.venv\Scripts\python.exe -m flask seed            # reference data (drafts)
.\.venv\Scripts\python.exe -m flask publish-pages   # publish the pages
.\.venv\Scripts\python.exe run.py                   # http://127.0.0.1:5000

# production — alwaysdata, free plan, one command
cd ~/sylhet && ./deploy.sh
```

Two entry points, one bootstrap: `wsgi.py` is what alwaysdata's panel points at
(type **Python WSGI**, application path = that file), and `passenger_wsgi.py` is
cPanel's startup filename. Both hand over to the same place, because the one rule that
must not be got wrong twice is that `APP_ENV=production` is set **before**
`app/config.py` is imported.

`flask backup` dumps the database and the uploads directory, records a row the
**Admin → Backups** screen reads, and keeps 30 days — `cron_backup.sh` schedules it.

---

## What this is, and what it is not

It is a **documentary site with a CMS**: pages built from ordered sections, a cohort register, course
documentation and a gallery — all entered and managed by a **single admin user**.

It is **not** the operational system behind the national site. Not being built: the online
application form, admit-card / results / certificate lookups, the exam engine, student accounts and
login, the student portal, enrolment and attendance tracking, TA reporting, certificate issuance,
SMS/email notifications, or multi-role permissions. `plan.md` §2.2 lists all 12 exclusions with
reasons, and §23.3 records the earlier operational design in case that decision ever reverses.

There is exactly **one kind of user**: the admin.

---

## Participant data — the rule that matters most

The site publishes people's names. That is a consent obligation, not a styling choice.

**Published:** name · education · occupation before · what they did (outcome) — and a photograph,
if and only if they signed for one.

**Never published, and the database cannot store it:** phone · email · NID or
birth-registration number · date of birth · blood group · full address · guardian names · marks

Four things enforce this:

1. **A photograph needs its own permission** — `participants.image_consent`. It is a line of the
   consent form in its own right: permission for a name and an education level is not permission for
   a face. The checkbox sits inside the image field on the participant screen, and the register
   draws the person's initials until it is ticked.
2. **Two database `CHECK` constraints**: one refuses to store a photograph without that permission,
   the other refuses to publish a row whose consent flag is unset — so neither an application bug
   nor a hand-written script can expose someone.
3. **A participant without recorded consent is not published at all** — excluded from every query,
   count, statistic and search. Withdrawing consent unpublishes immediately, takes the photograph
   down with the name, and invalidates the cache in the same transaction.
4. **No other spelling of a picture exists** — `flask check-db` fails if `photo_path`, `image`,
   `avatar` or `media_id` ever appears on `participants`, and fails if `photo_id` exists without
   `image_consent` beside it.

Full model in `plan.md` §5; the withdrawal workflow is §18.2.

---

## Planned stack

| Layer | Choice |
|---|---|
| Language / framework | Python 3.12 · Flask 3.1 (blueprints) |
| ORM / DB | Flask-SQLAlchemy · MySQL (`utf8mb4`) in prod, SQLite in dev |
| Auth | Flask-Login + Flask-Bcrypt — one admin account, **mandatory TOTP** |
| Forms / CSRF | Flask-WTF / WTForms |
| Images | Pillow — resize, re-encode, EXIF strip |
| CSS | **Tailwind CSS v4** — compiled + minified `app/static/css/app.css` **is committed**; the server never needs Node |
| Hosting | cPanel + Phusion Passenger |
| CI/CD | GitHub Actions — CI gates every push; a push to `main` deploys |

The stack deliberately mirrors the owner's already-live Flask/cPanel project so deployment, cron and
CI patterns are proven rather than invented.

---

## Operating rules for this repo

1. **Never commit** `.env`, keys, uploaded media, databases or backups. `.gitignore` covers these
   and the deploy script excludes them. See `plan.md` §12.4.
2. **No participant PII beyond the §5.1 field set** — never in fixtures, never in logs, never in a
   commit. Test data uses invented Bangla names.
3. **No secrets in `plan.md`** — host/IP/SSH details are referenced as `<REMOTE_HOST>` etc. and
   passed to `deploy.sh` via environment variables. This file is public.
4. **Styling:** no hand-written CSS, no `<style>` blocks in Jinja, no `@apply` in templates, no
   arbitrary values. Everything resolves through Tailwind utilities in `assets/tailwind/source.css`.
   The theme wipes Tailwind's default palette, radius and shadow scales, so generic-looking utilities
   **do not compile** — the anti-slop rules are enforced by the build, not by review.
5. **Rebuild CSS** (`npm run css:build`) whenever a template changes; CI fails the build on drift.
6. **A push to `main` is a production release.** The deploy workflow is gated on a blocking
   validation job (`css:build` drift check, `render-check --all`, ban-list check), so a broken
   template fails the deploy rather than the live site. No push without the owner's instruction.
7. **The design supplier stays in `design-src/`.** They never edit `assets/tailwind/source.css`,
   anything under `app/`, or `app/static/css/app.css`. Requests go through `DESIGN-NOTES.md`
   (`plan.md` §4.2.5). The folder is excluded from the deploy sync, so it cannot reach production.

---

## Where to read more

| Looking for | Where |
|---|---|
| **Deploying this site** (alwaysdata, step by step) | [`DEPLOY.md`](DEPLOY.md) |
| The React front end, and how the two halves fit together | [`docs/FRONTEND.md`](docs/FRONTEND.md) |
| What is and is not being built | [`plan.md`](plan.md) §2 Scope & Non-Goals |
| Programme facts and coverage | §3 |
| Content model — 10 content types, 13 section types | §4 |
| Participant fields, consent model, statistics | §5 |
| Sitemap and all 34 routes | §6 |
| Visual direction, design tokens, anti-slop | §7 |
| Tailwind and local development | §8 |
| Architecture and the section renderer | §9 |
| Data model — 21 tables | §10 |
| Admin CMS screens and workflows | §11 |
| Security, 2FA, privacy commitments | §12 |
| Media pipeline | §13 |
| Bangla typography and fonts | §14 |
| Performance, PWA, SEO | §15 |
| Environment variables and settings | §16 |
| Deployment, `deploy.sh`, cron, go-live | §17 — and [`DEPLOY.md`](DEPLOY.md) for the alwaysdata specifics |
| Operational runbook and withdrawal workflow | §18 |
| Testing strategy | §19 |
| Roadmap — 37 days, staged | §20 |
| Risks | §21 |
| Open questions | §22 |

---

<sub>`plan.md` is the single source of truth for what the site should be. Where this
repository has gone beyond it — the React front end, portraits with their own consent,
the deployment target — the amendment is dated in the plan itself and recorded in
[`EXECUTION-PLAN.md`](EXECUTION-PLAN.md).</sub>
