"""Local development server. plan.md §9.1.

    python run.py

WHAT THIS IS NOT
    This file is never used in production. Passenger imports `passenger_wsgi.py`
    instead, and the Flask development server is explicitly not for public traffic —
    it is single-threaded, has no request limits, and its debugger allows arbitrary
    code execution to anyone who can reach the page. `--debug` below is therefore
    localhost-only.

WHY IT IS NOT `flask run`
    `flask run` works, and this exists because it has one behaviour we want to be
    explicit about: it calls `create_app()` with no argument, which resolves the
    config from `APP_ENV`, so `python run.py` and Passenger take the SAME path. That
    is the path where an earlier bug lived — `.env` was ignored for programmatic
    callers and honoured only by the Flask CLI, so `flask run` worked and everything
    else silently used defaults.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    from app import create_app

    app = create_app()

    host = os.environ.get("DEV_HOST", "127.0.0.1")
    port = int(os.environ.get("DEV_PORT", "5000"))

    # Refusing to bind debug mode to a non-loopback address is deliberate. The
    # Werkzeug debugger is an interactive Python console served over HTTP; the
    # published CVEs for "Flask debug console exposed" all began with someone
    # setting host="0.0.0.0" to test from their phone.
    debug = app.config.get("APP_ENV") == "development"
    if debug and host not in {"127.0.0.1", "localhost", "::1"}:
        sys.stderr.write(
            f"refusing to start: APP_ENV=development enables the interactive "
            f"debugger, but DEV_HOST is {host!r}.\n"
            "Use DEV_HOST=127.0.0.1, or set APP_ENV=production for a real bind.\n"
        )
        raise SystemExit(2)

    print(f"  {app.config['APP_NAME']} — env={app.config['APP_ENV']} debug={debug}")
    print(f"  http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
