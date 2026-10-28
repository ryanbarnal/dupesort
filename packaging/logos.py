"""The six DupeSort logo designs, drawn with Pillow so they stay editable.

    python packaging/logos.py           # writes packaging/logos/logo<N>.png + sheet.png
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

S = 1024
OUT = Path(__file__).resolve().parent / "logos"

NAMES = {
    1: "Stacked Cards",
    2: "Twin Circles",
    3: "Mirror D",
    4: "Media Grid",
    5: "Magnifier",
    6: "Tidy Folder",
}


def _gradient(top, bottom, size=S) -> Image.Image:
    g = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(g)
    for y in range(size):
        t = y / (size - 1)
        d.line([(0, y), (size, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return g


def _tile(top, bottom, radius=220) -> Image.Image:
    """Rounded-square app-icon background with a vertical gradient."""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=radius, fill=255)
    img.paste(_gradient(top, bottom), (0, 0), mask)
    return img


def _over(img: Image.Image, draw_fn) -> Image.Image:
    """Draw on a transparent layer and alpha-composite it (so alpha blends)."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    return Image.alpha_composite(img, layer)


def _check(d: ImageDraw.ImageDraw, cx, cy, r, fill=(16, 185, 129)) -> None:
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=(255, 255, 255), width=r // 5)
    k = r / 130
    d.line([(cx - 70 * k, cy + 5 * k), (cx - 15 * k, cy + 60 * k), (cx + 75 * k, cy - 50 * k)],
           fill=(255, 255, 255), width=int(40 * k), joint="curve")


def _note(d, x, y, s, fill):
    """A simple eighth note with its stem top-left at (x, y)."""
    d.ellipse([x - 0.55 * s, y + 0.75 * s, x + 0.05 * s, y + 1.15 * s], fill=fill)
    d.rectangle([x - 0.06 * s, y, x + 0.05 * s, y + 0.95 * s], fill=fill)
    d.polygon([(x, y), (x + 0.45 * s, y + 0.25 * s), (x + 0.45 * s, y + 0.45 * s),
               (x, y + 0.2 * s)], fill=fill)


def logo1() -> Image.Image:
    """Stacked Cards: the kept original in front of a faded duplicate."""
    img = _tile((79, 70, 229), (13, 148, 136))
    img = _over(img, lambda d: d.rounded_rectangle([320, 200, 780, 720], 60,
                                                   fill=(255, 255, 255, 120)))
    img = _over(img, lambda d: d.rounded_rectangle([238, 316, 698, 836], 60, fill=(0, 0, 0, 60)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([230, 300, 690, 820], 60, fill="white")
    for i, w in enumerate((300, 340, 240)):
        d.rounded_rectangle([300, 400 + i * 80, 300 + w, 436 + i * 80], 18, fill=(199, 210, 254))
    _check(d, 690, 730, 130)
    return img


def logo2() -> Image.Image:
    """Twin Circles: two overlapping copies, the overlap is what gets sorted out."""
    img = _tile((15, 23, 42), (30, 41, 59))
    img = _over(img, lambda d: d.ellipse([170, 262, 670, 762], fill=(56, 189, 248, 230)))
    img = _over(img, lambda d: d.ellipse([354, 262, 854, 762], fill=(244, 114, 182, 200)))
    # Highlight the lens-shaped overlap in white.
    lens = Image.new("L", (S, S), 0)
    a = Image.new("L", (S, S), 0)
    ImageDraw.Draw(a).ellipse([170, 262, 670, 762], fill=255)
    b = Image.new("L", (S, S), 0)
    ImageDraw.Draw(b).ellipse([354, 262, 854, 762], fill=255)
    lens.paste(b, (0, 0), a)
    white = Image.new("RGBA", (S, S), (255, 255, 255, 255))
    img.paste(white, (0, 0), lens)
    return img


def logo3() -> Image.Image:
    """Mirror D: a bold D monogram with its duplicate echo behind it."""
    img = _tile((249, 115, 22), (225, 29, 72))

    def d_shape(d, dx, fill):
        d.rounded_rectangle([300 + dx, 250, 420 + dx, 780], 30, fill=fill)
        d.pieslice([140 + dx, 250, 730 + dx, 780], -90, 90, fill=fill)
        d.rectangle([300 + dx, 250, 435 + dx, 780], fill=fill)
        # Counter (hole) of the D.
        d.pieslice([290 + dx, 380, 600 + dx, 650], -90, 90, fill=(0, 0, 0, 0))
        d.rectangle([420 + dx, 380, 445 + dx, 650], fill=(0, 0, 0, 0))

    # The front D's hole, used to keep the echo from showing through it.
    hole = Image.new("L", (S, S), 0)
    hd = ImageDraw.Draw(hole)
    hd.pieslice([290, 380, 600, 650], -90, 90, fill=255)
    hd.rectangle([420, 380, 445, 650], fill=255)
    zero = Image.new("L", (S, S), 0)

    echo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d_shape(ImageDraw.Draw(echo), 70, (255, 255, 255, 90))
    echo.putalpha(Image.composite(zero, echo.getchannel("A"), hole))
    img = Image.alpha_composite(img, echo)
    front = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d_shape(ImageDraw.Draw(front), 0, (255, 255, 255, 255))
    front.putalpha(Image.composite(zero, front.getchannel("A"), hole))
    return Image.alpha_composite(img, front)


def logo4() -> Image.Image:
    """Media Grid: music, photo, video and document tiles - one ticked as kept."""
    img = _tile((99, 102, 241), (168, 85, 247))
    d = ImageDraw.Draw(img)
    boxes = [(200, 200), (532, 200), (200, 532), (532, 532)]
    for x, y in boxes:
        d.rounded_rectangle([x, y, x + 292, y + 292], 56, fill=(255, 255, 255, 255))
    ink = (99, 102, 241)
    _note(d, 360, 255, 170, ink)                                    # music
    d.polygon([(600, 440), (680, 330), (760, 440)], fill=ink)         # photo: mountains
    d.polygon([(660, 440), (720, 370), (780, 440)], fill=(168, 85, 247))
    d.ellipse([700, 255, 750, 305], fill=(250, 204, 21))
    d.polygon([(310, 600), (310, 760), (430, 680)], fill=ink)         # video: play
    for i, w in enumerate((170, 200, 130)):                           # document lines
        d.rounded_rectangle([590, 610 + i * 50, 590 + w, 634 + i * 50], 12, fill=ink)
    _check(d, 790, 790, 105)
    return img


def logo5() -> Image.Image:
    """Magnifier: a lens finding the matching pair."""
    img = _tile((14, 165, 233), (37, 99, 235))
    d = ImageDraw.Draw(img)
    for x, y, a in ((210, 250, 255), (420, 250, 255), (210, 470, 120), (420, 470, 120)):
        d.rounded_rectangle([x, y, x + 170, y + 170], 34, fill=(255, 255, 255, a))
    img = _over(img, lambda dd: dd.ellipse([330, 330, 760, 760], fill=(255, 255, 255, 70)))
    d = ImageDraw.Draw(img)
    d.ellipse([330, 330, 760, 760], outline="white", width=56)
    d.line([(705, 705), (850, 850)], fill="white", width=90)
    d.ellipse([805, 805, 895, 895], fill="white")
    _check(d, 545, 545, 95, fill=(34, 197, 94))
    return img


def logo6() -> Image.Image:
    """Tidy Folder: a folder with a sparkle - everything in its place."""
    img = _tile((16, 185, 129), (5, 150, 105))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([190, 300, 500, 420], 40, fill=(255, 237, 213))
    d.rounded_rectangle([190, 360, 834, 780], 60, fill=(255, 237, 213))
    d.rounded_rectangle([190, 430, 834, 780], 60, fill="white")
    for i in range(3):
        d.rounded_rectangle([280, 520 + i * 70, 740 - i * 90, 552 + i * 70], 16, fill=(16, 185, 129))

    def star(cx, cy, r, fill):
        pts = []
        for k in range(8):
            ang = math.pi / 4 * k - math.pi / 2
            rad = r if k % 2 == 0 else r * 0.32
            pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        d.polygon(pts, fill=fill)

    star(760, 250, 120, (250, 204, 21))
    star(640, 180, 55, (255, 255, 255))
    return img


LOGOS = {1: logo1, 2: logo2, 3: logo3, 4: logo4, 5: logo5, 6: logo6}


def draw(n: int) -> Image.Image:
    return LOGOS[n]()


def sheet() -> Image.Image:
    cell, pad = 300, 40
    w, h = 3 * cell + 4 * pad, 2 * (cell + 60) + 3 * pad
    out = Image.new("RGB", (w, h), (245, 245, 247))
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)
    except OSError:
        font = ImageFont.load_default()
    for i, n in enumerate(LOGOS):
        x = pad + (i % 3) * (cell + pad)
        y = pad + (i // 3) * (cell + 60 + pad)
        out.paste(draw(n).resize((cell, cell), Image.LANCZOS), (x, y), draw(n).resize((cell, cell)))
        label = f"{n}. {NAMES[n]}"
        tw = d.textlength(label, font=font)
        d.text((x + (cell - tw) / 2, y + cell + 14), label, fill=(30, 30, 35), font=font)
    return out


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for n in LOGOS:
        draw(n).save(OUT / f"logo{n}.png")
    sheet().save(OUT / "sheet.png")
    print("Wrote", OUT)
