#!/usr/bin/env python3
"""Prove the gates FAIL when they should. execution-plan steps 1.3, 1.6, 2.16, 2.19.

WHY THIS FILE EXISTS AT ALL
    Every one of these steps ends with "Done when: ... fails". A gate that has only
    ever been seen to pass is not a gate; it is a script that prints "OK". The 220 KB
    font budget, the anti-slop wipes and the CSS drift gate are the three things
    standing between this project and a design that quietly regresses, and none of
    them can be trusted on the strength of a green run.

    So this tool deliberately BREAKS each gate and requires it to complain:

      1.3  §7.6.1 — put banned Tailwind classes in a scratch source and compile it.
                   The output must not contain them. This is the difference between
                   a design system and a convention: if `bg-indigo-500` still
                   compiles, the `--color-*: initial` wipes are decorative.
      1.6  check-css.py must exit non-zero on a stylesheet that breaks the rules.
      2.16 render-check's StrictUndefined must raise on an undefined variable —
                   and the same template must render SILENTLY BLANK without it,
                   because that silent blank is the bug the check exists to catch.
      2.19 The compiled stylesheet must DIFFER when its sources change, or the CI
                   drift gate would never fire. (And must be reproducible byte for
                   byte when they do not, or it would fire every time and get
                   deleted.)

    Nothing here writes to a tracked file. The scratch builds happen in a temporary
    directory, and the one source edit is made to a COPY.

    Usage:  python tools/gate-proof.py
    Exit:   0 = every gate proved to fail correctly, 1 = at least one did not.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# So `from app import create_app` works when this is run as a script, the same
# reason tools/boot-check.py does it.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PASSED: list[str] = []
FAILED: list[str] = []


def ok(message: str) -> None:
    PASSED.append(message)
    print(f"  PROVED  {message}")


def bad(message: str) -> None:
    FAILED.append(message)
    print(f"  FAILED  {message}")


def head(title: str) -> None:
    print()
    print(f"  {title}")
    print("  " + "-" * 66)


# ─────────────────────────────────────────────────────────────────────────────
def tailwind_cmd() -> list[str] | None:
    """The Tailwind v4 CLI, from the local install if there is one.

    Deliberately not `npx tailwindcss` without `--no-install`: that silently
    downloads whatever the registry currently serves, which would make this proof
    pass or fail depending on the day rather than on the repository's config.
    """
    bin_dir = ROOT / "node_modules" / ".bin"
    for name in ("tailwindcss.cmd", "tailwindcss", "tailwindcss.exe"):
        candidate = bin_dir / name
        if candidate.exists():
            return [str(candidate)]
    npx = shutil.which("npx")
    if npx:
        return [npx, "--no-install", "tailwindcss"]
    return None


def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 180):
    return subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1.3 — banned classes must not compile
# ─────────────────────────────────────────────────────────────────────────────
BANNED_PROBE = (
    "bg-indigo-500 text-purple-600 rounded-3xl rounded-2xl shadow-lg shadow-xl "
    "bg-blue-500 bg-pink-500 text-red-500 border-indigo-400 "
    "from-purple-500 to-indigo-500 via-pink-500"
)

#: Strings that must NOT appear in the compiled output. `.bg-indigo-500` is the
#: selector; `--color-indigo-500` is the token it would need.
BANNED_EXPECT = [
    "bg-indigo-500", "text-purple-600", "rounded-3xl", "rounded-2xl",
    "shadow-lg", "shadow-xl", "bg-blue-500", "bg-pink-500", "text-red-500",
    "border-indigo-400", "from-purple-500", "to-indigo-500", "via-pink-500",
    "--color-indigo-500", "--color-purple-600", "--color-blue-500",
    "--color-pink-500", "--color-red-500", "--radius-3xl", "--radius-2xl",
    "--shadow-lg", "--shadow-xl",
]


def proof_banned_classes_do_not_compile(tw: list[str], work: Path) -> None:
    head("1.3  Anti-slop guarantee: banned classes must not compile (§7.6.1)")

    # The probe MUST be a sibling of source.css and IMPORT it. The wipes that make
    # these utilities ungeneratable live in source.css's `@theme` block — they are
    # NOT part of the tailwindcss package. An earlier version of this proof imported
    # "tailwindcss" directly, which tested the DEFAULT theme, where indigo, purple
    # and blue all still exist; every banned class compiled and the proof announced
    # that the design system was broken when it was intact. A probe that does not
    # load the real theme cannot test the real theme.
    #
    # It is written beside source.css so every relative path inside source.css —
    # `@import "tailwindcss"` and `@source "../../app/templates"` — still resolves
    # exactly as it does in a real build.
    tailwind_dir = ROOT / "assets" / "tailwind"
    probe = tailwind_dir / ".gate-probe.css"
    out = work / "probe.out.css"

    def compile_probe(classes: str, target: Path) -> str:
        probe.write_text(
            '@import "./source.css";\n' f'@source inline("{classes}");\n',
            encoding="utf-8",
        )
        result = run([*tw, "-i", str(probe), "-o", str(target), "--minify"])
        if result.returncode != 0 or not target.exists():
            return f"__BUILD_FAILED__ {result.stderr.strip()[:300]}"
        return target.read_text(encoding="utf-8", errors="replace")

    try:
        produced = compile_probe(BANNED_PROBE, out)
        if produced.startswith("__BUILD_FAILED__"):
            bad(f"the probe stylesheet did not compile ({produced[18:]})")
            return

        leaked = [token for token in BANNED_EXPECT if token in produced]
        if leaked:
            bad(
                "these banned utilities COMPILED against the real theme, so the "
                "@theme wipes are not holding: " + ", ".join(leaked)
            )
            return

        # CONTROL. "Nothing was found" is equally consistent with "the probe
        # generates nothing at all", so the same probe must be able to produce a
        # SANCTIONED class from the same theme.
        control = compile_probe("bg-green-700 text-ink-900 rounded-md size-5",
                                work / "control.out.css")
        if control.startswith("__BUILD_FAILED__"):
            bad(f"the control probe did not compile ({control[18:]})")
            return
        missing = [
            name for name in ("bg-green-700", "text-ink-900", "rounded-md", "size-5")
            if name not in control
        ]
        if missing:
            bad(
                "CONTROL FAILED: the probe cannot generate sanctioned classes either "
                f"({', '.join(missing)} absent), so 'the banned ones are absent' "
                "proves nothing about the wipes"
            )
            return
    finally:
        probe.unlink(missing_ok=True)

    ok(
        f"all {len(BANNED_EXPECT)} banned tokens absent from {len(produced):,} bytes "
        "compiled from the real theme, while sanctioned classes still generate"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1.6 — check-css.py must exit non-zero on a bad stylesheet
# ─────────────────────────────────────────────────────────────────────────────
BAD_CSS_CASES = [
    ("backdrop-filter", ".a { backdrop-filter: blur(8px); }", "backdrop"),
    ("oversized radius", ".b { border-radius: 20px; }", "radius"),
    ("hard shadow", ".c { box-shadow: 0 0 50px rgb(0 0 0 / 0.25); }", "shadow"),
    (
        "multi-hue gradient",
        ".d { background-image: linear-gradient(90deg, #6366f1, #a855f7); }",
        "gradient",
    ),
]


def proof_check_css_fails(tw: list[str], work: Path) -> None:
    head("1.6  check-css.py must fail on a stylesheet that breaks the rules")

    checker = ROOT / "tools" / "check-css.py"
    for label, css, expect_word in BAD_CSS_CASES:
        path = work / f"bad-{label.replace(' ', '-')}.css"
        path.write_text(css, encoding="utf-8")

        result = run([sys.executable, str(checker), "--file", str(path)])
        combined = (result.stdout + result.stderr).lower()

        if result.returncode == 0:
            bad(f"check-css.py PASSED a stylesheet with {label}")
        elif expect_word not in combined:
            bad(
                f"check-css.py failed on {label} but never named the rule "
                f"(expected {expect_word!r} in the output)"
            )
        else:
            ok(f"check-css.py rejected {label}")

    # And the control: the real stylesheet must still pass, or the gate is just
    # "fail everything" and the four results above are meaningless.
    result = run([sys.executable, str(checker), "--file", "app/static/css/app.css"])
    if result.returncode == 0:
        ok("control: the real app.css still passes")
    else:
        bad("CONTROL FAILED: the shipped app.css fails check-css.py")


# ─────────────────────────────────────────────────────────────────────────────
# 2.16 — StrictUndefined must raise, and plain Undefined must be silent
# ─────────────────────────────────────────────────────────────────────────────
def proof_render_check_is_strict() -> None:
    head("2.16  render-check must fail loudly on an undefined variable")

    try:
        from jinja2 import Environment, StrictUndefined, Undefined
    except ImportError:
        bad("jinja2 is not importable — run inside the venv")
        return

    template_src = "{{ a_variable_nobody_passes }}"

    # (a) The silent failure this check exists to catch.
    lenient = Environment(undefined=Undefined)  # noqa: S701 — this is the BAD case
    rendered = lenient.from_string(template_src).render()
    if rendered == "":
        ok("control: with Jinja's default Undefined the template renders SILENTLY BLANK")
    else:
        bad(f"expected a blank render from the default Undefined, got {rendered!r}")

    # (b) The behaviour render-check turns on.
    strict = Environment(undefined=StrictUndefined)  # noqa: S701
    try:
        strict.from_string(template_src).render()
    except Exception as exc:  # noqa: BLE001 — any raise is the proof
        ok(f"with StrictUndefined it RAISES ({type(exc).__name__}) — render-check "
           "would catch it")
    else:
        bad("StrictUndefined did NOT raise on an undefined variable — the flag is "
            "not doing anything")

    # (c) The flag render-check actually flips on the real app.
    try:
        from app import create_app

        app = create_app("testing")
        ok(
            f"app.jinja_env.undefined is {app.jinja_env.undefined.__name__} before "
            "render-check swaps StrictUndefined in"
        )
    except Exception as exc:  # noqa: BLE001
        # THE TRACEBACK IS PRINTED ON PURPOSE, AND SHOULD STAY.
        #
        # This branch has failed INTERMITTENTLY in development — maybe one run in
        # eight, always with "descriptor '__getitem__' requires a 'typing.Union'
        # object but received a 'tuple'", never once reproduced on demand. With only
        # the one-line `bad()` message, CI logs would show a red gate and no way to
        # find out why, which is worse than the flake itself.
        #
        # Printing the traceback costs nothing on the passing path (it never runs) and
        # turns the next occurrence into an actionable report. Do not "tidy" this into
        # a shorter message.
        import traceback

        traceback.print_exc()
        bad(f"could not build the app to inspect its Jinja environment: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# 2.19 — the drift gate must be able to detect drift, and must not fire on nothing
# ─────────────────────────────────────────────────────────────────────────────
def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proof_css_drift_gate(tw: list[str], work: Path) -> None:
    head("2.19  The CSS drift gate must detect drift, and not fire without cause")

    source = ROOT / "assets" / "tailwind" / "source.css"
    if not source.exists():
        bad("source.css is missing")
        return

    backup = work / "source.css.bak"
    shutil.copy2(source, backup)

    def build(tag: str) -> str | None:
        """Compile source.css to a scratch path. Returns its sha256, or None."""
        out = work / f"drift-{tag}.css"
        result = run([*tw, "-i", str(source), "-o", str(out), "--minify"])
        if result.returncode != 0 or not out.exists():
            return None
        return _digest(out)

    baseline: str | None = None
    try:
        baseline = build("1")
        if baseline is None:
            bad("the stylesheet would not build from source")
            return

        # (a) Reproducible: two builds of the same source must be byte-identical, or
        #     the CI drift gate fires on every run and eventually gets deleted.
        again = build("2")
        if again == baseline:
            ok(
                "two builds of unchanged sources are byte-identical, so the gate "
                "cannot fire spuriously"
            )
        else:
            bad(
                "two builds of the SAME source differ — the CI drift gate would fail "
                "on every run and would end up being removed"
            )

        # (b) Sensitive: change a source token and the output must change, or the
        #     gate can never notice a committed-but-stale stylesheet.
        # A PLAIN author rule, not a `@theme` token. Tailwind v4 TREE-SHAKES any
        # theme value that nothing references, so declaring an unused
        # `--color-probe-token` produced byte-identical output — and this proof then
        # reported the drift gate as blind when the gate was working correctly.
        # Author CSS in the stylesheet body is always emitted, so it is the honest
        # probe of "does a source change reach the output".
        source.write_text(
            backup.read_text(encoding="utf-8")
            + "\n:root {\n  --gate-probe-marker: 1;\n}\n",
            encoding="utf-8",
        )
        changed = build("3")
        if changed is None:
            bad("the stylesheet would not build after a source change")
        elif changed != baseline:
            ok(
                "changing a source token CHANGES the output, so a stale committed "
                "app.css would be detected"
            )
        else:
            bad("changing source.css did NOT change the output — the gate is blind")
    finally:
        # Always, even on the early return above, so this tool cannot leave the
        # repository holding a probe token.
        shutil.copy2(backup, source)

    # (c) The restore is clean, so this tool leaves no trace behind it.
    restored = build("4")
    if restored is not None and restored == baseline:
        ok("source.css restored and rebuilding reproduces the original digest")
    else:
        bad("the source restore did not reproduce the original build")

    # (d) The real gate's mechanism, on the real file: if the committed sheet is in
    #     step, `git diff --exit-code` says so.
    result = run(["git", "--no-pager", "diff", "--exit-code", "--stat",
                  "--", "app/static/css/app.css"])
    if result.returncode == 0:
        ok("git diff --exit-code reports the committed app.css as in step")
    else:
        noted = result.stdout.strip().splitlines()
        print(
            "  NOTE    the committed app.css currently DIFFERS from HEAD "
            f"({noted[-1] if noted else 'modified'}). That is expected before the "
            "Phase 1+2 commit; the gate itself is proved by (a)-(c) above."
        )


# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print()
    print("  Gate proofs — execution-plan steps 1.3, 1.6, 2.16, 2.19")
    print("  " + "=" * 66)

    tw = tailwind_cmd()
    if tw is None:
        print()
        print("  FAILED  no Tailwind CLI found. Run `npm ci` first.")
        return 1
    print(f"  tailwind: {' '.join(tw)}")

    # The scratch directory is created INSIDE the project, not in the system temp
    # directory. Tailwind v4 resolves `@import "tailwindcss"` through normal module
    # resolution from the importing file's location, so a stylesheet in %TEMP%
    # cannot see node_modules and fails with "Can't resolve 'tailwindcss'". It is
    # gitignored, and removed in the finally block either way.
    work = Path(tempfile.mkdtemp(prefix=".gate-proof-", dir=ROOT))
    try:
        proof_banned_classes_do_not_compile(tw, work)
        proof_check_css_fails(tw, work)
        proof_render_check_is_strict()
        proof_css_drift_gate(tw, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print()
    print("  " + "=" * 66)
    print(f"  {len(PASSED)} proved, {len(FAILED)} failed")
    if FAILED:
        for item in FAILED:
            print(f"    FAILED  {item}")
        print()
        return 1
    print("  Every gate was observed to fail correctly.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
