#!/usr/bin/env python3
"""Kitchen sink at 360 / 768 / 1440, plus the accessibility baseline.
execution-plan steps 1.7 and 1.10; plan.md §19.4, §7.8.

WHY THIS IS A SCRIPT AND NOT A ONE-OFF LOOK
    Step 1.7 says the harness must be "reviewed at 360 / 768 / 1440", and step 1.10
    says it must be "fully keyboard-navigable with a visible focus indicator at every
    stop". Both were checked by hand once. A design system whose layout guarantees
    are only ever verified by a human looking at a screenshot regresses the first
    time somebody adds a table, and the regression is invisible — a page that scrolls
    sideways at 360px still looks fine on the 1440px monitor the developer is using.

    §19.4 makes 360 / 768 / 1440 a requirement, so it is checked here.

WHAT IT CHECKS
    1. Horizontal overflow at each width. §19.4's failure mode: ONE wide table
       scrolls the WHOLE page, because `white-space: nowrap` on a table header
       propagates out. That bug was real in this project.
    2. All 29 §7.7 components are present, via their `id="kb-<name>"` markers — a
       harness that silently drops a component is worse than no harness.
    3. The focus ring is actually painted. Programmatic `.focus()` does NOT trigger
       `:focus-visible`, so this presses Tab — the only honest way to test it.
    4. No console errors, and no horizontal scrollbar on the document element.

Requires:  playwright + chromium  →  python -m playwright install chromium
"""

from __future__ import annotations

import sys

from serve_design import ROOT, serve_in_background

SERVE_DIR = ROOT
HARNESS = "design-src/kitchen-sink.html"

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

#: §19.4's three required widths, plus phone and tablet-landscape as extras.
WIDTHS = (360, 390, 768, 1024, 1440)

#: The 29 §7.7 components, spelled EXACTLY as tools/render-design.py spells them.
#: The markers are underscores (`kb-site_header`), not hyphens, and they are matched
#: as a plain substring because most appear as HTML comments rather than as element
#: ids. Getting this wrong the first time made the check report 23 absent components
#: on a harness that was rendering all 29.
COMPONENTS = [
    "site_header", "site_footer", "breadcrumb", "hero", "section_heading",
    "document_rule", "stat_strip", "stat_table", "fact_list", "module_grid",
    "participant_card", "participant_grid", "filter_bar", "pagination",
    "gallery_strip", "media_feature", "quote_block", "timeline",
    "institution_card", "faq_accordion", "cta_band", "rich_text",
    "empty_state", "contact_form", "consent_badge", "toast", "modal",
    "data_table", "kpi_card",
]

PASSED: list[str] = []
FAILED: list[str] = []


def ok(message: str) -> None:
    PASSED.append(message)
    print(f"  OK      {message}")


def bad(message: str) -> None:
    FAILED.append(message)
    print(f"  FAIL    {message}")


def note(message: str) -> None:
    print(f"  note    {message}")


def start_server() -> tuple[object, int]:
    """Start the shared harness server.

    The real server lives in tools/serve-design.py because it needs the /fonts/ alias
    and must be rooted at the project — both of which `npm run design:serve` needs as
    well. Serving from anywhere else means the harness renders in fallback fonts and a
    design review here reviews the wrong typeface.
    """
    return serve_in_background()


def chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            browser.close()
        return True
    except Exception:  # noqa: BLE001 — "not installed" is the expected failure
        return False


# ─────────────────────────────────────────────────────────────────────────────
def check_harness_exists() -> bool:
    path = SERVE_DIR / HARNESS
    if not path.is_file():
        bad(f"{path} is missing — run `npm run design:render` first")
        return False
    return True


def check_components_in_source() -> None:
    """An independent second assertion that all 29 components are in the harness.

    `tools/render-design.py` already asserts this as part of `npm run design:render`,
    and this repeats it on the RENDERED output rather than the source. Duplication is
    deliberate here: step 1.8's "each is on the kitchen-sink page in its real states"
    is a Phase 1 exit-gate item, and a component that is silently absent renders as a
    blank gap that nobody notices — so it is worth two independent checks rather than
    one that could be weakened by an unrelated edit.
    """
    source = SERVE_DIR / HARNESS
    if not source.is_file():
        bad("the rendered harness is missing — run `npm run design:render` first")
        return
    html = source.read_text(encoding="utf-8")
    missing = [name for name in COMPONENTS if f"kb-{name}" not in html]
    if missing:
        bad(f"{len(missing)} component(s) absent from the rendered harness: "
            f"{', '.join(missing)}")
    else:
        ok(f"all {len(COMPONENTS)} §7.7 components present in the rendered harness")


def _collect_problems(page) -> dict[str, list[str]]:
    """Console errors and failing HTTP responses for ONE page.

    A function rather than inline lambdas because of closure capture: lambdas defined
    inside the width loop all share one closure cell for the lists, so a callback that
    fires late (a font load failure, say) would append to a LATER width's list and be
    reported against the wrong viewport. A call frame per page gives each its own.

    The HTTP list exists because a browser reports a failed subresource only as
    "Failed to load resource: 404", which names nothing and cannot be acted on. The
    response hook records the URL.
    """
    problems: dict[str, list[str]] = {"console": [], "http": []}

    def _on_console(message) -> None:
        if message.type == "error":
            problems["console"].append(message.text)

    def _on_pageerror(error) -> None:
        problems["console"].append(str(error))

    def _on_response(response) -> None:
        if response.status >= 400:
            problems["http"].append(f"HTTP {response.status} {response.url}")

    page.on("console", _on_console)
    page.on("pageerror", _on_pageerror)
    page.on("response", _on_response)
    return problems


def check_with_browser(port: int) -> None:
    from playwright.sync_api import sync_playwright

    url = f"http://127.0.0.1:{port}/{HARNESS}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for width in WIDTHS:
                page = browser.new_page(viewport={"width": width, "height": 900})

                problems = _collect_problems(page)

                page.goto(url, wait_until="load")
                page.wait_for_timeout(250)

                # (1) Horizontal overflow — §19.4's actual failure mode.
                metrics = page.evaluate(
                    """() => ({
                        scrollWidth: document.documentElement.scrollWidth,
                        clientWidth: document.documentElement.clientWidth,
                        bodyScrollWidth: document.body.scrollWidth,
                    })"""
                )
                over = max(metrics["scrollWidth"], metrics["bodyScrollWidth"]) - metrics["clientWidth"]
                if over > 1:
                    offenders = page.evaluate(
                        """() => {
                            const limit = document.documentElement.clientWidth;
                            const out = [];
                            for (const el of document.querySelectorAll('*')) {
                                const r = el.getBoundingClientRect();
                                if (r.width > 0 && (r.right > limit + 1 || r.left < -1)) {
                                    out.push(el.tagName.toLowerCase()
                                        + (el.className && typeof el.className === 'string'
                                            ? '.' + el.className.trim().split(/\\s+/).slice(0, 3).join('.')
                                            : '')
                                        + ' -> ' + Math.round(r.left) + '..' + Math.round(r.right));
                                }
                                if (out.length >= 5) break;
                            }
                            return out;
                        }"""
                    )
                    bad(f"{width}px: horizontal overflow of {over}px — {offenders}")
                else:
                    ok(f"{width}px: no horizontal overflow ({metrics['scrollWidth']}px wide)")

                # (2) The page's structural landmarks. Component COVERAGE is asserted
                #     by render-design.py above and by CI; what matters here is that
                #     the chrome wrapping the components actually rendered, because a
                #     header that collapses to nothing at 360px is a layout bug that no
                #     marker check would notice.
                if width == WIDTHS[0]:
                    structure = page.evaluate(
                        """() => ({
                            header: document.querySelectorAll('header').length,
                            footer: document.querySelectorAll('footer').length,
                            main: document.getElementById('main') !== null,
                            skip: document.querySelector('a[href="#main"]') !== null,
                        })"""
                    )
                    for label, present in (
                        ("<header>", structure["header"]),
                        ("<footer>", structure["footer"]),
                        ('<main id="main">', structure["main"]),
                    ):
                        if present:
                            ok(f"360px: {label} present")
                        else:
                            bad(f"360px: {label} MISSING from the harness")
                    # The skip link is NOT asserted here. It belongs to the real page
                    # layout (`layouts/base.html`), not to this component gallery, and
                    # tests/test_routes.py asserts it on a real rendered page.

                # (3) The focus ring, tested with a real Tab press. `.focus()` does
                #     NOT activate :focus-visible, so a programmatic focus would pass
                #     even with the ring deleted.
                if width == 768:
                    page.keyboard.press("Tab")
                    focused = page.evaluate(
                        """() => {
                            const el = document.activeElement;
                            if (!el || el === document.body) return null;
                            const s = getComputedStyle(el);
                            return {
                                tag: el.tagName.toLowerCase(),
                                outlineWidth: s.outlineWidth,
                                outlineStyle: s.outlineStyle,
                                outlineColor: s.outlineColor,
                                outlineOffset: s.outlineOffset,
                            };
                        }"""
                    )
                    if not focused:
                        bad("Tab did not move focus to anything (§7.8: every stop needs "
                            "a visible indicator)")
                    elif focused["outlineStyle"] in ("none", "") or float(
                        focused["outlineWidth"].replace("px", "") or 0
                    ) < 2:
                        bad(f"the first Tab stop has no 2px ring: {focused}")
                    else:
                        ok(
                            f"first Tab stop ({focused['tag']}) has a "
                            f"{focused['outlineWidth']} {focused['outlineStyle']} ring, "
                            f"offset {focused['outlineOffset']}"
                        )

                    # The skip link must be reachable on the FIRST Tab, before any
                    # navigation — that is the entire point of it (§7.8).
                    page.goto(url, wait_until="load")
                    page.keyboard.press("Tab")
                    first = page.evaluate("() => document.activeElement?.textContent?.trim()")
                    is_skip = bool(first) and ("যান" in first or "skip" in first.lower())
                    if is_skip:
                        ok(f"the first Tab stop is the skip link ({first!r})")
                    else:
                        note(f"the first Tab stop is {first!r}; check it is the skip link")

                # (4) Console errors and failed subresources.
                if problems["console"]:
                    bad(f"{width}px: {len(problems['console'])} console error(s): "
                        f"{problems['console'][:3]}")
                else:
                    ok(f"{width}px: no console errors")

                if problems["http"]:
                    unique = sorted(set(problems["http"]))
                    bad(f"{width}px: {len(problems['http'])} failed request(s): "
                        + "; ".join(unique[:4]))
                else:
                    ok(f"{width}px: every subresource loaded")

                page.close()
        finally:
            browser.close()


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print()
    print("  Kitchen sink — steps 1.7 (360/768/1440) and 1.10 (a11y baseline)")
    print("  " + "=" * 66)

    if not check_harness_exists():
        return 1

    check_components_in_source()

    if not chromium_available():
        print()
        print("  SKIP — Chromium is not installed for Playwright.")
        print("         python -m playwright install chromium")
        print("         The markup check above still ran; layout and focus were not.")
        print()
        return 0

    server, port = start_server()
    try:
        check_with_browser(port)
    finally:
        server.shutdown()
        server.server_close()

    print()
    print("  " + "=" * 66)
    print(f"  {len(PASSED)} ok, {len(FAILED)} failed")
    if FAILED:
        for item in FAILED:
            print(f"    FAIL  {item}")
        print()
        return 1
    print("  Layout and accessibility baseline hold at every required width.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
