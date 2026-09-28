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
| `/gallery`, `/contact` | `spa_bp` | the shell, deep-linked — the frontend's own pages |
| `/spa-assets/index-<hash>.js` | `spa_bp` | `immutable`, one year |
| `/course`, `/batch-1`, `/about`, `/privacy` | `public_bp` | still rendered from the `pages` table |
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
- **Method-not-allowed.** A `GET` catch-all matches `GET /logout` before Werkzeug
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

1. `frontend/src/App.tsx` — render it on the path (`location.pathname === '/x'`).
2. `app/config.py` — add `"/x"` to `SPA_ROUTES`, or a hard-loaded `/x` gets the Jinja
   404 page.
3. `npm run build` — the built shell is what the server hands over.

The page itself is a component under `frontend/src/components/`, and the header and
footer link to it with `<Link to="/x">` so the router handles the click without a
reload.

### The two routed pages

| Page | Component | What it is |
|---|---|---|
| `/gallery` | `GalleryPage.tsx` | every Batch 1 work, filterable by type, opening the same `WorkModal` the home page uses |
| `/contact` | `ContactPage.tsx` | the office addresses and the contact channels, as ruled label/value rows |

Neither is a new source of truth. `/gallery` renders the same `mockData.ts` works the
home page's rail does, and `/contact` repeats the details already published in the
footer and the office block — no address, number or claim was invented for it.

**`/contact` has no form**, deliberately. A contact form that posts nowhere, on a
government site, collects a citizen's message and discards it, which is worse than not
offering one. Correspondence goes through the phone numbers and the mailto links until
there is something behind a submit button.

Every other nav item — কোর্স, অংশগ্রহণকারীরা, ট্রেইনারগণ, the batch menu — still
switches a view with `useState` and does not change the URL. They are `#fragment`
links to sections of the home page, and `/course` remains the Jinja CMS page, so
turning those into routes is a separate decision about which half owns the content.

### Settings

| Key | Env | Default | Meaning |
|---|---|---|---|
| `SPA_ENABLED` | `SPA_ENABLED` | `True` | serve the frontend at all |
| `SPA_URL_PREFIX` | `SPA_URL_PREFIX` | `""` | `""` is the domain root |
| `SPA_ROUTES` | `SPA_ROUTES` | `/`, `/gallery`, `/contact` | the paths the frontend owns, comma-separated |
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
nothing, so `/`, `/gallery` and `/contact` go back to the Jinja site.

## What is not wired

- **Content.** The frontend renders `src/data/mockData.ts`. **Readers of the front page
  no longer see anything the CMS contains.** The `pages` table still drives `/course`
  and the other three Jinja pages; it does not drive `/`, `/gallery` or `/contact`. This
  is the largest consequence of the mount and is a content decision, not a technical
  one.
- **The API.** The app has `/api` and the Vite dev server proxies `/api/*` to Flask, so
  the plumbing exists, but the frontend makes no requests yet. Wiring it means
  replacing the `mockData.ts` imports with `fetch('/api/...')`.
- **Participant privacy.** `plan.md` §5 defines what may be published about a person:
  name, education, occupation before, outcome. The front page currently renders
  portraits and other fields for people it invents. If it is ever pointed at real
  participant data, **none of that may come from a request** until §5.3's consent rules
  apply to it — the frontend has no consent filter and the database cannot enforce one
  from the browser side.

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
