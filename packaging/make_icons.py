"""Draw the DupeSort icon and write icon.png, icon.ico (Windows) and, on macOS, icon.icns.

Run from the project root:  python packaging/make_icons.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent
S = 1024


def draw() -> Image.Image:
    """The app icon is logo 7, "Twin Rings" (see logos.py for all the designs)."""
    sys.path.insert(0, str(OUT))
    from logos import draw as draw_logo

    return draw_logo(7)


def main() -> None:
    img = draw()
    img.save(OUT / "icon.png")
    img.save(OUT / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    img.resize((512, 512), Image.LANCZOS).save(OUT.parent / "dupesort" / "gui" / "logo.png")
    if sys.platform != "darwin" or not shutil.which("iconutil"):
        img.save(OUT / "icon.icns")  # Pillow can write .icns too
    else:
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
