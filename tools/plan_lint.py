#!/usr/bin/env python3
"""
plan_lint.py — structural health check for plan.md.

plan.md is the source of truth and the contract between the two development
tracks (see plan.md §10.5). It is 3,900+ lines with ~220 headings, so drift is
easy to introduce and hard to spot by eye. This script catches it.

Checks
  1. File health      — encoding, NUL bytes, BOM, balanced code fences
  2. Section coverage — every top-level section 1..27 exists as a heading
  3. Subsection gaps  — no missing x.2 between x.1 and x.3
  4. Duplicate numbers— the same section number used twice
  5. Table of contents— every TOC entry resolves to a real heading anchor,
                        and every numbered heading appears in the TOC
  6. Cross-references — every "§X.Y" in the prose points at a heading that exists

Usage
  python tools/plan_lint.py            # lint the default plan.md
  python tools/plan_lint.py --toc      # also regenerate the TOC block in place
  python tools/plan_lint.py path.md

Exit code 0 = clean, 1 = problems found (so CI can gate on it).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAN = REPO_ROOT / "plan.md"

MAX_REASONABLE_SECTIONS = 60   # sanity ceiling; the range is derived, not fixed
HEADING_RE = re.compile(r"^(#{2,6})\s+(.*)$")
TOC_ROW_RE = re.compile(r"^(\s*)- \[(.+?)\]\(#(.+?)\)", re.M)
TOC_ANCHOR_RE = re.compile(r"^(- \[(\d+)\. )", re.M)
# NOTE: no check for "[[TOKEN]]" leftovers here — plan.md legitimately *documents*
# the placeholder convention (§10.6.4), so its examples would false-positive.


def github_slug(title: str) -> str:
    """Reproduce GitHub's heading-anchor algorithm closely enough to validate."""
    s = re.sub(r"[^\w\s-]", "", title.lower(), flags=re.UNICODE)
    return re.sub(r"\s", "-", s)


class Lint:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.raw = path.read_bytes()
        self.problems: list[str] = []
        self.notes: list[str] = []

        try:
            self.text = self.raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            self.text = self.raw.decode("utf-8", errors="replace")
            self.problems.append(f"not valid UTF-8: {exc}")

        self.lines = self.text.splitlines()
        self.headings: list[tuple[int, int, str]] = []  # (lineno, level, text)
        for i, line in enumerate(self.lines, start=1):
            m = HEADING_RE.match(line)
            if m:
                self.headings.append((i, len(m.group(1)), m.group(2).strip()))

        self.slugs = self._compute_slugs()

    # ---------------------------------------------------------------- helpers
    def _compute_slugs(self) -> set[str]:
        seen: dict[str, int] = {}
        out: set[str] = set()
        for _, _, text in self.headings:
            s = github_slug(text)
            if s in seen:
                seen[s] += 1
                s = f"{s}-{seen[s] - 1}"
            else:
                seen[s] = 0
            out.add(s)
        return out

    def numbered_headings(self) -> set[str]:
        return {
            m.group(1)
            for _, _, text in self.headings
            if (m := re.match(r"^(\d+(?:\.\d+)*)", text))
        }

    # ----------------------------------------------------------------- checks
    def check_encoding(self) -> None:
        if self.raw.startswith(b"\xef\xbb\xbf"):
            self.problems.append("file starts with a UTF-8 BOM (GitHub renders it as a stray character)")
        if self.raw.startswith(b"\xff\xfe"):
            self.problems.append("file is UTF-16LE — git will treat it as binary")
        nuls = self.raw.count(0)
        if nuls:
            self.problems.append(f"{nuls} NUL bytes — file is not plain UTF-8 text")
        bad = self.text.count("\ufffd")
        if bad:
            self.problems.append(f"{bad} U+FFFD replacement characters (mojibake)")
        fences = sum(1 for line in self.lines if line.startswith("```"))
        if fences % 2:
            self.problems.append(f"unbalanced code fences ({fences} — must be even)")
        for i, line in enumerate(self.lines, start=1):
            if "<!--PART" in line:
                self.problems.append(f"line {i}: leftover build sentinel")
        self.notes.append(f"{len(self.lines)} lines, {len(self.raw) / 1024:.1f} KB, {fences} code fences")

    def section_numbers(self) -> list[int]:
        """Top-level section numbers actually present, ascending."""
        return sorted(
            {
                int(m.group(1))
                for _, _, text in self.headings
                if (m := re.match(r"^(\d+)\.", text))
            }
        )

    def check_sections(self) -> None:
        present = self.section_numbers()
        if not present:
            self.problems.append("no numbered top-level sections found")
            return
        missing = [n for n in range(1, max(present) + 1) if n not in present]
        if missing:
            self.problems.append(f"missing top-level sections: {missing}")
        if max(present) > MAX_REASONABLE_SECTIONS:
            self.problems.append(
                f"section numbering reached {max(present)} (expected <= {MAX_REASONABLE_SECTIONS})"
            )
        self.notes.append(
            f"top-level sections: {len(present)}, numbered 1-{max(present)}, "
            f"gaps: {missing or 'none'}"
        )

    def check_subsection_gaps(self) -> None:
        for n in self.section_numbers():
            subs = sorted(
                {
                    int(m.group(1))
                    for _, _, text in self.headings
                    if (m := re.match(rf"^{n}\.(\d+)", text))
                }
            )
            if subs and subs != list(range(1, max(subs) + 1)):
                expected = set(range(1, max(subs) + 1))
                self.problems.append(
                    f"§{n} subsection gap — have {subs}, missing {sorted(expected - set(subs))}"
                )

    def check_duplicates(self) -> None:
        seen: dict[str, int] = {}
        for _, _, text in self.headings:
            m = re.match(r"^(\d+(?:\.\d+)*)", text)
            if m:
                seen[m.group(1)] = seen.get(m.group(1), 0) + 1
        dups = {k: v for k, v in seen.items() if v > 1}
        if dups:
            self.problems.append(f"duplicate section numbers: {dups}")

    def check_toc(self) -> None:
        toc = TOC_ROW_RE.findall(self.text)
        if not toc:
            self.problems.append("no table of contents entries found")
            return
        broken = [u for _, _, u in toc if u not in self.slugs]
        if broken:
            shown = ", ".join(broken[:5])
            self.problems.append(f"{len(broken)} TOC links do not resolve: {shown}")

        in_toc = {
            int(m.group(2))
            for m in (TOC_ANCHOR_RE.match(line) for line in self.lines)
            if m
        }
        missing = [n for n in self.section_numbers() if n not in in_toc]
        if missing:
            self.problems.append(f"sections absent from the TOC: {missing}")

        numbered = self.numbered_headings()
        absent = [
            n
            for n in numbered
            if not re.search(rf"^\s*- \[{re.escape(n)}[\. ]", self.text, re.M)
        ]
        if absent:
            self.problems.append(
                f"{len(absent)} numbered headings are missing from the TOC: "
                + ", ".join(sorted(absent, key=_ver_key)[:10])
            )
        self.notes.append(f"TOC entries: {len(toc)} (all resolve: {not broken})")

    def check_cross_references(self) -> None:
        exists = self.numbered_headings()
        refs = sorted(set(re.findall(r"§(\d+(?:\.\d+)*)", self.text)))
        dangling = [r for r in refs if r not in exists]
        if dangling:
            self.problems.append(f"§-references to non-existent sections: {dangling}")
        self.notes.append(f"cross-references: {len(refs)} distinct, all resolving: {not dangling}")

    # ------------------------------------------------------------------ driver
    def run(self) -> int:
        for check in (
            self.check_encoding,
            self.check_sections,
            self.check_subsection_gaps,
            self.check_duplicates,
            self.check_toc,
            self.check_cross_references,
        ):
            check()

        print(f"plan_lint: {self.path}")
        for note in self.notes:
            print(f"  . {note}")
        if self.problems:
            print(f"\n  {len(self.problems)} PROBLEM(S):")
            for p in self.problems:
                print(f"  x {p}")
            return 1
        print("\n  OK - no structural problems found")
        return 0


def _ver_key(s: str) -> tuple[int, ...]:
    return tuple(int(p) for p in s.split("."))


def regenerate_toc(path: Path) -> None:
    """Rewrite the TOC block in place from the current headings."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    sec1_idx = next(i for i, line in enumerate(lines) if re.match(r"^## 1\. ", line))
    try:
        toc_idx = next(
            i for i, line in enumerate(lines) if line.strip() == "## Table of Contents"
        )
    except StopIteration:
        # no TOC yet — insert one immediately before section 1
        toc_idx = sec1_idx
        lines = [
            *lines[:toc_idx],
            "## Table of Contents", "", "---", "",
            *lines[toc_idx:],
        ]
        sec1_idx = next(i for i, line in enumerate(lines) if re.match(r"^## 1\. ", line))

    seen: dict[str, int] = {}
    body: list[str] = []
    for line in lines[sec1_idx:]:
        m = HEADING_RE.match(line)
        if not m:
            continue
        text_ = m.group(2).strip()
        if text_ == "Table of Contents":
            continue
        s = github_slug(re.sub(r"[*`]", "", text_))
        if s in seen:
            seen[s] += 1
            s = f"{s}-{seen[s] - 1}"
        else:
            seen[s] = 0
        indent = " " * ((len(m.group(1)) - 2) * 2)
        body.append(f"{indent}- [{re.sub(r'[*`]', '', text_)}](#{s})")

    header = [
        "## Table of Contents",
        "",
        "> Complete index of every section and subsection. Generated by "
        "`tools/plan_lint.py --toc` —",
        "> regenerate rather than editing it by hand.",
        "",
    ]
    out = lines[:toc_idx] + header + body + ["", "---"] + lines[sec1_idx:]
    path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(f"regenerated TOC with {len(body)} entries in {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("plan", nargs="?", type=Path, default=DEFAULT_PLAN)
    ap.add_argument("--toc", action="store_true", help="regenerate the TOC block in place first")
    args = ap.parse_args()

    if not args.plan.exists():
        print(f"not found: {args.plan}", file=sys.stderr)
        return 2
    if args.toc:
        regenerate_toc(args.plan)
    return Lint(args.plan).run()


if __name__ == "__main__":
    sys.exit(main())
