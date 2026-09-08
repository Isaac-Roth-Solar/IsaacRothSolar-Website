#!/usr/bin/env python3
"""Render the 1200x630 social share cards in assets/og/.

Every unfurler (Facebook, LinkedIn, X, Slack, iMessage) crops to roughly
1.91:1, so the cards are authored at exactly 1200x630 rather than letting a
scraper crop a 4:3 photo. JPEG, not WebP: LinkedIn's scraper has never been
reliable with WebP.

Run from the repo root:

    pip install Pillow cairosvg
    python3 .github/scripts/make-og-images.py

Fonts come from Google Fonts (the same Antonio/Archivo the site loads) and are
downloaded to a cache dir on first run, so this is reproducible on a clean
checkout without vendoring font binaries into the repo.

It lives under .github/ because the FTP deploy publishes the repository root
verbatim and already excludes .git* paths -- a build script in tools/ would be
uploaded to the docroot.
"""

import os
import re
import sys
import urllib.request

import cairosvg
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630

# assets/logo + colors_and_type.css
MOSS_900 = (0x0F, 0x1F, 0x0C)
MOSS_700 = (0x1F, 0x33, 0x19)
MOSS_500 = (0x3E, 0x62, 0x33)
MOSS_200 = (0xB6, 0xC8, 0xAC)
SUN_400 = (0xFF, 0xB9, 0x27)
CREAM_50 = (0xFB, 0xF7, 0xF0)
CREAM_300 = (0xD6, 0xCB, 0xB6)

PAD_X = 68
PHOTO_X = 648          # left edge of the photo panel
BLEND = 265            # width of the photo's fade into the green field


def smoothstep(t):
    """Ease in and out. A linear ramp leaves a visible edge where it clamps."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

FONTS = {
    "display": ("Antonio-Bold.ttf",
                "https://fonts.gstatic.com/s/antonio/v22/"
                "gNMbW3NwSYq_9WD34ngK5F8vR8T0PVyW9htI.ttf"),
    "sans": ("Archivo-Bold.ttf",
             "https://fonts.gstatic.com/s/archivo/v25/"
             "k3k6o8UDI-1M0wlSV9XAw6lQkqWY8Q82sJaRE-NWIDdgffTT0zRp8A.ttf"),
    "italic": ("Archivo-Italic.ttf",
               "https://fonts.gstatic.com/s/archivo/v25/"
               "k3k8o8UDI-1M0wlSfdzyIEkpwTM29hr-8mTYIRyOSVz60_PG_HBmtBds.ttf"),
}

CACHE = os.environ.get("OG_FONT_CACHE", os.path.expanduser("~/.cache/irs-og-fonts"))

# Stat row. Every value here is a claim the site itself makes: "200+ installs
# and counting" (about), "Independent Solar Consultant" (schema jobTitle), and
# the services FAQ answering that the consultation is free. Nothing invented --
# in particular no aggregate star rating, which the site has no basis for.
STATS = [
    ("200+", "EAST BAY INSTALLS"),
    ("Independent", "SOLAR CONSULTANT"),
    ("Free", "SITE VISIT"),
]

# Headlines are the pages' own <h1> copy; *stars* mark the same words the
# markup emphasises with <em>.
CARDS = {
    "og-home.jpg": {
        "lines": ["OAKLAND", "RAISED.", "*Honest* SOLAR", "GUIDANCE."],
        "photo": "assets/photos/isaac-lake-merritt-1600.webp",
        "focus": 0.42,
    },
    "og-services.jpg": {
        "lines": ["SOLAR", "GUIDANCE FROM", "*start to finish.*"],
        "photo": "assets/photos/install-tudor-maple-1120.webp",
        "focus": 0.5,
    },
    "og-about.jpg": {
        "lines": ["I'M *ISAAC.*", "I GREW UP IN", "OAKLAND."],
        "photo": "assets/photos/isaac-portrait-900.webp",
        "focus": 0.45,
    },
    "og-default.jpg": {"lines": None, "photo": None, "focus": 0},
}


def font_path(kind):
    name, url = FONTS[kind]
    os.makedirs(CACHE, exist_ok=True)
    dest = os.path.join(CACHE, name)
    if not os.path.exists(dest):
        print("  fetching %s" % name)
        urllib.request.urlretrieve(url, dest)
    return dest


def font(kind, size):
    return ImageFont.truetype(font_path(kind), size)


def tracked(draw, xy, text, fnt, fill, tracking=0.0):
    """Draw text with letter spacing; returns the advance width."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + tracking
    return x - tracking - xy[0]


def tracked_width(draw, text, fnt, tracking=0.0):
    return sum(draw.textlength(c, font=fnt) for c in text) + tracking * (len(text) - 1)


def cover(img, box_w, box_h, focus=0.5):
    """Scale to fill box_w x box_h and crop, keeping `focus` of the width."""
    scale = max(box_w / img.width, box_h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)),
                     Image.LANCZOS)
    left = max(0, min(img.width - box_w, round((img.width - box_w) * focus)))
    top = max(0, min(img.height - box_h, round((img.height - box_h) * 0.35)))
    return img.crop((left, top, left + box_w, top + box_h))


def field():
    """The moss background, lightly graded so it isn't a flat slab."""
    base = Image.new("RGB", (W, H), MOSS_700)
    grad = Image.new("L", (W, 1))
    for x in range(W):
        grad.putpixel((x, 0), int(150 * (x / W) ** 1.4))
    grad = grad.resize((W, H))
    return Image.composite(Image.new("RGB", (W, H), MOSS_900), base, grad)


def place_photo(canvas, path, focus):
    photo = Image.open(path).convert("RGB")
    panel_w = W - PHOTO_X
    photo = cover(photo, panel_w, H, focus)

    # Fade the photo's left edge into the field instead of butting a hard seam.
    mask = Image.new("L", (panel_w, 1))
    for x in range(panel_w):
        mask.putpixel((x, 0), round(255 * smoothstep(x / BLEND)))
    canvas.paste(photo, (PHOTO_X, 0), mask.resize((panel_w, H)))

    # Green wash over the blend zone so headline counters stay readable if a
    # bright part of the photo lands near the text column. It has to fade out
    # over a wider span than the photo fades in, or its own tail becomes the
    # seam it was meant to hide.
    wash = Image.new("RGB", (panel_w, H), MOSS_700)
    wmask = Image.new("L", (panel_w, 1))
    for x in range(panel_w):
        wmask.putpixel((x, 0), round(110 * smoothstep(1 - x / (BLEND * 1.8))))
    canvas.paste(wash, (PHOTO_X, 0), wmask.resize((panel_w, H)))


def header(canvas, draw, centered=False):
    mark_px = 48
    png = cairosvg.svg2png(url="assets/logo/sun-mark.svg",
                           output_width=mark_px * 2, output_height=mark_px * 2)
    import io
    mark = Image.open(io.BytesIO(png)).convert("RGBA").resize(
        (mark_px, mark_px), Image.LANCZOS)

    name_f = font("display", 35)
    tag_f = font("sans", 15)
    name, tag = "ISAAC ROTH SOLAR", "OAKLAND · EAST BAY"
    name_w = tracked_width(draw, name, name_f, 4.5)
    tag_w = tracked_width(draw, tag, tag_f, 2.6)
    total = mark_px + 20 + name_w + 26 + 1 + 26 + tag_w

    x = (W - total) / 2 if centered else PAD_X
    y = 72
    canvas.paste(mark, (round(x), round(y - 4)), mark)
    x += mark_px + 20
    tracked(draw, (x, y + 2), name, name_f, CREAM_50, 4.5)
    x += name_w + 26
    draw.line([(x, y + 8), (x, y + 34)], fill=MOSS_500, width=2)
    x += 26
    tracked(draw, (x, y + 15), tag, tag_f, MOSS_200, 2.6)


def headline(draw, lines):
    size, leading = 74, 79
    disp, ital = font("display", size), font("italic", round(size * 0.86))
    bottom = 452
    y = bottom - len(lines) * leading
    for line in lines:
        x = PAD_X
        for part in re.split(r"(\*[^*]+\*)", line):
            if not part:
                continue
            if part.startswith("*"):
                txt = part[1:-1]
                draw.text((x, y + size * 0.10), txt, font=ital, fill=SUN_400)
                x += draw.textlength(txt, font=ital)
            else:
                draw.text((x, y), part, font=disp, fill=CREAM_50)
                x += draw.textlength(part, font=disp)
        y += leading


def stats(draw):
    draw.rectangle([PAD_X, 476, PAD_X + 138, 481], fill=SUN_400)
    val_f, lab_f = font("sans", 29), font("sans", 13)
    x = PAD_X
    for value, label in STATS:
        tracked(draw, (x, 506), value, val_f, SUN_400, 0)
        tracked(draw, (x, 545), label, lab_f, CREAM_300, 1.7)
        x += max(draw.textlength(value, font=val_f),
                 tracked_width(draw, label, lab_f, 1.7)) + 46
    tracked(draw, (PAD_X, 578), "ISAACROTHSOLAR.COM", font("sans", 15), MOSS_200, 2.4)


def default_card(canvas, draw):
    """Logo card for the noindex legal pages -- no photo, nothing to crop."""
    header(canvas, draw, centered=True)
    disp = font("display", 70)
    for i, line in enumerate(["OAKLAND RAISED.", "HONEST SOLAR GUIDANCE."]):
        w = draw.textlength(line, font=disp)
        draw.text(((W - w) / 2, 262 + i * 76), line, font=disp, fill=CREAM_50)
    draw.rectangle([(W - 138) / 2, 452, (W + 138) / 2, 457], fill=SUN_400)
    f = font("sans", 15)
    dom = "ISAACROTHSOLAR.COM"
    tracked(draw, ((W - tracked_width(draw, dom, f, 2.4)) / 2, 498), dom, f,
            MOSS_200, 2.4)


def build(name, spec):
    canvas = field()
    if spec["photo"]:
        place_photo(canvas, spec["photo"], spec["focus"])
    draw = ImageDraw.Draw(canvas)
    canvas.paste(Image.new("RGB", (10, H), SUN_400), (0, 0))  # brand edge
    if spec["lines"] is None:
        default_card(canvas, draw)
    else:
        header(canvas, draw)
        headline(draw, spec["lines"])
        stats(draw)
    out = os.path.join("assets/og", name)
    # quality 92 with no chroma subsampling: the gold type sits on dark green,
    # exactly where 4:2:0 smears colour edges.
    canvas.save(out, "JPEG", quality=92, subsampling=0, optimize=True,
                progressive=True)
    print("  %-18s %s  %6.1f KB" % (name, canvas.size, os.path.getsize(out) / 1024))


def main():
    if not os.path.isdir("assets/photos"):
        sys.exit("run this from the repository root")
    os.makedirs("assets/og", exist_ok=True)
    print("rendering share cards:")
    for name, spec in CARDS.items():
        build(name, spec)


if __name__ == "__main__":
    main()
