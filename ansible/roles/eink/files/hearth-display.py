#!/usr/bin/env python3
"""
hearth-display.py — Render the Hearth boot screen on a Pimoroni Inky e-ink display.

Draws a flame icon, the box name, and the access domain in landscape orientation
on the 212×104 Inky pHAT. Uses inky.auto() to detect the attached display via
the HAT EEPROM over I2C — no model configuration required.

Configuration is read from environment variables set by the systemd unit:
  HEARTH_NAME    — Box name shown on screen  (default: Hearth)
  HEARTH_DOMAIN  — Domain shown on screen    (default: hearth.local)
"""

import os

from inky.auto import auto
from PIL import Image, ImageDraw, ImageFont

NAME   = os.environ.get("HEARTH_NAME",   "Hearth")
DOMAIN = os.environ.get("HEARTH_DOMAIN", "hearth.local")

FONT_BOLD   = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_NORMAL = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def load_fonts(size_large=16, size_small=11):
    try:
        return (
            ImageFont.truetype(FONT_BOLD,   size_large),
            ImageFont.truetype(FONT_NORMAL, size_small),
        )
    except OSError:
        f = ImageFont.load_default()
        return f, f


def draw_flame(draw, cx, cy, w, h, black):
    """Draw a stylised flame centred at (cx, cy) in a w × h bounding box."""
    hw, hh = w // 2, h // 2

    # Outer flame body
    outer = [
        (cx,        cy - hh),           # tip
        (cx + hw,   cy - hh // 3),      # upper-right shoulder
        (cx + hw,   cy + hh // 2),      # lower-right
        (cx,        cy + hh),           # base centre
        (cx - hw,   cy + hh // 2),      # lower-left
        (cx - hw,   cy - hh // 3),      # upper-left shoulder
    ]
    draw.polygon(outer, fill=black)

    # Inner teardrop highlight (white cutout for depth)
    iw, ih = w // 4, h // 3
    inner = [
        (cx,        cy - hh + ih // 2),
        (cx + iw,   cy + ih // 2),
        (cx - iw,   cy + ih // 2),
    ]
    draw.polygon(inner, fill=0)  # Inky WHITE is always palette index 0


def main():
    inky = auto(ask_user=False, verbose=False)

    W, H = inky.WIDTH, inky.HEIGHT   # 212 × 104 for Inky pHAT
    BLACK = inky.BLACK               # palette index for black
    WHITE = inky.WHITE               # palette index for white (0)

    img  = Image.new("P", (W, H), WHITE)
    draw = ImageDraw.Draw(img)

    font_large, font_small = load_fonts()

    # --- Flame icon — left quarter ------------------------------------------
    # Icon area: 0..H wide square, centred vertically
    icon_area = H
    flame_cx  = icon_area // 2
    flame_cy  = H // 2
    flame_w   = icon_area * 2 // 5
    flame_h   = H * 3 // 5
    draw_flame(draw, flame_cx, flame_cy, flame_w, flame_h, BLACK)

    # --- Vertical rule -------------------------------------------------------
    div_x = icon_area + 6
    draw.line([(div_x, 8), (div_x, H - 8)], fill=BLACK, width=1)

    # --- Box name and domain — right of the rule ----------------------------
    text_x  = div_x + 10
    name_y  = H // 2 - 14
    domain_y = H // 2 + 6

    draw.text((text_x, name_y),   NAME,   font=font_large, fill=BLACK)
    draw.text((text_x, domain_y), DOMAIN, font=font_small, fill=BLACK)

    inky.set_image(img)
    inky.show()


if __name__ == "__main__":
    main()
