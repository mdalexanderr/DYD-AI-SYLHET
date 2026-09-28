#!/usr/bin/env python3
"""Build the hero artwork from the supplied master.

    python tools/build-hero-image.py [source.png]

THE SUPPLIED ARTWORK IS A PNG AND THE WEB WANTS A JPEG
    1176x941 at 1.6 MB as a PNG, for a photograph-like illustration with no
    transparency to preserve. Re-encoded as a progressive JPEG it is a fraction of
    that, which matters here: this is the largest image on the front page and it is
    above the fold.

    Run this again if the supplied artwork changes. It writes one file:

        ../frontend/src/assets/hero-landscape.jpg

    The frontend half is skipped with a note if that folder is absent, so this still
    works in a checkout of this repository on its own.

PROVENANCE
    `assets/media/hero-master.png` is the master — a source asset, never deployed,
    because `assets/` is excluded from the deploy sync (§17.2). See docs/FRONTEND.md
    for why the hero's alt text calls it a প্রতীকী চিত্র (symbolic illustration) and
    not a photograph: an AI-generated image presented as documentary photography on
    a site that publishes real participants' stories is a claim the site cannot
    support.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "assets" / "media" / "hero-master.png"
FRONTEND_ASSETS = ROOT.parent / "frontend" / "src" / "assets"

#: 82 keeps the gradients in the sky and the river smooth without the visible
#: blocking that appears in large flat areas below about 78.
QUALITY = 82

#: The front page shows this in a column of roughly 590px, so the master's own width
#: is already 2x for it. Declared rather than hard-coded so a larger master is not
#: silently downscaled.
MAX_WIDTH = 1400


def main(source: Path) -> int:
    print()
    print("  hero artwork")
    print("  " + "=" * 64)

    if not source.is_file():
        raise SystemExit(
            f"master image not found: {source}\n"
            "Pass one explicitly:  python tools/build-hero-image.py <source.png>"
        )

    image = Image.open(source)
    print(f"  master      {source.name}  {image.size[0]}x{image.size[1]}  {image.mode}")

    if FRONTEND_ASSETS.parent.is_dir() is False:
        print(f"  note: {FRONTEND_ASSETS.parent} is absent, nothing to write")
        return 0

    if image.size[0] > MAX_WIDTH:
        height = round(image.size[1] * MAX_WIDTH / image.size[0])
        image = image.resize((MAX_WIDTH, height), Image.LANCZOS)
        print(f"  scaled      {image.size[0]}x{image.size[1]}")

    # JPEG has no alpha channel. A transparent edge would come out black, so anything
    # not fully opaque is composited onto white first — the artwork is opaque, and
    # this only matters if a future master is not.
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        if image.getchannel("A").getextrema()[0] < 255:
            print("  note: partial transparency found, flattening onto white")
            flat = Image.new("RGBA", image.size, (255, 255, 255, 255))
            image = Image.alpha_composite(flat, image)
        image = image.convert("RGB")

    out = FRONTEND_ASSETS / "hero-landscape.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        out,
        format="JPEG",
        quality=QUALITY,
        optimize=True,
        progressive=True,
        # No EXIF, no colour profile, nothing carried over from wherever it was made.
        exif=b"",
        icc_profile=None,
    )
    print(f"  wrote       {out.relative_to(ROOT.parent)}  {out.stat().st_size // 1024} KB")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE))
