# The React frontend

`frontend/` holds a React + Vite site, and it **is the front page**. Flask serves it
at `/`, and at the two pages that have their own URL — `/gallery` and `/contact`.
Everything else in this application — `/course`, `/batch-1`, `/about`, `/privacy`, the
participant profiles, `/health`, the admin CMS — is unchanged and still rendered the
way it was.

This document records how the two are wired together, and what has not been decided.

---

## The two halves

```
dyd-ai-program-—-sylhet/           <- the project folder you open
├── frontend/                      <- React + Vite source. Edit the site here.
│   ├── src/                       components, data/mockData.ts
│   ├── index.html
│   ├── vite.config.ts             builds into the path below
│   └── package.json
└── DYD-AI-SYLHET/                 <- this Flask app (its own git repository)
    ├── app/
    │   ├── routes/spa.py          serves the built frontend
    │   └── static/spa/            <- the build lands here, and is committed
    └── tests/test_spa.py
```

## The build

One command, run in `frontend/`:

```powershell
cd frontend
npm install      # first time only
npm run build
```

`vite.config.ts` writes the output straight into `DYD-AI-SYLHET/app/static/spa/`, so
there is nothing to copy afterwards.

The output is **committed**, exactly like `app/static/css/app.css`, for the same
reason: the cPanel host has no Node and no build step, so a deploy is a file sync and
the server only serves what is already in the repository. Build before you commit a
frontend change, or production keeps serving the previous bundle.

Three consequences worth knowing:

- **The assets go to `spa-assets/`, not `assets/`.** That is not Vite's default and it
  is not an accident. `public/.htaccess` — the document root — refuses `/assets/` at
  the Apache layer to protect the Tailwind source directory of the same name, *before*
  a request reaches Flask. A default build would work perfectly on a developer's
  machine and 404 on the live site. `vite.config.ts` (`build.assetsDir`) and
  `app/routes/spa.py` (`ASSET_URL_PREFIX`) must be changed together.
- **Do not rename the output directory to `dist`.** `.gitignore` ignores `dist/`
  repository-wide (it is a Python build directory), so the bundle would silently never
  be committed and the deploy would ship an empty front page.
- `app/static/spa/` is excluded from `check-bans.py` through `GENERATED_PATH_PARTS`. A
  minified bundle contains its dependencies' code and every Tailwind class the frontend
  uses as a string literal, so scanning it produces permanent false positives.

## The brand logo and the icon set

One master file feeds both halves. Regenerate everything with:

```powershell
cd DYD-AI-SYLHET
.\.venv\Scripts\python.exe tools\build-brand-icons.py
```

It reads `assets/brand/logo-master.png` — a source asset, never deployed, because
`assets/` is excluded from the deploy sync — and writes:

| Output | Used by |
|---|---|
| `app/static/img/dyd-logo.png` | the Jinja header, footer and admin header |
| `app/static/img/favicon.ico` + `favicon-16/32/48.png` | every page, via `layouts/base.html` |
| `app/static/img/apple-touch-icon.png` | iOS — flattened onto paper, because iOS draws transparency as black |
| `app/static/img/icon-192.png`, `icon-512.png`, `icon-maskable-512.png` | `site.webmanifest` |
| `frontend/src/assets/brand-logo.png` | the React header and footer |
| `frontend/src/assets/favicon.png` | the React shell, hashed into `/spa-assets/` |

The artwork is trimmed to its real pixels and re-padded per output, because the master
carries a wide transparent margin — scaled straight down, it produces a favicon that is
mostly empty space. The header logo is 256px and 69 KB: it is displayed at 36–56px, so
that already covers 4× DPR, and the 512px version was 208 KB on every page load.

**On a dark ground the mark needs a plate.** It is dark-green artwork, and both footers
(`bg-green-900` in Jinja, `#06301F` in React) would swallow it, so each wraps it in a
paper-coloured plate. If the logo is ever re-drawn with a light or knockout variant,
those two plates should go.

`roundel.svg` stays on disk and stays in the tree gate: it is the drawn placeholder
that `plan.md` Q4 calls the fallback "until supplied", and `design-src/` still draws it.

**A rule this breaks.** §7.4 says "no raster logo in the header". A supplied logo is what
Q4 asks for and supersedes the placeholder, but §7.4 itself has not been amended — the
same situation as §15.1 below, and the same one-line fix in `plan.md`.

### The CTA band and the footer

Both were rebuilt to one direction — the page ends as a document, on paper — and both
halves match: the marginal rule beside the closing note, a ruled register of batches, the
contact block as labelled rows instead of an icon per line, and one wrapped navigation
line. Measured on a 1440px viewport, the React end matter went from 784px of dark green
(CTA 329 + footer 455) to 582px of paper (CTA 175 + footer 407), and it says more: the
batch sequence with a status per entry replaces a link list that duplicated the sticky
header.

**This contradicts §7.5**, which lists "green institutional ground" and puts the footer on
green-900. The footer is now `#F1EFE6` with a 2px green rule, in both halves, because two
adjacent dark slabs — the CTA and the footer, both saying "batches" — was the problem the
redesign set out to solve. §7.5 needs the amendment, or the footer needs to go back.

### The hero artwork

`frontend/src/assets/hero-landscape.jpg` is the front-page hero. It is **bundled, not
fetched**: it used to be a third-party `i.ibb.co` URL with a retry against a second
hostname, which was both a privacy leak (§7.4 and §15.1 forbid third-party images) and
a dependency on someone else's uptime for the first thing a visitor sees.

Regenerate it with:

```powershell
cd DYD-AI-SYLHET
.\.venv\Scripts\python.exe tools\build-hero-image.py
```

from `assets/media/hero-master.png` — the source, kept in the repository and never
deployed, because `assets/` is excluded from the deploy sync. The master is a 1.6 MB
PNG; the bundled JPEG is 162 KB, which is what makes it usable above the fold.

**What it is, and what the words now say.** The artwork is **AI-generated**, and
`plan.md` §7.6 lists, among its *Required* rules: "real content … mobile-first at 360px ·
**no AI-generated imagery anywhere**". It is on the front page, so the site contradicts
that rule — the third of this kind, alongside §15.1 and §7.4.

Because of that, the text around the image was changed to describe what the picture
actually is, instead of inheriting the documentary framing of the photograph it
replaced:

| Where | Was | Now |
|---|---|---|
| `alt` | `সিলেটের চা বাগান ও নারী চা শ্রমিক — প্রামাণ্য আলোকচিত্র` | `কৃত্রিম বুদ্ধিমত্তার প্রতীকসহ সিলেটের চা বাগান, শহর ও সুরমা নদীর ভোরের দৃশ্য, সামনে ল্যাপটপ ও বইয়ের ডেস্ক — প্রতীকী চিত্র` |
| corner badge | `সিলেট প্রামাণ্য আর্কাইভ · ২০২৫` | **removed** — every wording that fits a corner label either repeats the caption or makes a claim about the picture |
| caption | `সুরমা অববাহিকা ও চা-বাগান দিগন্ত` | `শেখার টেবিল থেকে সুরমা অববাহিকার দিগন্ত` |

The alternative the plan prefers is a real photograph of the programme: Q8 asks whether
training-session photographs exist, and §13.3 permits them **in the gallery**, where a
caption cannot be read as a portrait of a named participant. `HeroLandscapeImage.tsx`
also still carries a drawn SVG plate as its fallback — the plan-compliant option if that
is the direction taken.

## Where it is served

| URL | Served by | Notes |
|---|---|---|
| `/` | `spa_bp` | the React shell; `no-cache` |
| `/batches`, `/gallery`, `/participants`, `/trainers`, `/contact`, `/course-modules` | `spa_bp` | the shell, deep-linked — the frontend's own pages |
| `/spa-assets/index-<hash>.js` | `spa_bp` | `immutable`, one year |
| `/course`, `/batch-1`, `/about`, `/privacy` | `public_bp` | still rendered from the `pages` table; **the CMS owns these** |
| `/batch-1/<slug>` | `public_bp` | participant profiles, consent-filtered |
| `/<ADMIN_URL_PREFIX>/` | `admin_bp` | the CMS |
| `/health`, `/sitemap.xml`, `/robots.txt` | `api_bp`, `seo_bp` | |
| anything else | the site | the Bangla 404 |
| `GET /logout` | `auth_bp` | 405 — the route is POST-only |

**An allow-list, not a catch-all.** `SPA_ROUTES` names the exact paths the frontend
router owns, and Flask registers one rule per entry. A catch-all would have been three
lines and would have broken three things at once:

- **The 404 page.** It would answer 200 with the shell for every mistyped URL, so the
  Bangla 404 (`plan.md` §9.2, "the most-seen page after the homepage") would never
  fire. `tests/test_routes.py` and `tests/test_public.py` assert it does.
- **Method-not-allowed.** A `GET` catch-all matches `GET /admin/logout` before Werkzeug
  notices the POST-only rule, so the site's 405 turns into a 404. `tests/test_spa.py`
  asserts the 405, because `test_auth.py` relies on it to prove logout cannot be
  triggered by an `<img>` tag.
- **The Jinja pages.** Two rules for one path are resolved by registration order,
  without a warning, and the loser simply stops existing.

So a path on the list is **withdrawn** from `public.PAGE_ROUTES` rather than shadowed:
one owner per path, decided at boot. Adding a page to the router means adding a line to
`SPA_ROUTES`; forgetting to leaves a 404 on a page the nav links to — loud, instead of
a wrong 200 on every mistyped URL.

**Adding a page.** Three places, in this order:

1. `frontend/src/App.tsx` — render it on the path, in the branch chain below the Header.
2. `app/config.py` — add `"/x"` to `SPA_ROUTES`, or a hard-loaded `/x` gets the Jinja
   404 page.
3. `npm run build` — the built shell is what the server hands over.

The page itself is a component under `frontend/src/components/`, and the header and
footer link to it with `<Link to="/x">` so the router handles the click without a
reload. **One exception, for whenever it is needed again:** a page the *other* half
serves takes a plain `<a href>`, not `<Link>`, because the router has no route for it and
would fall through to the home page. No React link does this today — `/course`, `/about`
and `/privacy` are reachable by URL and from the Jinja half's own nav.

## The pages, and who owns each

| Page | Component | What it is | Owner |
|---|---|---|---|
| `/` | `App.tsx` | the home page: hero, stats, works rail, participants, modules, trainers, CTA | React |
| `/batches` | `BatchesPage.tsx` | all three batches, their status and facts, each opening `BatchViewModal` | React |
| `/gallery` | `GalleryPage.tsx` | every Batch 1 work, filterable by type, opening the same `WorkModal` the home rail uses | React |
| `/participants` | `AllParticipantsPage.tsx` | the full participant register | React |
| `/trainers` | `TrainersPage.tsx` | the faculty, reusing `TrainersSection` in its `standalone` mode | React |
| `/contact` | `ContactPage.tsx` | the office addresses and contact channels, as ruled rows | React |
| `/course-modules` | `CourseModulePage.tsx` | **the course page in the nav** — 13 modules, phases, tool filter, search, module modal | React |
| `/course` | `public/page.html` | the CMS course page — 7 sections from the `pages` table | **the CMS** |
| `/about`, `/privacy` | `public/page.html` | as `plan.md` §6.2 defines them | **the CMS** |
| `/batch-1/<slug>` | `public/profile.html` | one participant's profile, consent-filtered | **the CMS** |

**There are two course pages and that is deliberate.** The nav's **কোর্স** (and the
footer's কোর্স কারিকুলাম) opens `/course-modules`: React's course page, with the 13
modules, the phase filter, the tool filter, the search and the module modal. It renders
`/api/v1/content`, which is the `course_modules` table.

The second is the CMS page at `/course`, which Flask renders from the `pages` table and
which an operator can edit in the admin panel. It is **not linked from the React half** —
one nav item, one destination — but it is live, it is in the sitemap, and the Jinja
half's own header and footer still link to it.

So: if you edit the course text in `/admin`, the change appears at `/course`, not in the
nav. If you want one page instead of two, either point `SPA_ROUTES` at `/course` and drop
the React page, or delete `CourseModulePage.tsx` and link the nav back to `/course` —
say which and it is a small change either way.

Every routed page is a `<Link>` in the header, the mobile menu and the footer, and
every one answers a hard load with the shell (see `SPA_ROUTES`). `BatchesPage` also
exports `PROGRAMME_BATCHES`, which the header's dropdown reads — the nav and the page
cannot drift about what ব্যাচ ২ is called or whether it has started.

**`/contact` has no form**, deliberately. A contact form that posts nowhere, on a
government site, collects a citizen's message and discards it, which is worse than not
offering one. Correspondence goes through the phone numbers and the mailto links until
there is something behind a submit button.

### Settings

| Key | Env | Default | Meaning |
|---|---|---|---|
| `SPA_ENABLED` | `SPA_ENABLED` | `True` | serve the frontend at all |
| `SPA_URL_PREFIX` | `SPA_URL_PREFIX` | `""` | `""` is the domain root |
| `SPA_ROUTES` | `SPA_ROUTES` | `/`, `/batches`, `/gallery`, `/participants`, `/trainers`, `/contact`, `/course-modules` | the paths the frontend owns, comma-separated |
| `SPA_DIST_DIR` | — | `app/static/spa` | where `npm run build` writes |

`VITE_BASE` in `frontend/vite.config.ts` **must** equal `SPA_URL_PREFIX`. Vite bakes it
into every asset URL, so if the two disagree the page loads and then renders nothing.
`main.tsx` passes Vite's `BASE_URL` to `<BrowserRouter basename>`, so a prefixed mount
links within its prefix.

A path is withdrawn from the Jinja page table only when the frontend is mounted **at
the root**. With `SPA_URL_PREFIX=/preview` the whole site keeps its pages and the
frontend's rules move under the prefix:

```powershell
# render the React site beside the live one, and rebuild it for that URL
$env:SPA_URL_PREFIX="/preview"; $env:VITE_BASE="/preview/"; npm run build; python run.py
```

`SPA_ROUTES` is validated at boot: an entry that is not root-relative (`gallery`) is a
`RuntimeError` rather than a rule that can never match. `SPA_ENABLED=false` withdraws
nothing, so `/`, `/batches`, `/gallery` and the rest go back to the Jinja site.

## What the admin panel does and does not control

This is the question to ask of every page: **if I change it in `/admin`, does the page
change?**

| What | Where it is edited | Reaches the page? |
|---|---|---|
| `/course`, `/about`, `/privacy` text and sections | the CMS, on the `pages` table | **yes** — Flask renders them on every request |
| Participant profiles and the register (`/batch-1/<slug>`) | the CMS + consent records | **yes**, after the consent rules in `plan.md` §5.3 |
| Course, modules, institutions, statistics, FAQs, settings | the CMS (`/admin/course`, `/admin/institutions`, `/admin/stats`, `/admin/faqs`, `/admin/settings`) | **yes** — the public templates read the tables |
| Uploaded images | the CMS media library (`/admin/media`) | **yes** — an upload stores outside the webroot and is served signed |
| Phases, tools, batch works, statistics | `flask seed-programme`, then the CMS | **yes** — `/api/v1/content` serves them and the React pages fetch that payload |
| Trainers | the CMS (`/admin/instructors`) | **yes** — same payload, and a trainer's list fields are one entry per line |
| The React pages: `/`, `/batches`, `/gallery`, `/participants`, `/trainers`, `/contact`, `/course-modules` | `frontend/src/data/content.ts` (the API) + the tables above | **yes**, on the next page load — the payload is fetched once per session and revalidated with an ETag |
| Nav labels, the batch announcements on `/batches` | `frontend/src/components/*` | a code change and a deploy. The batches are programme announcements, not a table |

### The wire between the CMS and React

The React half does not read the database directly; it fetches `/api/v1/content`
(`app/routes/content.py`), which is built by `app/services/content_service.py`. That
module exists so the projections are decided ONCE, in the same place the Jinja pages
get theirs: a participant card is `participant_service.to_card()` (an allowlist of four
facts, §5.2) and the list is `list_published()` (the consent rule, §5.3), so the browser
is never the last place "may this name be public" is answered.

`frontend/src/data/content.ts` adapts that payload into the shapes the components
already used, which is why moving the site onto the database changed the data source
rather than the design. **`mockData.ts` is no longer imported by the app** — it is kept
as the source the seeder's JSON was compiled from, and `flask seed-programme` reads that
JSON, not the TypeScript.

**Everything has an empty state, and that is not decoration.** The register starts empty
and fills up as consent forms are imported, so `ParticipantsRegister`, `AllParticipantsPage`,
`TrainersSection`, `GalleryPage`, `BatchWorks` and `StatStrip` each render a deliberate
empty band (or, for the stat strip, nothing at all) rather than a heading over a void.
The headline figures that COUNT something — participants, modules — are rendered from the
counts in the payload; the ones that are editorial (৩০০ ঘণ্টা, ১১ টুলস) stay as stored.

### The CMS screens

`/admin/login` is the portal and `/admin` is the dashboard. Sixteen screens hang off
it, in a left rail grouped so that the order means something: **01 Overview**, **02
The site** (what a reader sees), **03 Course**, **04 People** (the register, its
consent records and the trainers), **05 System** (settings, audit, backups).

| Screen | What it edits |
|---|---|
| Dashboard | consent counts, published/draft pages, the last eight audit entries, the message queue, the newest backup |
| Pages | the `pages` table, and each page's ordered sections |
| Media library | images: upload, alt text, usage, delete (refused while in use) |
| Messages | contact-form submissions, with status and internal notes |
| Course · Modules | the course record and its ordered modules. A module needs BOTH a course (a picker) and, to appear on `/course-modules`, a phase |
| Institutions | the training centre and the partners |
| Trainers | the faculty: name, designation, experience, bio, quotation, specialties and contributions (one per line), plus the teaching figures the trainer's card shows. A portrait is uploaded or picked from the library here |
| Statistics | the figures in a stat strip |
| Questions | grouped questions and answers |
| Settings | site copy, hotline, footer, toggles. `is_secret` rows are read-only (§16.2) |
| Participants | the register: create, edit, filter, bulk publish, CSV export. The photograph and its permission are part of the record form |
| Consent | the five consent buckets and the three lists that need attention |
| Import | CSV import, with a dry run that writes nothing. See "What the CSV may contain" below |
| Audit log | every write, with its before/after diff (§12.1) |
| Backups | a read-only report of what the backup job has produced |

### What the CSV may contain

Headers are matched case-insensitively, with spaces and underscores ignored — so
`Name_BN`, `name bn` and `name` are the same column. **Every Bangla spelling the
department uses is accepted as well**; those spellings live in `COLUMN_ALIASES`
(`app/services/import_service.py`), which is the one place to read or extend, and
`tests/test_import.py` proves every entry in it resolves through the normaliser.

| Column | Accepts | Notes |
|---|---|---|
| Name | `name`, `name_bn`, `fullname` | required |
| Name (English) | `name_en` | |
| Education | `education` | required; `HSC`/`SSC`, `Diploma`, `Degree`, `Honours`/`Masters` |
| Occupation before | `occupation_before` | |
| Outcome | `outcome`, `outcome_type` | one of the six outcome values |
| Outcome detail | `outcome_text` | |
| Quotation | `quote`, `quote_bn` | **needs `quote_consent: yes`** (§5.3 rule 5), or the row is rejected rather than stripped of its quote |
| Quotation consent | `quote_consent`, `quote_consented` | `yes`/`no` |
| Batch | `batch` | a number; anything else means batch 1 |
| Consent | `consent`, `consent_publication` | `yes`/`no`. Anything else REJECTS the row rather than becoming "no" |
| Consent date | `consent_date` | `2026-03-01`, `01/03/2026`… Consent without a date is accepted and BLOCKS publication (§5.3 rule 3) |
| Slug | `slug` | left empty, it is derived from the name |

**An import never publishes.** A spreadsheet cannot carry the decision to make a
person's name public; that is made one record at a time on the detail screen, with the
consent panel in front of you. The dry run reports every row's problems and writes
nothing; the commit writes the valid rows and records each failure against its line
number.

### Portraits

An image field appears on the participant and trainer forms: what is there now, a picker of every
image in the library, an upload, and a remove. All three screens share one macro
(`media_field`), so "remove" cannot come to mean something different on one of them.

**A trainer's portrait is a staff photograph; a participant's is personal data.** The trainer form
is one field. The participant form carries `image_consent` inside the same block, because §5.1 was
amended on 2026-09-29 to allow a participant photograph *only* alongside a permission of its own —
permission for a name and an education level is not permission for a face. The database enforces the
pair, so the practical consequences are:

* Uploading a picture without ticking the box **stores the file in the library and leaves the
  record untouched**, and says so. It cannot attach it: the INSERT would be refused.
* The content API sends `photo_url` only when `Participant.photo_is_publishable` is true. Otherwise
  it sends `null` and the components draw the person's initials, which is what every card did before
  this feature existed.
* A portrait is served through the same signed URL as every other upload, and the participant
  profile page at `/batch-1/<slug>` remains typographic by design.

### The panel is English; the site is Bangla

§14.1 makes the public site Bangla-first. §11.1's panel is the operator's tool, and it
is **English**: the rail, the page headings, every button, every validation message and
every flash. Two consequences worth knowing:

* **Content stays Bangla, and says so.** A page title, a person's name, a quotation and
  a stat's display value are Bangla, and every element that renders one carries
  `lang="bn"` — so a screen reader reads the interface in English and the data in
  Bangla, which is the correct behaviour for both.
* **The document declares itself English** (`<html lang="en">`, via the `html_lang`
  block in `layouts/base.html`). The default is `bn` for every public page and for the
  error pages. `tests/test_admin_cms.py::test_the_admin_panel_is_english` walks all
  fifteen screens and fails if Bangla leaks into the chrome.

Labels are **derived, not hand-written**: `app/routes/admin/_labels.py` turns a field's
key into its label, so `title_bn` is "Title (Bangla)" in the record form, in the section
editor, in a table header and in a validation message — one source, so they cannot
disagree. The one hand-written map is the 13 section-type names and hints.

**Why the address is `/admin` and not a secret path.** `plan.md` §12.1 asked for an
`ADMIN_URL_PREFIX` that cannot be guessed, and the first build used one. It was traded
deliberately for the plainer address, for three reasons:

1. **A secret path is not a control.** It is security by obscurity: it does not appear in
   `robots.txt`, it does not survive a shared screenshot, a browser history sync or a
   mis-sent link, and it cannot be rotated without breaking every bookmark. The controls
   that do work are the ones already in place — a signed session, the idle timeout, a
   rate-limited login and the optional `ADMIN_IP_ALLOWLIST`.
2. **The owner has to be able to find it.** One admin, working alone, inheriting this
   site: an address they have to look up is an address they will lose.
3. **`robots.txt` disallows it either way** (`app/routes/seo.py`), and every admin route
   carries `login_required`, asserted over the whole URL map in `tests/test_admin_cms.py`.

**2-step verification (TOTP) is off.** The portal asks for an email address and a
password, and nothing else. `ADMIN_2FA_REQUIRED=false` in `.env` plus an account with no
TOTP enrolled, so the login form does not even draw the code field. The reason on record
is the owner's instruction; the consequence to be aware of is that the password is now the
**only** thing between the internet and participant data, which makes the lockout, the
session timeout and the IP allowlist carry more weight than they did.

Turning it back on does not need a code change:

```powershell
# 1. set ADMIN_2FA_REQUIRED=true in DYD-AI-SYLHET/.env and restart
# 2. enrol the account
.\.venv\Scripts\python.exe -m flask admin-reset-2fa whym85854@gmail.com
```

The field reappears on the login form, and the account is required to present a code.
The tests for both states are in `tests/test_auth.py`.

To reverse the decision, set `ADMIN_URL_PREFIX` in `.env` and restart. Nothing else
changes: the blueprint prefix, the login URL and the IP allowlist all read that one value.

**What it still cannot do:** upload a video (a video is a *link*, `plan.md` §10.5), run a
backup from the browser (a cron job does that, §17.5), or attach a trainer's portrait to
the trainer record — the portrait is uploaded in the media library, and the Trainers
screen has no picker for it yet, so a trainer without one is drawn with their initial.

**What it CAN now do, and did not when this document was first written:** change the
React half. The paragraphs that used to sit here described a content API as a project —
read endpoints, consent filtering on the server, a loading state per page. That work is
done:

1. **The content API exists.** `/api/v1/content` (`app/routes/content.py`) is built by
   `app/services/content_service.py` and serves stats, tools, phases, modules, works,
   trainers, participants, institutions and batches in one payload.
2. **Consent filtering is server-side.** Every participant in that payload came through
   `participant_service.list_published()`, which applies §5.3 inside the query. A
   photograph of a participant is not in the database at all (§5.1), so the API sends
   two initials instead and nothing can leak the rest.
3. **The pages have loading and empty states.** `frontend/src/data/content.ts` fetches
   the payload once per session; each section renders a ruled empty band while the
   register is empty, which is the state the site is in until consent forms are
   imported.

## What is not wired

- **The batch announcements.** `/batches` and the header's dropdown read
  `PROGRAMME_BATCHES` in `frontend/src/components/BatchesPage.tsx` — three announcements
  (delivered, next, planned), not rows in a table. The delivered batch's summary and its
  headcount ARE derived from the register, so the page cannot advertise people who are
  not there; the other two are programme statements with nothing behind them yet. Making
  them table rows means a `programme_batches` model, an admin screen, and a seeder — worth
  doing when the office starts scheduling batch 2 for real.
- **Navigation labels and the hero copy.** `Header.tsx`, `Hero.tsx`, `CtaBand.tsx` and
  `Footer.tsx` still hold their text. The footer's contact details duplicate the
  `settings` table, and a change in one does not reach the other.
- **`mockData.ts` is still in the repository.** Nothing imports it, and it is the source
  the seeder's JSON was compiled from, so deleting it would lose the provenance of 25
  invented people who are still loadable with `flask seed-programme --with-people`. It
  should be deleted once nobody needs a demo database; when it is, delete
  `app/seeds/data/frontend_content.json` and the `--with-people` flag with it.
- **A CSP that permits two third parties.** See "The one allowance it needed" below.

## The unresolved conflict, now live

`plan.md` §15.1 caps first-load JavaScript at **30 KB** and asks for **no framework** in
the critical path, and §7.4 forbids CDN fonts and third-party images. The front page now
ships a **461 KB** React bundle that loads Google Fonts and Unsplash imagery.

While the frontend sat on a `/preview` URL this was a hypothetical. It is now the front
page, so the site contradicts its own plan on every visit, and `plan.md` — the stated
single source of truth — has not been amended. One of these has to happen:

1. **Port the design into the Jinja templates**, which is what the plan assumes. The
   sections the frontend draws already exist as `app/templates/sections/*`, the CMS
   already drives them, and the consent filtering already applies. This keeps §15.1,
   §7.4, the CMS and the no-JavaScript fallback intact.
2. **Amend §15.1** to allow a shipped React bundle, and **self-host the fonts and the
   images** so §7.4 still holds. This is a real option, but it replaces the CMS as the
   source of content and needs §5's consent model rebuilt in the frontend before any
   real participant data reaches it.

### The one allowance it needed

The React shell carries its own `Content-Security-Policy`
(`SPA_CONTENT_SECURITY_POLICY` in `app/config.py`), because the site policy's
`default-src 'self'` blocks both the fonts and the images and the page would render
unstyled. `_after_request` sets the site policy with `setdefault`, so this header wins
for that response only, and `tests/test_spa.py` asserts it does not leak onto any other
route.

It exists solely to permit those two third parties, both of which §15.1 forbids.
Self-host the fonts and images and the policy can be deleted.

## Removing the mount

Set `SPA_ENABLED=false` and `/`, `/gallery` and `/contact` fall back to the Jinja pages,
which are then registered again. To remove it outright:

1. `frontend/` (the front end itself).
2. `app/routes/spa.py`, and its line in `BLUEPRINT_MODULES` (`app/__init__.py`).
3. The `SPA_*` keys in `app/config.py`, `_frontend_routes` and the withheld-path logic
   in `_register_blueprints`, and the `withheld` parameter in `app/routes/public.py`.
4. `app/static/spa/`.
5. `tests/test_spa.py`.
6. Its two lines in `tools/check-tree.py`, and `app/static/spa/` in
   `tools/check-bans.py`'s `GENERATED_PATH_PARTS`.
7. `build.assetsDir` in `frontend/vite.config.ts` if the frontend survives in any form.

## Development

Two servers, so the frontend reloads while the Flask app keeps its session:

```powershell
cd DYD-AI-SYLHET; .\.venv\Scripts\python.exe run.py   # http://127.0.0.1:5000
cd frontend;      npm run dev                        # http://localhost:3000
```

`vite.config.ts` proxies `/api/*` to `http://127.0.0.1:5000`, so a `fetch` written in
the frontend reaches Flask without CORS. Override with `VITE_API_PROXY`.

On port collisions: if `run.py` reports the address in use, another Flask app holds
5000 — `DEV_PORT` changes it, and `VITE_API_PROXY` has to follow.
