"""The React frontend mount at the domain root. docs/FRONTEND.md.

WHAT IS SERVED FROM HERE
    `frontend/` is a React + Vite project. `npm run build` inside it writes a
    self-contained bundle into `app/static/spa/`, and this blueprint serves it:

        /                            -> app/static/spa/index.html  (front page)
        /spa-assets/index-<hash>.js  -> the bundle, immutable
        /spa-assets/index-<hash>.css -> the stylesheet, immutable

    TWO URL SHAPES, AND NOTHING ELSE. The frontend is mounted at the root but does
    not own every path beneath it: three separate regressions live in that difference.

      - The Bangla 404 (§9.2). A catch-all answers 200 with the shell for every
        mistyped URL; `test_routes.py` and `test_public.py` assert it does not.
      - Method-not-allowed. A catch-all matches `GET /logout` before the POST-only
        route does, so the site's 405 becomes this blueprint's 404.
      - The Jinja pages. `/course`, `/batch-1`, `/about`, `/privacy` and every
        participant profile are still rendered from the `pages` table. The paths the
        React router owns are withdrawn from that table rather than shadowed by a
        fallback — see SPA_ROUTES in app/config.py.

WHICH PATHS THE FRONTEND OWNS
    A LIST, IN CONFIG: `SPA_ROUTES`. One rule per entry and nothing else. The router
    gives `/`, `/gallery` and `/contact` real URLs, so each needs the server to answer
    a direct request with the shell — a bookmark, a reload, a link opened in a new
    tab. Each entry is withdrawn from the Jinja page table at the same time, so a path
    still has exactly one owner.

    A CATCH-ALL WOULD HAVE BEEN THREE LINES AND IS WRONG. It answers every path with
    the shell, which is what the three regressions above are. The list is maintained
    by hand, and that is the point: adding a page to the router means adding a line to
    config, and forgetting to leaves a 404 on a linked page — loud, instead of a
    wrong 200 on every mistyped URL.

    IF THE MOUNT IS EVER GIVEN A PREFIX (`SPA_URL_PREFIX=/preview`), the rules move
    with it and nothing is withheld from the Jinja side. The router then needs its
    `basename`, which `main.tsx` reads from Vite's `BASE_URL` — build with
    `VITE_BASE=/preview/`.

WHY THE ASSETS ARE NOT AT `/assets/`
    That is where Vite puts them by default, and it is the one location this site
    cannot use. `public/.htaccess` — the document root itself, not the fail-safe at
    the project root — ends with:

        RedirectMatch 404 ^/(app|migrations|tools|tests|assets|design-src|instance|var)(/|$)

    which is Apache refusing the Tailwind SOURCE directory before a request ever
    reaches Flask. `/assets/*` would therefore be served perfectly in development and
    404 on the deployed site. `frontend/vite.config.ts` sets `assetsDir: 'spa-assets'`
    and this blueprint serves that name; the two must be changed together.

WHY A MISSING FILE 404s RATHER THAN FALLING BACK
    A typo'd asset URL must not return HTML with a 200: the browser reports a syntax
    error inside a file that is not JavaScript, and the cause then reads as a
    bundler problem rather than as a typo.

WHY THE SHELL CARRIES ITS OWN CONTENT-SECURITY-POLICY
    `_after_request` sets the site policy with `setdefault`, so a header set here
    wins for this response only. The React app loads Google Fonts and Unsplash
    images, both of which `default-src 'self'` blocks; without the override the
    front page renders unstyled and imageless. It is an allowance for two routes,
    it is visible in config, and it deletes itself the day those fonts and images
    are self-hosted — which §15.1 requires anyway.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from flask import Blueprint, Response, abort, current_app, send_from_directory

#: `_register_blueprints` in app/__init__.py supplies the real prefix from
#: `SPA_URL_PREFIX`, the same way it does for the admin. Kept as None here so the
#: default lives in one place — config.py. An empty prefix means the domain root.
URL_PREFIX = None

#: Hashed filenames are content-addressed: `index-DuViRRQJ.css` changes name when
#: its content changes, so it can be cached for as long as a cache is willing.
IMMUTABLE_SECONDS = 60 * 60 * 24 * 365

#: Where Vite puts the bundle. Must match `build.assetsDir` in frontend/vite.config.ts,
#: and must NOT be `assets` — public/.htaccess refuses that path at the Apache layer.
#: See the module docstring.
ASSET_URL_PREFIX = "spa-assets"


def _dist_dir() -> Path:
    """Where `npm run build` writes. A Path from config, not a string built here."""
    return Path(current_app.config["SPA_DIST_DIR"])


def _endpoint_name(route: str) -> str:
    """`/gallery` -> `route_gallery`; `/batch-1/report` -> `route_batch_1_report`.

    An endpoint name has to be unique and identifier-safe, and a path is neither. The
    prefix also keeps a page from ever colliding with `index` or `asset`.
    """
    return "route_" + route.strip("/").replace("/", "_").replace("-", "_")


def create_blueprint(*, routes: Iterable[str] = ("/",)) -> Blueprint:
    """Build the mount with one rule per path the frontend router owns.

    A FACTORY RATHER THAN A MODULE-LEVEL `spa_bp`, for the same reason `public` is
    one: which paths exist is a configuration decision (`SPA_ROUTES`), and a rule
    cannot be added once a blueprint has been registered. A module-level blueprint
    would answer for the first application built in a process and raise
    AssertionError for the second — which is exactly what the test suite does.

    `routes` is the allow-list and this loop is the only place it becomes rules.
    There is no catch-all here, and the module docstring says why.
    """
    bp = Blueprint("spa", __name__, static_folder=None)

    for route in routes:
        bp.add_url_rule(
            route,
            endpoint="index" if route == "/" else _endpoint_name(route),
            view_func=_index_response,
        )

    bp.add_url_rule(
        f"/{ASSET_URL_PREFIX}/<path:filename>",
        endpoint="asset",
        view_func=asset,
    )
    return bp


def _index_response() -> Response:
    """The React shell.

    `no-cache` rather than `no-store`: the file is small, and a revalidation that
    gets a 304 is cheaper than a document that cannot be revalidated at all. What
    matters is that it is never reused without asking — its whole job is to name
    the current hashed bundle, so a stale copy pins a stale build forever.
    """
    response = send_from_directory(_dist_dir(), "index.html")
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    response.headers["Content-Security-Policy"] = current_app.config[
        "SPA_CONTENT_SECURITY_POLICY"
    ]
    return response


def asset(filename: str) -> Response:
    """One file from the build, or a 404 if there is none.

    Deliberately NOT a fallback to the shell, and deliberately confined to one URL
    prefix. See the module docstring for what both of those protect.

    `send_from_directory` resolves the path and refuses to leave its directory, so
    `/spa-assets/%2e%2e/run.py` is a 404 rather than a source file.
    """
    dist = _dist_dir()
    if not (dist / ASSET_URL_PREFIX / filename).is_file():
        abort(404)

    response = send_from_directory(
        dist / ASSET_URL_PREFIX, filename, max_age=IMMUTABLE_SECONDS
    )
    response.headers["Cache-Control"] = (
        f"public, max-age={IMMUTABLE_SECONDS}, immutable"
    )
    return response
