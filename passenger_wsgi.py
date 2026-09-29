"""Passenger entry point — cPanel. plan.md §17.2 step 4, §9.1.

    cPanel → Setup Python App → Application root `sylhet.dydaiproject.com`
                              → startup file `passenger_wsgi.py`

Passenger imports this module and looks for a WSGI callable named ``application``.
That name is fixed; anything else is "the application could not be started" with no
further explanation.

ONE IMPLEMENTATION, TWO HOSTS
    The bootstrap — sys.path, APP_ENV before the import, the loud failure banner —
    lives in ``wsgi.py``, because alwaysdata's panel points at a file path while
    cPanel's points at this filename. Two copies of that bootstrap would be two
    places for the APP_ENV ordering to be got wrong, and getting it wrong means a
    DEVELOPMENT instance on a public host.

    So this file does only what Passenger needs and nothing else: make the project
    root importable, then hand over. Anything changed in ``wsgi.py`` changes here.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Passenger does NOT run with the application root as the working directory, and it
# does not guarantee that the application root is importable. Without this line,
# `from wsgi import application` below raises ModuleNotFoundError and the site
# answers 500 on every request while the log says only "could not import".
PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from wsgi import app, application  # noqa: E402,F401 — the path insert must come first

__all__ = ["application", "app"]
