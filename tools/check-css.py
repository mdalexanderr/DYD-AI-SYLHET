#!/usr/bin/env python3
"""Policy gate for the compiled Tailwind stylesheet — plan.md §7.6.1, §8.1 rule 4.

    python tools/check-css.py [--file app/static/css/app.css]

Exits 0 when the sheet obeys the design system, 1 when it does not. Wired into
`npm run css:check`, `ci.yml`, and `deploy.sh --check-css`.

WHAT THIS GUARDS
    The @theme wipe in assets/tailwind/source.css makes the *token-driven* banned
    utilities impossible to write. It cannot reach Tailwind's static utilities
    (`backdrop-filter`, bare `backdrop-blur`) or anything a developer writes in
    plain CSS inside the stylesheet. Those are caught here, by inspecting the
    compiled output. The two mechanisms together are what §7.6.1 claims.

CHECKS
    1. backdrop-filter        glassmorphism — banned outright (§7.6)
    2. gradient hue           more than one hue among gradient stops (§7.6.1)
    3. border radius          above 12px, except the pill (999px+)
    4. shadow softness        blur + spread above 32px
    5. theme wipes            the @theme `initial` lines still hold in the output
    6. size budget            max 45 KB gzipped (§8.1 rule 4); min 12 KB sanity

DEVIATION FROM §7.6.1 — "or `backdrop-filter`" CANNOT BE TAKEN LITERALLY
    Tailwind v4.3 emits a static `.backdrop-filter` utility and nine
    `@property --tw-backdrop-*` declarations UNCONDITIONALLY — they are in the
    sheet even when no template mentions backdrop at all. Verified by an
    isolation build against an empty template set.

    Failing on the bare string therefore makes the gate permanently red, and a
    gate that always fails gets disabled — which is worse than no gate. This
    checker instead distinguishes:

      tolerated  Tailwind's static `.backdrop-filter` utility, ALWAYS emitted
      FAILED     any OTHER selector declaring backdrop-filter — i.e. handwritten
                 CSS in source.css
      FAILED     any selector SETTING `--tw-backdrop-blur: blur(...)`, which
                 means a template actually used a backdrop utility

    The token-driven variants (`backdrop-blur-lg`, …) are already impossible:
    the `--blur-*: initial` wipe in source.css removes the scale, so those
    classes do not compile at all.
    Class usage in TEMPLATES is caught by tools/check-bans.py, which is where a
    `backdrop-blur` written by hand can actually be seen.

WHY blur + SPREAD, NOT blur ALONE
    §7.6.1 says "a shadow with a blur over 32px". Read literally that rejects the
    plan's own token, because §7.3 defines `--shadow-3: 0 20px 44px -24px` — a
    44px blur with a -24px spread. A negative spread pulls the shadow in, so the
    softness that is actually visible is blur + spread = 20px.

    This checker therefore measures NET softness (blur + spread), which is the
    property §7.6.1 is really about ("all very quiet"). A literal reading would
    fail on the project's own tokens, which cannot be the intent.

STDLIB ONLY — package.json runs this as bare `python`, so it must not need the venv.
"""

from __future__ import annotations

import argparse
import gzip
import re
import sys
from pathlib import Path

MAX_GZIP_BYTES = 45 * 1024  # §8.1 rule 4 / §15.1

# Sanity floor: catches an empty or failed build, nothing more.
#
# NOT 20 KB. §17.3's deploy step says "verify app.css arrived and is > 20 KB", and
# that number does not match reality: with the full token set, 8 self-hosted faces,
# every hand-written component and an empty template tree, the real sheet is
# ~17.7 KB — so a 20 KB floor fails on a healthy build. The floor here is 12 KB,
# which still catches a zero-byte or half-written artefact.
#
# ACTION FOR PHASE 9: re-derive the deploy.sh threshold from the ACTUAL shipped
# size once the templates exist (it will be larger then), rather than inheriting
# the plan's estimate.
MIN_RAW_BYTES = 12 * 1024
MAX_RADIUS_PX = 12  # §7.3 — only xs/sm/md/lg, plus the pill
MAX_SHADOW_BLUR_PX = 32  # §7.6.1, measured as blur + spread
PILL_MIN_PX = 999  # --radius-pill

# Tailwind v4.3 emits `.backdrop-filter` unconditionally; see the docstring.
TAILWIND_STATIC_BACKDROP = {".backdrop-filter"}

HEX_RE = re.compile(r"#([0-9a-fA-F]{3,8})\b")
RGB_RE = re.compile(r"rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)")
OKLAB_RE = re.compile(r"oklab\([^)]*\)")
OKLCH_RE = re.compile(r"oklch\(\s*([\d.]+%?)\s+([\d.]+)\s+([\d.]+)")
VAR_RE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^)]*))?\)")

# A hue bucket of 30° means two greens are one hue and green→gold is two.
HUE_BUCKET = 30


class Finding:
    def __init__(self, check: str, detail: str, fix: str) -> None:
        self.check = check
        self.detail = detail
        self.fix = fix

    def __str__(self) -> str:
        return f"  FAIL  {self.check}\n        {self.detail}\n        fix: {self.fix}"


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────


def gzip_size(data: bytes) -> int:
    return len(gzip.compress(data, compresslevel=9))


def force_utf8() -> None:
    """This tool prints ‘§’. A cp1252 console mangles it, and a mangled message
    in a build log is worse than no message."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def collect_custom_props(css: str) -> dict[str, str]:
    """Every `--name: value;` in the sheet, so var() can be resolved."""
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;}]+)", css)}


def resolve(value: str, props: dict[str, str], depth: int = 0) -> str:
    """Substitute var(--x) so radius/shadow tokens can be measured. 2 passes is plenty."""
    if depth > 2 or "var(" not in value:
        return value

    def sub(m: re.Match[str]) -> str:
        name, fallback = m.group(1), m.group(2)
        return props.get(name, fallback if fallback is not None else "0")

    return resolve(VAR_RE.sub(sub, value), props, depth + 1)


def hue_of(token: str) -> float | None:
    """Hue in degrees for a colour literal, or None if it is not one."""
    token = token.strip()

    if m := OKLCH_RE.match(token):
        try:
            return float(m.group(3))
        except ValueError:
            return None

    if token.startswith("oklab("):
        # oklab has no hue channel; treat as neutral so it never triggers
        return None

    if m := HEX_RE.search(token):
        digits = m.group(1)
        if len(digits) in (3, 4):
            digits = "".join(c * 2 for c in digits[:3])
        if len(digits) not in (6, 8):
            return None
        r, g, b = (int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4))
        return _hue(r, g, b)

    if m := RGB_RE.search(token):
        r, g, b = (min(max(float(m.group(i)) / 255, 0.0), 1.0) for i in (1, 2, 3))
        return _hue(r, g, b)

    return None


def _hue(r: float, g: float, b: float) -> float:
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return 0.0  # greyscale — no hue to compare
    d = mx - mn
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60.0


def bucket(hue: float) -> int:
    return int(hue // HUE_BUCKET)


def split_shadows(value: str) -> list[str]:
    """Split a box-shadow list on commas that are NOT inside parens."""
    parts, depth, current = [], 0, []
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def shadow_lengths(shadow: str) -> list[float]:
    r"""The length components of one box-shadow, in order, in px.

    Colour functions are removed first, then the remaining tokens are classified.
    This is deliberately token-based rather than a `(\d+)(px|rem)` positional scan:
    offsets are very often written as a bare `0` with no unit, and a positional
    regex silently drops it — which shifts blur into the offset slot and makes the
    checker miss an over-soft shadow entirely. That mistake was in this file.

    Box-shadow order is (offset-x, offset-y, blur, spread), so callers read
    `lengths[2]` as the blur and `lengths[3]` as the spread.
    """
    cleaned = re.sub(r"[\w-]+\([^)]*\)", " ", shadow)
    out: list[float] = []
    for token in cleaned.split():
        if token == "inset":
            continue
        m = re.fullmatch(r"(-?\d*\.?\d+)(px|rem|em)?", token)
        if not m:
            continue  # a colour like #000, or a keyword
        number, unit = float(m.group(1)), m.group(2)
        if unit is None and number != 0:
            continue  # a bare non-zero number is not a length
        out.append(number * (16 if unit in ("rem", "em") else 1))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# checks
# ─────────────────────────────────────────────────────────────────────────────


def check_backdrop_filter(css: str) -> list[Finding]:
    """Glassmorphism (§7.6) — see the module docstring for why the bare string is
    tolerated. Tailwind's static `.backdrop-filter` is always present; anything
    else declaring the property was written by hand."""
    findings: list[Finding] = []

    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        prelude, body = m.group(1).strip(), m.group(2)
        if "backdrop-filter" not in body:
            continue
        selectors = {s.strip() for s in prelude.split(",") if s.strip()}
        # @property blocks and the static utility are Tailwind's, not ours
        extra = {
            s for s in selectors
            if s not in TAILWIND_STATIC_BACKDROP and not s.startswith("@property")
        }
        if extra:
            findings.append(
                Finding(
                    "backdrop-filter in handwritten CSS",
                    f"selector(s) {', '.join(sorted(extra))} declare backdrop-filter",
                    "remove it; §7.6 bans glassmorphism. Depth comes from rules, "
                    "not softness.",
                )
            )

    # Belt: a rule that actually SETS the blur variable means a template used a
    # backdrop utility. The --blur-* wipe should prevent this from ever existing.
    for m in re.finditer(
        r"([^{}]+)\{[^{}]*--tw-backdrop-blur\s*:\s*(?!initial|,)[^{};]+[^{}]*\}", css
    ):
        selector = m.group(1).strip()
        if selector.startswith("@property") or selector in TAILWIND_STATIC_BACKDROP:
            continue
        findings.append(
            Finding(
                "backdrop-blur utility used",
                f"selector {selector} sets --tw-backdrop-blur to a real value",
                "remove the backdrop-blur class from the template; §7.6.1",
            )
        )

    return findings


def check_gradient_hues(css: str) -> list[Finding]:
    """More than one hue among gradient stops (§7.6.1).

    CONSERVATIVE ON PURPOSE: Tailwind emits `linear-gradient(var(--tw-gradient-stops))`,
    so the stops cannot be paired to a specific gradient. Every gradient-stop colour in
    the sheet is therefore treated as belonging to one gradient. The Surma Protocol uses
    no CSS gradients at all, so this cannot produce a false positive today — and if a
    gradient is ever wanted, one hue family is the rule.
    """
    stops: list[tuple[str, str]] = []
    for prop in ("--tw-gradient-from", "--tw-gradient-via", "--tw-gradient-to",
                 "--tw-gradient-stops", "--tw-gradient-position"):
        for m in re.finditer(re.escape(prop) + r"\s*:\s*([^;}]+)", css):
            stops.append((prop, m.group(1)))

    for m in re.finditer(r"(?:linear|radial|conic)-gradient\(([^;{}]*)\)", css):
        body = m.group(1)
        if "var(" in body:
            continue  # unresolved; covered by the --tw-gradient-* properties above
        stops.append(("gradient()", body))

    hues: dict[int, list[str]] = {}
    for _prop, value in stops:
        for token in re.findall(r"#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)|oklch\([^)]*\)|oklab\([^)]*\)", value):
            h = hue_of(token)
            if h is None:
                continue
            hues.setdefault(bucket(h), []).append(token)

    if len(hues) > 1:
        summary = "; ".join(f"{b * HUE_BUCKET}–{b * HUE_BUCKET + HUE_BUCKET}°: {sorted(set(v))}"
                            for b, v in sorted(hues.items()))
        return [
            Finding(
                "multi-hue gradient",
                f"{len(hues)} hue families among gradient stops — {summary}",
                "use one hue family, or drop the gradient; §7.6.1",
            )
        ]
    return []


def check_radii(css: str, props: dict[str, str]) -> list[Finding]:
    findings = []
    for m in re.finditer(r"border-radius\s*:\s*([^;}]+)", css):
        raw = m.group(1).strip()
        value = resolve(raw, props)
        if "infinity" in value:
            continue  # calc(infinity * 1px) — the pill
        for px in re.findall(r"(-?[\d.]+)(?:e[+-]?\d+)?px", value):
            n = float(px)
            if n <= MAX_RADIUS_PX:
                continue  # xs / sm / md / lg — fine
            if n >= PILL_MIN_PX:
                continue  # the pill, which §7.3 permits
            if n >= 1e30:
                # Tailwind minifies `rounded-full`'s calc(infinity * 1px) to
                # 3.40282e38px (FLT_MAX). It is a pill, and Tailwind emits the
                # utility unconditionally, so failing here would keep the gate
                # permanently red. Templates are steered to `rounded-pill` by
                # tools/check-bans.py instead.
                continue
            findings.append(
                Finding(
                    f"border-radius {n:g}px is in the banned band",
                    f"`{raw}` resolves to `{value.strip()}` — the rounded-3xl family",
                    "use a --radius-* token (xs/sm/md/lg/pill); §7.3",
                )
            )
    return findings


def check_shadows(css: str, props: dict[str, str]) -> list[Finding]:
    """Net softness = blur + spread (§7.6.1, see module docstring)."""
    findings = []
    declarations = [(m.group(1), m.group(2)) for m in
                    re.finditer(r"(--shadow-[\w-]+|box-shadow)\s*:\s*([^;}]+)", css)]

    for name, raw in declarations:
        value = resolve(raw, props)
        if value.strip() in ("none", "0", "0 0 #0000", "0 0 rgb(0 0 0 / 0)"):
            continue
        for shadow in split_shadows(value):
            lengths = shadow_lengths(shadow)
            if len(lengths) < 3:
                continue  # not an offset/length/blur triple
            blur = lengths[2]
            spread = lengths[3] if len(lengths) > 3 else 0.0
            net = blur + spread
            if net > MAX_SHADOW_BLUR_PX:
                findings.append(
                    Finding(
                        f"shadow softness {net:g}px > {MAX_SHADOW_BLUR_PX}px",
                        f"`{name}: {raw.strip()}` (blur {blur:g}px, spread {spread:g}px)",
                        f"lower the blur to <= {MAX_SHADOW_BLUR_PX - spread:g}px; §7.6.1",
                    )
                )
    return findings


def check_theme_wipes(css: str) -> list[Finding]:
    """The @theme wipes in source.css must still hold in the SHIPPED sheet.

    This replaces a throwaway probe template. §7.6.1 claims the banned families are
    \"structurally impossible to write\"; a probe proved it once, on one afternoon.
    Asserting it against the compiled artefact proves it on every build instead, and
    needs no file that deliberately contains banned classes.

    A token can reappear three ways, and all three are caught here: someone removes
    a wipe, someone re-adds a default Tailwind value below it, or an `@source`
    directive starts scanning a file that references a banned class.
    """
    wiped = {
        "wiped palette (--color-*: initial)": (
            r"--color-(?:indigo|purple|violet|fuchsia|pink|rose|sky|cyan|teal|emerald|"
            r"lime|amber|orange|yellow|blue|slate|gray|zinc|neutral|stone)-\d+",
            "a Tailwind default colour is back — check the `--color-*: initial` line",
        ),
        "wiped radius (--radius-*: initial)": (
            r"--radius-(?:3xl|4xl|full)",
            "a default radius is back — §7.3 allows only xs/sm/md/lg/pill",
        ),
        "wiped blur (--blur-*: initial)": (
            r"--blur-(?:xs|sm|md|lg|xl|2xl|3xl)",
            "the blur scale is back — §7.6.1 bans glassmorphism; blur-* is unavailable too",
        ),
    }
    findings = []
    for label, (pattern, why) in wiped.items():
        hits = sorted(set(re.findall(pattern, css)))
        if hits:
            findings.append(
                Finding(label, f"found {', '.join(hits[:6])}", f"{why}; see §7.6.1")
            )
    return findings


def check_size(raw: bytes) -> list[Finding]:
    findings = []
    gz = gzip_size(raw)
    if gz > MAX_GZIP_BYTES:
        findings.append(
            Finding(
                f"gzipped size {gz / 1024:.1f} KB > {MAX_GZIP_BYTES / 1024:.0f} KB",
                "the CSS performance budget (§15.1)",
                "remove unused tokens or split the admin skin into its own file",
            )
        )
    if len(raw) < MIN_RAW_BYTES:
        findings.append(
            Finding(
                f"stylesheet only {len(raw) / 1024:.1f} KB",
                f"below the {MIN_RAW_BYTES / 1024:.0f} KB sanity floor — the build probably failed",
                "re-run `npm run css:build`; check that source.css has its @theme block",
            )
        )
    return findings


# ─────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(description="CSS policy gate (plan.md §7.6.1).")
    parser.add_argument("--file", default="app/static/css/app.css",
                        help="compiled stylesheet to inspect (default: %(default)s)")
    parser.add_argument("--quiet", action="store_true", help="only print on failure")
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.exists():
        print(f"check-css: {path} not found — run `npm run css:build` first", file=sys.stderr)
        return 1

    raw = path.read_bytes()
    css = raw.decode("utf-8", errors="replace")
    props = collect_custom_props(css)

    findings: list[Finding] = []
    findings += check_backdrop_filter(css)
    findings += check_gradient_hues(css)
    findings += check_radii(css, props)
    findings += check_shadows(css, props)
    findings += check_theme_wipes(css)
    findings += check_size(raw)

    if not args.quiet:
        print(f"check-css: {path}")
        print(f"  raw      {len(raw):,} bytes")
        print(f"  gzipped  {gzip_size(raw):,} bytes  ({gzip_size(raw) / 1024:.1f} KB of "
              f"{MAX_GZIP_BYTES / 1024:.0f} KB budget)")
        print(f"  props    {len(props)} custom properties")

    if findings:
        print(f"\n{len(findings)} policy violation(s):", file=sys.stderr)
        for f in findings:
            print(f, file=sys.stderr)
        return 1

    if not args.quiet:
        print("  OK — no banned pattern found (§7.6.1)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
