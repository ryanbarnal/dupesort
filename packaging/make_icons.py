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
    """The app icon is logo 2, "Twin Circles" (see logos.py for all six designs)."""
    sys.path.insert(0, str(OUT))
    from logos import draw as draw_logo

    return draw_logo(2)


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
