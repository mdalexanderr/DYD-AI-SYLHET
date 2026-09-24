"""Passenger entry point. plan.md §17.2 step 4, §9.1.

WHAT cPANEL CALLS
    Setup Python App → Application root `sylhet.dydaiproject.com`
                       → startup file `passenger_wsgi.py`
    Passenger imports this module and looks for a WSGI callable named
    ``application``. That name is fixed; anything else is "the application could not
    be started" with no further explanation.

WHY THERE IS A sys.path LINE AT ALL
    Passenger does NOT run with the application root as the working directory, and it
    does not guarantee the application root is importable. Without the insert below,
    ``from app import create_app`` raises ModuleNotFoundError and the site returns
    500 on every request while the log says only "could not import".

    This is the same class of assumption that once made ``.env`` silently ignored and
    made a relative SQLite path resolve against the wrong directory. Nothing about
    the runtime is inherited here, so nothing about it is assumed.

WHY THE ERROR HANDLER IS SO BLUNT
    If this file raises, there is no Flask app to render an error page — the response
    the visitor gets is Passenger's generic 500, and the ONLY place the real reason
    can appear is stderr, which on cPanel means the app's `stderr.log` inside the
    Python App's log directory. So the traceback is written plainly to stderr and the
    exception is re-raised: swallowing it would turn a clear failure into a blank
    page.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# The directory containing app/, migrations/ and .env.
#
# `resolve()` follows symlinks, which is deliberate: cPanel sometimes places a
# symlink where the app root is expected, and Passenger must end up with the real
# directory rather than a link that may not be the app root at all.
PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set BEFORE importing the app: config.py reads the environment (and .env) while its
# class attributes are evaluated at import time, so anything set later has no effect.
# On the server APP_ENV comes from the real environment; the default only applies to
# a misconfigured deployment, where it is safer to be explicit than to fall through
# to a development config on a public host.
os.environ.setdefault("APP_ENV", "production")


def _build_application():
    from app import create_app

    return create_app()


try:
    application = _build_application()
    #: Some WSGI servers and monitoring tools look for `app` instead of
    #: `application`. Both names point at the same object, so an uptime probe
    #: written against either one works.
    app = application
except Exception:
    sys.stderr.write(
        "\n"
        "==========================================================\n"
        " passenger_wsgi.py could not build the application.\n"
        " The real reason is below. On cPanel, check:\n"
        "   1. `flask check-config` passes on the server\n"
        "   2. .env exists, is readable, and is not world-readable\n"
        "   3. the virtualenv has requirements.txt installed\n"
        "==========================================================\n"
    )
    traceback.print_exc(file=sys.stderr)
    sys.stderr.flush()
    raise
