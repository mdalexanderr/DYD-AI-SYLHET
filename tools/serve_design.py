#!/usr/bin/env python3
"""Serve the design harness the way it has to be served. plan.md §8.1, step 1.7.

    python tools/serve_design.py --port 8099
    open http://127.0.0.1:8099/design-src/kitchen-sink.html

NOTE THE UNDERSCORE IN THIS FILENAME
    Every other tool here is hyphenated (`check-css.py`, `check-bans.py`), following
    the usual convention for a single-file script. This one cannot be: Python has no
    way to import a module whose name contains a hyphen, and `tools/check-widths.py`
    needs the server below so that both the automated layout check and the human
    `npm run design:serve` workflow serve the harness identically. An underscore is
    the price of sharing one implementation instead of two that drift.

WHY NOT PLAIN `python -m http.server`
    Two failure modes, and BOTH are silent — the page loads, looks plausible, and is
    wrong. Neither produces an error a human would notice.

    1. CROSS-DOCUMENT `<use>` IS BLOCKED ON file:// AND MISROOTED ELSEWHERE.
       The harness draws its icons with `<use href="sprite.svg#name">`. Chrome refuses
       that across documents from a `file:` origin, so every icon renders blank with no
       message anywhere. It must be served over http. And it must be served from the
       PROJECT ROOT, because the harness also references `/app/static/img/...` — which
       404s if the server is rooted at `design-src/`.

    2. THE FONT URLS ARE RELATIVE TO THE COMPILED SHEET.
       `source.css` declares its faces as `url("../fonts/...")`. That is CORRECT in
       production: the sheet is emitted to `app/static/css/app.css`, so `../fonts/`
       is `app/static/fonts/`. The harness's sheet is emitted to
       `design-src/preview.out.css`, where the identical URL resolves to
       `<root>/fonts/` — which does not exist.

       The consequence is the dangerous one: the kitchen sink renders every Bangla
       string in a FALLBACK face, on a page whose entire purpose is judging Bangla
       typography. A design review done there reviews the wrong typeface, and nothing
       on the page says so. Measured before the alias was added: 14 failed requests
       per load, every font and icon.

    The alias below maps /fonts/ onto the real directory, so the harness sees exactly
    what production serves.
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

#: URL prefix -> directory relative to the project root.
#:
#: Both entries exist for ONE reason, and it is worth stating plainly because it looks
#: like a hack: every asset `source.css` references is addressed RELATIVE TO THE
#: COMPILED SHEET. The sheet is authored at `assets/tailwind/` and emitted to
#: `app/static/css/`, so `url("../fonts/...")` and `url("../img/...")` are correct
#: ONLY at the emit location — `app/static/fonts/` and `app/static/img/`.
#:
#: The harness emits the same sheet to `design-src/`, where those identical URLs
#: resolve to `<root>/fonts/` and `<root>/img/`, neither of which exists. Without
#: these aliases the kitchen sink renders in fallback fonts with no contour bands,
#: on a page whose whole purpose is judging Bangla typography and the signature
#: elements — and nothing on the page reports the problem. It was 14 failed requests
#: per load before the aliases were added; a human reviewing it would have seen a
#: slightly-wrong page and moved on.
ALIASES: dict[str, str] = {
    "/fonts/": "app/static/fonts/",
    "/img/": "app/static/img/",
}


class HarnessHandler(SimpleHTTPRequestHandler):
    """Static handler rooted at the project, with the /fonts/ alias applied."""

    def translate_path(self, path: str) -> str:
        for prefix, target in ALIASES.items():
            if path.startswith(prefix):
                path = "/" + target + path[len(prefix):]
                break
        return super().translate_path(path)

    def log_message(self, fmt: str, *args) -> None:
        # Per-request logging drowns the page load (30-odd subresources) and hides the
        # 404s among them, which are the only lines worth reading.
        if args and isinstance(args[1], str) and args[1].startswith(("4", "5")):
            print(f"  {args[1]}  {args[0]}", file=sys.stderr)

    def end_headers(self) -> None:
        # The whole point of the harness is that it shows the CURRENT build. A cached
        # stylesheet makes a design review of yesterday's CSS.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def make_server(directory: Path | None = None) -> ThreadingHTTPServer:
    """Bind a server on a free port, rooted at `directory` (default: project root)."""
    handler = partial(HarnessHandler, directory=str(directory or ROOT))
    return ThreadingHTTPServer(("127.0.0.1", free_port()), handler)


def serve_in_background() -> tuple[ThreadingHTTPServer, int]:
    """Start the server on a daemon thread. Used by tools/check-widths.py."""
    server = make_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, int(server.server_address[1])


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the design harness (§8.1).")
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()

    handler = partial(HarnessHandler, directory=str(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://127.0.0.1:{args.port}/design-src/kitchen-sink.html"

    print()
    print(f"  kitchen sink   {url}")
    print(f"  served from    {ROOT}")
    print(f"  alias          {'  '.join(f'{k} -> {v}' for k, v in ALIASES.items())}")
    print("  (404s and 5xx are printed; a clean load prints nothing)")
    print()
    print("  Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
