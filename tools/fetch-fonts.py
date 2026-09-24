#!/usr/bin/env python3
"""Fetch and self-host the Bengali/Latin faces — plan.md §14.2, §7.4.

    python tools/fetch-fonts.py

Writes woff2 files to app/static/fonts/ and prints the @font-face block that
belongs in assets/tailwind/source.css.

WHY SELF-HOSTED
    §14.2: no CDN, no Google Fonts at runtime. A government site must not depend on
    a third party for the glyphs that render its own language, and the critical-path
    font budget is only measurable if we control the files.

WHY IT PRINTS CSS INSTEAD OF WRITING A FILE
    §8.1 rule 1: all CSS lives in source.css. A generated fonts.css would break that,
    so this tool emits the block and a human pastes it in — which also makes a font
    change a reviewable diff rather than a silent regeneration.

READING THE SUBSET NAME — the obvious approach is wrong
    The Google Fonts CSS v2 API returns each face preceded by a comment naming its
    subset:

        /* cyrillic-ext */
        @font-face { ... }

    Inferring the subset from `unicode-range` instead looks plausible and fails badly:
    every Cyrillic, Greek and Vietnamese range also lacks `U+0980`, so they all get
    classified "latin", collapse onto one filename, and silently overwrite each other.
    Six IBM Plex subsets became one file. The comment IS the subset name — use it.

WEIGHTS
    §14.2 lists five weights; §7.4 — the typography table that actually assigns them —
    uses three. 500 (Noto Sans Bengali) and 600 (Noto Serif Bengali) are referenced
    nowhere, so they are not shipped. They would add ~292 KB to a budget the same plan
    caps at 220 KB. Add them to SPEC if a design change needs them.

STDLIB ONLY — no venv needed, so this can run in CI.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

# A modern Chrome UA is required: the API serves TTF to unknown clients and woff2
# only to browsers it recognises.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Which weights are wanted, and for which subsets. Derived from §7.4:
#   Display XL / L  -> Noto Serif Bengali 700     (hero, section headings)
#   Heading M / S   -> Noto Sans Bengali 600
#   Body / Body S   -> Noto Sans Bengali 400
#   Caption / meta  -> Noto Sans Bengali 400
#   Numerals        -> IBM Plex Sans 400 / 500
SPEC: dict[str, dict] = {
    "Noto Serif Bengali": {"slug": "noto-serif-bengali", "weights": [700], "subsets": ["bengali", "latin"]},
    "Noto Sans Bengali":  {"slug": "noto-sans-bengali",  "weights": [400, 600], "subsets": ["bengali", "latin"]},
    "IBM Plex Sans":      {"slug": "ibm-plex-sans",      "weights": [400, 500], "subsets": ["latin"]},
}

# Above-the-fold faces to preload (§14.2). Chosen against the budget below.
PRELOAD = {("noto-sans-bengali", "bengali", 400), ("ibm-plex-sans", "latin", 400)}

# §14.2: "Critical-path font budget ≤ 220 KB".
CRITICAL_BUDGET_KB = 220

# Not on Google Fonts. Kept in the --font-* stacks as local fallbacks (§14.2).
EXTRA_FALLBACKS = {
    "kalpurush": "Kalpurush — commonly installed on Bangladeshi Windows machines",
    "nikosh": "Nikosh — used by Bangladeshi government documents",
}

FACE_RE = re.compile(r"/\*\s*([a-z0-9-]+)\s*\*/\s*@font-face\s*\{(.*?)\}", re.S)
SUBSET_ORDER = {"bengali": 0, "latin": 1}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 — fixed https URL
        return r.read()


def build_css_url() -> str:
    families = []
    for family, spec in SPEC.items():
        weights = ";".join(str(w) for w in spec["weights"])
        families.append(f"family={family.replace(' ', '+')}:wght@{weights}")
    return "https://fonts.googleapis.com/css2?" + "&".join(families) + "&display=swap"


def parse_faces(css: str) -> list[dict]:
    """Subset comes from the preceding comment; everything else from the block."""
    faces = []
    for m in FACE_RE.finditer(css):
        subset, block = m.group(1), m.group(2)
        family = re.search(r"font-family:\s*'([^']+)'", block)
        weight = re.search(r"font-weight:\s*(\d+)", block)
        url = re.search(r"url\((https://[^)]+\.woff2)\)", block)
        urange = re.search(r"unicode-range:\s*([^;]+)", block)
        if not (family and weight and url and urange):
            continue
        faces.append({
            "family": family.group(1),
            "weight": int(weight.group(1)),
            "url": url.group(1),
            "range": urange.group(1).strip(),
            "subset": subset,
        })
    return faces


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="Self-host the project fonts (§14.2).")
    parser.add_argument("--out", default="app/static/fonts")
    parser.add_argument("--keep-old", action="store_true",
                        help="do not clear the output directory first")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    if out_dir.exists() and not args.keep_old:
        # Stops a renamed or dropped face lingering as an orphan that nothing
        # references and nobody remembers to delete.
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    url = build_css_url()
    print("fetch-fonts:")
    print(f"  manifest  {url.split('?')[1][:96]}…")
    try:
        manifest = fetch(url).decode("utf-8")
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"  FAILED to reach fonts.googleapis.com: {exc}", file=sys.stderr)
        print("\n  Nothing was written. The site still renders — the --font-* stacks fall\n"
              "  back to system-ui — but Bengali text will use whatever the device has.",
              file=sys.stderr)
        return 1

    faces = parse_faces(manifest)
    print(f"  manifest returned {len(faces)} @font-face rule(s)")

    wanted: list[dict] = []
    for face in faces:
        spec = SPEC.get(face["family"])
        if not spec:
            continue
        if face["weight"] not in spec["weights"]:
            continue
        if face["subset"] not in spec["subsets"]:
            continue
        face["slug"] = spec["slug"]
        wanted.append(face)

    wanted.sort(key=lambda f: (f["slug"], SUBSET_ORDER.get(f["subset"], 9), f["weight"]))

    all_subsets = {f["subset"] for f in faces}
    dropped_subsets = sorted(all_subsets - {"bengali", "latin"})
    dropped_weights = sorted({
        f"{f['family']} {f['weight']}" for f in faces
        if f["family"] in SPEC and f["weight"] not in SPEC[f["family"]]["weights"]
    })
    print(f"  keeping {len(wanted)}; dropped subsets [{', '.join(dropped_subsets)}]")
    if dropped_weights:
        print(f"  dropped weights  [{', '.join(dropped_weights)}] — unused by §7.4")

    written: list[dict] = []
    total = 0
    for face in wanted:
        name = f"{face['slug']}-{face['subset']}-{face['weight']}.woff2"
        try:
            data = fetch(face["url"])
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  FAILED {name}: {exc}", file=sys.stderr)
            return 1
        (out_dir / name).write_bytes(data)
        face["file"], face["bytes"] = name, len(data)
        written.append(face)
        total += len(data)
        print(f"  {name:<44} {len(data) / 1024:>6.1f} KB")

    # ── the §14.2 critical-path budget ───────────────────────────────────────
    critical = [f for f in written if (f["slug"], f["subset"], f["weight"]) in PRELOAD]
    critical_kb = sum(f["bytes"] for f in critical) / 1024
    print(f"\n  total on disk      {total / 1024:>7.1f} KB in {len(written)} file(s)")
    print(f"  critical path      {critical_kb:>7.1f} KB in {len(critical)} preloaded face(s) "
          f"of {CRITICAL_BUDGET_KB} KB")
    over_budget = critical_kb > CRITICAL_BUDGET_KB
    if over_budget:
        print(f"  OVER BUDGET by {critical_kb - CRITICAL_BUDGET_KB:.1f} KB — "
              "remove a face from PRELOAD", file=sys.stderr)

    # ── emit the @font-face block ────────────────────────────────────────────
    lines = [
        "/* =============================================================================",
        "   §14.2 Self-hosted fonts — GENERATED by tools/fetch-fonts.py",
        "   =============================================================================",
        "   No CDN, no Google Fonts at runtime. `font-display: swap` everywhere, so a slow",
        "   connection shows text in the fallback face immediately rather than nothing.",
        "",
        "   `unicode-range` scopes each face to the block it covers, so a Latin-only page",
        "   downloads no Bengali glyphs at all — which is most of the saving.",
        "",
        f"   Critical path: {len(critical)} preloaded face(s), {critical_kb:.1f} KB of the "
        f"{CRITICAL_BUDGET_KB} KB",
        "   budget in §14.2. The serif display face is deliberately NOT preloaded: Noto Serif",
        "   Bengali is the heaviest file here, and preloading it beside the body face would",
        "   exceed the budget. `font-display: swap` covers the gap.",
        "",
        "   To regenerate: python tools/fetch-fonts.py",
        "   ============================================================================= */",
        "",
    ]
    for face in written:
        preload = (face["slug"], face["subset"], face["weight"]) in PRELOAD
        lines += [
            f"/* {face['family']} {face['weight']} — {face['subset']}"
            f"{' (preloaded)' if preload else ''} */",
            "@font-face {",
            f"  font-family: \"{face['family']}\";",
            "  font-style: normal;",
            f"  font-weight: {face['weight']};",
            "  font-display: swap;",
            f"  src: url(\"../fonts/{face['file']}\") format(\"woff2\");",
            f"  unicode-range: {face['range']};",
            "}",
            "",
        ]

    print("\n" + "-" * 78)
    print("@font-face block for assets/tailwind/source.css")
    print("(URLs are relative to the COMPILED sheet at app/static/css/app.css)")
    print("-" * 78 + "\n")
    print("\n".join(lines))
    print("-" * 78)
    print("NOT FETCHED — not distributed via Google Fonts (§14.2):")
    for slug, why in EXTRA_FALLBACKS.items():
        print(f"  {slug:<12} {why}")
    print("  They stay in the --font-* stacks as local fallbacks. Absent files are not an")
    print("  error: they are picked up on machines that have them installed (common on")
    print("  Bangladeshi Windows) and degrade silently elsewhere.")
    return 2 if over_budget else 0


if __name__ == "__main__":
    raise SystemExit(main())
