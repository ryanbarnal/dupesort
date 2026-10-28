"""Draw the DupeSort icon and write icon.png, icon.ico (Windows) and, on macOS, icon.icns.

Run from the project root:  python packaging/make_icons.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
S = 1024


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # Rounded-square background with a vertical gradient (indigo -> teal).
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    top, bottom = (79, 70, 229), (13, 148, 136)
    for y in range(S):
        t = y / (S - 1)
        gd.line([(0, y), (S, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=220, fill=255)
    img.paste(grad, (0, 0), mask)

    # Back card (the duplicate), faded and offset; composited so it blends.
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle([320, 200, 780, 720], radius=60,
                                            fill=(255, 255, 255, 120))
    img = Image.alpha_composite(img, layer)
    # Soft shadow, then the front card (the kept original).
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle([238, 316, 698, 836], radius=60, fill=(0, 0, 0, 60))
    img = Image.alpha_composite(img, layer)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([230, 300, 690, 820], radius=60, fill=(255, 255, 255, 255))
    for i, w in enumerate((300, 340, 240)):
        y = 400 + i * 80
        d.rounded_rectangle([300, y, 300 + w, y + 36], radius=18, fill=(199, 210, 254))
    # Check badge.
    d.ellipse([560, 600, 820, 860], fill=(16, 185, 129), outline=(255, 255, 255), width=24)
    d.line([(620, 735), (675, 790), (765, 680)], fill=(255, 255, 255), width=40, joint="curve")
    return img


def main() -> None:
    img = draw()
    img.save(OUT / "icon.png")
    img.save(OUT / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    if sys.platform == "darwin" and shutil.which("iconutil"):
        iconset = OUT / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        for s in (16, 32, 128, 256, 512):
            img.resize((s, s), Image.LANCZOS).save(iconset / f"icon_{s}x{s}.png")
            img.resize((s * 2, s * 2), Image.LANCZOS).save(iconset / f"icon_{s}x{s}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT / "icon.icns")],
                       check=True)
        shutil.rmtree(iconset)
    print("Icons written to", OUT)


if __name__ == "__main__":
    main()
