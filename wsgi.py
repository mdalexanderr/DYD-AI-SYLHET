"""WSGI entry point for alwaysdata. plan.md §17.2; DEPLOY.md.

WHAT ALWAYSDATA DOES
    Web > Sites > Add a site → type **Python WSGI**. The panel asks for
    three things that matter here:

        Application path    /home/<account>/sylhet/wsgi.py   ← this file
        Working directory   /home/<account>/sylhet
        Virtualenv          /home/<account>/venv

    The site then runs under **uWSGI** behind Apache. uWSGI imports the file given
    as the application path and looks for a WSGI callable named ``application``.
    That name is fixed: anything else is "the application could not be started",
    with nothing further in the browser.

WHY THERE IS A sys.path LINE AT ALL
    uWSGI does not guarantee that the directory containing this file is importable,
    and the "Working directory" field only changes the process's cwd — which is not
    the same thing. Without the insert below, ``from app import create_app`` raises
    ModuleNotFoundError and every request answers 500 while the log says only
    "could not import".

    This is the same class of assumption that once made ``.env`` silently ignored and
    made a relative SQLite path resolve against the wrong directory. Nothing about
    this runtime is inherited, so nothing about it is assumed.

WHY APP_ENV IS SET BEFORE THE IMPORT
    ``app/config.py`` reads the environment *while its class attributes are
    evaluated at import time*, and it skips ``.env`` entirely when ``APP_ENV`` is
    already ``production``. So the order below is load-bearing:

        set APP_ENV  →  import app.config  →  the production class is chosen

    Reverse the two and a missing APP_ENV in the panel turns this into a
    DEVELOPMENT instance on a public host: debug mode, no secure cookies, and an
    interactive debugger one request away. The ``setdefault`` means the panel's own
    environment variables still win — this only supplies the safe default for a
    misconfigured site.

WHY THE ERROR HANDLER IS SO BLUNT
    If this file raises, there is no Flask app to render an error page: the visitor
    gets uWSGI's generic 500 and the real reason exists only on stderr. On
    alwaysdata that is ``/home/<account>/admin/logs/uwsgi/<site-id>.log``, also
    readable in the panel under Logs. So the traceback is written plainly and the
    exception is re-raised — swallowing it would turn a diagnosable failure into a
    blank page.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# The directory containing app/, migrations/ and .env.
#
# `resolve()` follows symlinks deliberately: a deploy that swaps a release directory
# behind a symlink must end up with the real directory, not with the link.
PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Before the import — see "WHY APP_ENV IS SET BEFORE THE IMPORT" above.
os.environ.setdefault("APP_ENV", "production")


def _build_application():
    from app import create_app

    return create_app()


try:
    application = _build_application()
    #: uWSGI and most monitoring probes look for `application`; some look for `app`.
    #: Both names point at the same object.
    app = application
except Exception:
    sys.stderr.write(
        "\n"
        "==========================================================\n"
        " wsgi.py could not build the application.\n"
        " The real reason is below. On alwaysdata, check:\n"
        "   1. the virtualenv field on the site points at the venv\n"
        "      that has `pip install -r requirements.txt` in it\n"
        "   2. the site's environment variables are filled in —\n"
        "      `SECRET_KEY`, `DATABASE_URL` (charset=utf8mb4),\n"
        "      `ALLOWED_HOSTS`, `APP_URL`\n"
        "   3. over SSH:  python -m flask check-config\n"
        " Logs: /home/<account>/admin/logs/uwsgi/<site-id>.log\n"
        "==========================================================\n"
    )
    traceback.print_exc(file=sys.stderr)
    sys.stderr.flush()
    raise
