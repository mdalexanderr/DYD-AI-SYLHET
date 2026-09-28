#!/usr/bin/env python3
"""Build the brand icon set from the master logo.

    python tools/build-brand-icons.py [source.png]

WHY A SCRIPT AND NOT SIXTEEN COMMITTED IMAGES NOBODY CAN REGENERATE
    A favicon is not one file. It is a `.ico` carrying three sizes, a 16/32/48 PNG
    set, a 180px apple-touch icon that must be OPAQUE (iOS draws transparency as
    black), a 192/512 pair for the manifest, and a maskable 512 whose content has to
    survive being cropped to a circle by Android. Each has a different rule about
    padding and background, and doing them by hand is how a site ends up with a
    favicon that is a shrunken photograph with a white box around it.

    Run this again when the logo changes. It writes both halves of the project:

        app/static/img/*            the Flask site (Jinja pages + admin)
        ../frontend/src/assets/*    the React frontend

    The frontend half is skipped with a note if that folder is not present, so this
    still works in a checkout of this repository on its own.

THE MASTER
    `assets/brand/logo-master.png` — a source asset, not a deployed one. `assets/` is
    excluded from the deploy sync (§17.2), so the master never reaches the server.

WHY THE ARTWORK IS TRIMMED FIRST
    The master has a wide transparent margin. Scaling it straight down produces a
    favicon that is mostly empty space with a speck in the middle. Each output is
    therefore trimmed to its actual pixels and then re-padded to a chosen coverage,
    which is the only way a 16px icon reads as the same mark as a 512px one.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "app" / "static" / "img"
FRONTEND_ASSETS = ROOT.parent / "frontend" / "src" / "assets"

DEFAULT_SOURCE = ROOT / "assets" / "brand" / "logo-master.png"

#: `--color-paper` from assets/tailwind/source.css — the site's page background, and
#: the only correct backdrop for an icon that cannot be transparent.
PAPER = (250, 249, 244, 255)

#: How much of each canvas the artwork should fill. Not one number, deliberately:
#: a favicon needs a little air, a maskable icon needs a lot of it or Android's
#: circular crop eats the book.
LOGO_COVERAGE = 0.96
FAVICON_COVERAGE = 0.88
APPLE_COVERAGE = 0.86
MASKABLE_COVERAGE = 0.58

FAVICON_SIZES = (16, 32, 48)
ICO_SIZES = [(16, 16), (32, 32), (48, 48)]
APPLE_TOUCH_PX = 180
MANIFEST_SIZES = (192, 512)
MASKABLE_PX = 512

#: The header and footer logo. It is displayed at 36–56px, so 256 covers 4x DPR —
#: and at 512 this file was 208 KB, fetched on every page, for pixels no screen
#: can show.
LOGO_PX = 256


def load_master(source: Path) -> Image.Image:
    """The master, as RGBA, with its transparent margin removed."""
    if not source.is_file():
        raise SystemExit(
            f"master logo not found: {source}\n"
            "Pass one explicitly:  python tools/build-brand-icons.py <source.png>"
        )

    image = Image.open(source).convert("RGBA")
    bounds = image.getbbox()
    if bounds is None:
        raise SystemExit(f"{source} is fully transparent — nothing to draw")

    trimmed = image.crop(bounds)
    print(f"  master      {source.name}  {image.size[0]}x{image.size[1]}")
    print(f"  artwork     {trimmed.size[0]}x{trimmed.size[1]} after trimming the margin")
    return trimmed


def fit(art: Image.Image, size: int, coverage: float) -> Image.Image:
    """The artwork, scaled to fill `coverage` of a transparent `size` square."""
    target = max(1, round(size * coverage))
    scale = target / max(art.size)
    scaled = art.resize(
        (max(1, round(art.size[0] * scale)), max(1, round(art.size[1] * scale))),
        Image.LANCZOS,
    )

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(
        scaled,
        ((size - scaled.size[0]) // 2, (size - scaled.size[1]) // 2),
        scaled,
    )
    return canvas


def on_paper(art: Image.Image, size: int, coverage: float) -> Image.Image:
    """The same, flattened onto the site's paper colour.

    Required for apple-touch-icons: iOS composites transparency against black, so a
    transparent icon becomes a dark square with a dark logo on it.
    """
    canvas = Image.new("RGBA", (size, size), PAPER)
    canvas.alpha_composite(fit(art, size, coverage))
    return canvas.convert("RGB")


def write(image: Image.Image, path: Path, **kwargs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True, **kwargs)
    print(f"  wrote       {path.relative_to(ROOT.parent)}  {path.stat().st_size // 1024} KB")


def main(source: Path) -> int:
    print()
    print("  brand icon set")
    print("  " + "=" * 64)

    art = load_master(source)

    # ── The Flask site ──────────────────────────────────────────────────────
    # Same filenames as before, so app/templates/layouts/base.html and
    # site.webmanifest keep pointing at the right things.
    write(fit(art, LOGO_PX, LOGO_COVERAGE), IMG_DIR / "dyd-logo.png")
    write(fit(art, 256, FAVICON_COVERAGE), IMG_DIR / "favicon.ico", sizes=ICO_SIZES)
    for size in FAVICON_SIZES:
        write(fit(art, size, FAVICON_COVERAGE), IMG_DIR / f"favicon-{size}.png")
    write(on_paper(art, APPLE_TOUCH_PX, APPLE_COVERAGE), IMG_DIR / "apple-touch-icon.png")
    for size in MANIFEST_SIZES:
        write(fit(art, size, FAVICON_COVERAGE), IMG_DIR / f"icon-{size}.png")
    # Full-bleed, with the artwork well inside the safe zone: Android crops a
    # maskable icon to whatever shape the launcher uses, circle included.
    maskable = Image.new("RGBA", (MASKABLE_PX, MASKABLE_PX), PAPER)
    maskable.alpha_composite(fit(art, MASKABLE_PX, MASKABLE_COVERAGE))
    write(maskable, IMG_DIR / "icon-maskable-512.png")

    # ── The React frontend ──────────────────────────────────────────────────
    if not FRONTEND_ASSETS.parent.is_dir():
        print(f"\n  note: {FRONTEND_ASSETS.parent} is absent, skipping the frontend copy")
        return 0

    write(fit(art, LOGO_PX, LOGO_COVERAGE), FRONTEND_ASSETS / "brand-logo.png")
    write(fit(art, 64, FAVICON_COVERAGE), FRONTEND_ASSETS / "favicon.png")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE))
