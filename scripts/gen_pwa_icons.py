#!/usr/bin/env python3
"""Generate the kleeblatt.space PWA icons: a green clover (3-lobed shamrock)
on transparent / white backgrounds, at the sizes the app references.

Brand: #2FBF71 (clover green) — see landing.html theme-color. "kleeblatt"
is German for clover, so a clover leaf is the obvious mark.

Sizes produced:
  icon-192.png       512-maskable-safe render (manifest "any maskable")
  icon-512.png       same, large
  icon-72.png        small badge (referenced by sw.js push `badge`)
  apple-touch-icon.png  180x180 on white rounded bg (iOS home screen)
"""
import math
import os
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(__file__), "..", "app", "api", "static", "icons")
OUT = os.path.abspath(OUT)
os.makedirs(OUT, exist_ok=True)

GREEN = (47, 191, 113)      # #2FBF71
GREEN_DARK = (36, 160, 94)  # subtle shade for depth
WHITE = (255, 255, 255)
TRANSPARENT = (0, 0, 0, 0)


def draw_clover(size: int, bg=None, pad: float = 0.18):
    """Draw a 3-lobed clover centered, leaving `pad` margin (maskable-safe).

    bg: None = transparent, else an RGB(A) tuple.
    """
    img = Image.new("RGBA", (size, size), bg if bg else TRANSPARENT)
    d = ImageDraw.Draw(img)

    # Work in a square inset by `pad`; lobes arranged around a center.
    inset = size * pad
    lo, hi = inset, size - inset
    cx, cy = size / 2, size / 2
    radius = (hi - lo) / 2 * 0.62  # lobe radius
    arm = (hi - lo) / 2 * 0.52     # distance from center to each lobe

    # Three lobes at 90° (top), 210°, 330° -> classic shamrock
    angles = [-90, 30, 150]
    for a in angles:
        rad = math.radians(a)
        lx = cx + arm * math.cos(rad)
        ly = cy + arm * math.sin(rad)
        # soft two-tone: darker base ellipse, lighter overlay for a little depth
        d.ellipse(
            [lx - radius, ly - radius, lx + radius, ly + radius],
            fill=GREEN_DARK,
        )
        r2 = radius * 0.86
        d.ellipse(
            [lx - r2, ly - r2, lx + r2, ly + r2],
            fill=GREEN,
        )

    # Stem: a short rounded line from center downward
    stem_w = max(2, int(radius * 0.30))
    stem_top = cy + arm * 0.15
    stem_bottom = hi - size * 0.02
    d.line([cx, stem_top, cx, stem_bottom], fill=GREEN_DARK, width=stem_w)
    d.ellipse(
        [cx - stem_w / 2, stem_bottom - stem_w / 2,
         cx + stem_w / 2, stem_bottom + stem_w / 2],
        fill=GREEN_DARK,
    )
    return img


def rounded_white(size: int):
    img = Image.new("RGBA", (size, size), TRANSPARENT)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size, size], radius=size * 0.22, fill=WHITE)
    return img


def main():
    # Manifest icons (maskable-safe margins already built in)
    draw_clover(192).save(os.path.join(OUT, "icon-192.png"))
    draw_clover(512).save(os.path.join(OUT, "icon-512.png"))
    draw_clover(72).save(os.path.join(OUT, "icon-72.png"))
    # iOS apple-touch-icon: clover on white rounded tile
    tile = rounded_white(180)
    clover = draw_clover(180, pad=0.16)
    tile.alpha_composite(clover)
    tile.convert("RGB").save(os.path.join(OUT, "apple-touch-icon.png"))
    print("wrote:", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
