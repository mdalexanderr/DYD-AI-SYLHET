# DYD AI SYLHET

Official website and management system for the **Sylhet Division** roll-out of the
Government of Bangladesh project *"তথ্যপ্রযুক্তি জ্ঞানসম্পন্ন যুবদের কৃত্রিম বুদ্ধিমত্তা (এআই)
প্রযুক্তির মাধ্যমে দক্ষতা উন্নয়ন"* — implemented by **যুব উন্নয়ন অধিদপ্তর (Department of Youth
Development)**, Ministry of Youth & Sports.

Companion to the national site: <https://www.dydaiproject.com> · Scope: **4 districts / 41 upazilas**
· Package-৪ (Chattogram + Sylhet).

---

## Status

> 📋 **Planning stage. No application code yet.**

| Item | State |
|---|---|
| Master plan | ✅ [`plan.md`](plan.md) — ~3,900 lines, 27 sections, 218 indexed headings |
| Design direction | ✅ A + C hybrid (Surma Protocol) |
| CSS approach | ✅ Tailwind CSS v4 (CSS-first `@theme`) |
| Development model | ✅ Solo build + an external design supplier (`plan.md` §10.5) |
| Hosting / domain / dates / brand assets | ⏳ pending, unblocked via provisional defaults (`plan.md` §26.1) |
| **Next step** | **M1 — the supplier handoff kit** (`plan.md` §10.6) |

---

## Team

**One developer on this project**, working with GitHub Copilot. The frontend collaborator is a
**supplier of markup**, not a second engineer on the codebase.

| | Who | Produces |
|---|---|---|
| **Sole developer** | The project owner | Everything — backend, database, auth, admin console, student portal, public-site wiring, documents, notifications, deployment, data, security |
| **Design supplier** | Collaborator | **HTML + CSS for the public pages only.** No Python, no Jinja, no access to `app/` |

**Why it is not a "backend/frontend split".** In a server-rendered Jinja app there is no
horizontal line — a template calls `url_for()`, reads `current_user` and is chosen by a Python
view. With one developer there is nothing to parallelise, only a sequence of work plus one
external input:

```
  Supplier: design-src/public/*.html  ──convert──►  Developer: app/templates/public/*.html
            standalone HTML + Tailwind               Jinja wired to routes and data
            [[TOKEN]] placeholders                   real context variables
            NOT deployed                             owns the entire runtime
```

Because `design-src/` is **excluded from the deploy sync**, the supplier's files are structurally
incapable of affecting production. No `CODEOWNERS`, no branch protection needed.

The four frozen contracts (URL map, design tokens, component inventory, placeholder dictionary)
are in `plan.md` §10.5.3; the file-level breakdown is §10.5.2.

> ⚠️ **Capacity note — read before starting.** 108 developer-days on one person is **~22 weeks
> best case, 24–27 realistic**. The lever is scope, not people. `plan.md` §24.1 quantifies it and
> §24.2 lists the cuts that reach ~17 weeks. Stage 1 (public + apply) still clears the application
> deadline in ~7–8 weeks.

---

## The core business rule

**Nobody registers an account.** The only way in is to *apply*:

```
apply  →  admin screens the application  →  written exam + viva
       →  merit list published  →  ONLY then is an account created
```

Selected candidates sign in with **exam roll + registered mobile number** *or*
**email + password**. There is no `/register` route anywhere in the application, and a test
asserts that. Account creation is possible from exactly one code path, at merit publication.

---

## Planned stack

| Layer | Choice |
|---|---|
| Language / framework | Python 3.12 · Flask 3.1 (blueprints) |
| ORM / DB | Flask-SQLAlchemy · MySQL (`utf8mb4`) in prod, SQLite in dev |
| Auth | Flask-Login + Flask-Bcrypt · Roll+Mobile and Email+Password |
| Forms / CSRF | Flask-WTF / WTForms |
| CSS | **Tailwind CSS v4** — compiled + minified `app/static/css/app.css` **is committed**; the server never needs Node |
| Documents | HTML print views (guaranteed) + WeasyPrint/Playwright when available |
| QR | `segno` (pure Python, zero native deps) |
| Hosting | cPanel + Phusion Passenger (VPS path also supported) |
| CI/CD | GitHub Actions — CI gates every PR; a push to `main` deploys |

The stack deliberately mirrors the owner's already-live Flask/cPanel project so that
deployment, cron and CI patterns are proven rather than invented.

---

## Operating rules for this repo

1. **Never commit** `.env`, keys, citizen PII, uploaded photos/documents, databases or backups.
   `.gitignore` covers these; the deploy script excludes them too. See `plan.md` §14.5.
2. **No secrets in `plan.md`** — host/IP/SSH details are referenced as `<REMOTE_HOST>` etc. and
   supplied to `deploy.sh` via environment variables. This file is public.
3. **Styling:** no hand-written CSS, no `<style>` blocks in Jinja, no `@apply` in templates.
   All styling resolves through Tailwind utilities in `assets/tailwind/source.css`.
   The theme wipes Tailwind's default palette, radius and shadow scales, so generic-looking
   utilities **do not compile** — the anti-slop rules are enforced by the build, not by review.
4. **Rebuild CSS** (`npm run css:build`) whenever a template changes; CI fails the build on drift.
5. **A push to `main` is a production release.** Branch for anything risky, merge when CI is
   green. The deploy workflow is gated on a blocking `flask render-check --all` pre-flight job,
   so a broken template fails the deploy rather than the live site. If the design supplier is
   given repository access, their `design-src/` commits are safe by construction — that folder
   is excluded from the deploy sync.
6. **The supplier stays in `design-src/`.** They never edit `assets/tailwind/source.css`,
   anything under `app/`, or `app/static/css/app.css`. Token and component requests go through
   `DESIGN-NOTES.md` (`plan.md` §10.6.5) so the design system stays coherent.

---

## Where to read more

| Looking for | Section in [`plan.md`](plan.md) |
|---|---|
| How the whole system works | §1 Executive Summary, §5 User Journeys |
| Reference-site analysis (verified live) | §2 |
| Every requirement, numbered | §6 |
| Visual direction and design tokens | §7 |
| All ~93 routes | §8.2 |
| Database schema (~52 tables) | §11 |
| Login / security design | §14 |
| Bangla typography and fonts | §16 |
| Admin operations runbook | §18 |
| Local dev setup | §21 |
| Deployment, `deploy.sh`, cron, CI | §22 |
| Milestones and effort | §24 |
| Risks | §25 |
| Open questions + provisional defaults | §26, §26.1 |

---

<sub>Working documents: `plan.md` is the single source of truth. Nothing is implemented until the
plan is approved.</sub>

