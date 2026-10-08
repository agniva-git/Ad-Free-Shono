#!/usr/bin/env python3
"""Generates the app icons (a plain cassette). Needs Pillow:  pip install pillow"""
from pathlib import Path
from PIL import Image, ImageDraw

BG, FG = (18, 18, 18), (226, 178, 74)
OUT = Path(__file__).resolve().parent.parent / "frontend" / "assets"


def draw(size: int) -> Image.Image:
    s = 512  # draw large, then shrink for clean edges
    img = Image.new("RGB", (s, s), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([56, 120, 456, 392], outline=FG, width=14)          # cassette body
    d.rectangle([116, 168, 396, 264], outline=FG, width=10)         # tape window
    for cx in (186, 326):                                           # reels
        d.ellipse([cx - 34, 190, cx + 34, 258], outline=FG, width=10)
    d.polygon([(116, 392), (146, 330), (366, 330), (396, 392)], outline=FG, width=10)  # bottom plate
    d.rectangle([216, 352, 296, 368], fill=FG)
    return img.resize((size, size), Image.LANCZOS) if size != s else img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        draw(size).save(OUT / f"icon-{size}.png")
        print(f"wrote icon-{size}.png")
