#!/usr/bin/env python3
"""Render Phase 1 Quiet Luxury favicon ladder, ICO, and OG card from locked SVGs."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from urllib.request import urlopen

import cairosvg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
BRAND = PUBLIC / "brand"
FAVICON_SVG = BRAND / "favicon.svg"
MARK_SVG = BRAND / "mark.svg"

CREAM = (245, 241, 233, 255)
GOLD = (170, 139, 84, 255)
INK = (0, 0, 0, 255)

PLAYFAIR_URL = (
    "https://github.com/google/fonts/raw/main/ofl/playfairdisplay/"
    "PlayfairDisplay%5Bwght%5D.ttf"
)
PLAYFAIR_FALLBACK = (
    "https://github.com/google/fonts/raw/main/ofl/playfairdisplay/"
    "PlayfairDisplay-Regular.ttf"
)


def svg_png(svg_path: Path, size: int) -> Image.Image:
    data = cairosvg.svg2png(
        url=str(svg_path),
        output_width=size,
        output_height=size,
    )
    return Image.open(io.BytesIO(data)).convert("RGBA")


def write_png(img: Image.Image, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="PNG", optimize=True)


def load_playfair(size: int) -> ImageFont.FreeTypeFont:
    cache = ROOT / ".cache" / "PlayfairDisplay.ttf"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        for url in (PLAYFAIR_FALLBACK, PLAYFAIR_URL):
            try:
                with urlopen(url, timeout=30) as resp:
                    payload = resp.read()
                if payload[:4] == b"PK\x03\x04":
                    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                        ttf = next(n for n in zf.namelist() if n.endswith(".ttf"))
                        payload = zf.read(ttf)
                cache.write_bytes(payload)
                break
            except Exception:
                continue
        if not cache.exists():
            raise RuntimeError("Could not download Playfair Display")
    return ImageFont.truetype(str(cache), size=size)


def render_favicon_ladder() -> None:
    sizes = {
        PUBLIC / "favicon-16.png": 16,
        PUBLIC / "favicon-32.png": 32,
        PUBLIC / "favicon-48.png": 48,
        PUBLIC / "favicon-64.png": 64,
        PUBLIC / "apple-touch-icon.png": 180,
        PUBLIC / "favicon-512.png": 512,
    }
    for dest, size in sizes.items():
        write_png(svg_png(FAVICON_SVG, size), dest)

    ico_images = [svg_png(FAVICON_SVG, s) for s in (16, 32, 48)]
    ico_images[0].save(
        PUBLIC / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=ico_images[1:],
    )

    # Root SVG copy stays byte-identical to the canonical favicon-weight mark.
    (PUBLIC / "favicon.svg").write_bytes(FAVICON_SVG.read_bytes())


def render_og() -> None:
    width, height = 1200, 630
    canvas = Image.new("RGBA", (width, height), CREAM)
    draw = ImageDraw.Draw(canvas)

    lockup = svg_png(MARK_SVG, 72)
    canvas.alpha_composite(lockup, (72, 78))
    word = load_playfair(54)
    draw.text((158, 88), "Magic Table Finder", font=word, fill=INK)

    display = load_playfair(42)
    draw.text((80, 250), "Magic Table Finder", font=display, fill=INK)
    sub = load_playfair(26)
    draw.text((80, 318), "Walt Disney World dining alerts — quietly.", font=sub, fill=INK)

    footer = load_playfair(20)
    draw.text((80, 548), "magictablefinder.com", font=footer, fill=GOLD)
    draw.text((420, 548), "@magictablefinder_ig", font=footer, fill=GOLD)

    hero = svg_png(MARK_SVG, 420)
    canvas.alpha_composite(hero, (740, 90))

    write_png(canvas.convert("RGBA"), PUBLIC / "og-1200x630.png")


def main() -> None:
    if not FAVICON_SVG.exists() or not MARK_SVG.exists():
        raise SystemExit("canonical brand SVGs missing")
    render_favicon_ladder()
    render_og()
    print("wrote favicon ladder, favicon.ico, favicon.svg, og-1200x630.png")


if __name__ == "__main__":
    main()
