"""Render the start-up animation to a video, e.g. for a website or social media.

    python packaging/render_intro.py            # -> dist/DupeSort-intro.mp4 (1920x1080, 60 fps)
    python packaging/render_intro.py --vertical # -> dist/DupeSort-intro-vertical.mp4 (1080x1920)
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402

from dupesort.gui.intro import DURATION_MS, paint_intro  # noqa: E402
from dupesort.tools import find_tool  # noqa: E402


def main() -> None:
    vertical = "--vertical" in sys.argv
    w, h = (1080, 1920) if vertical else (1920, 1080)
    fps = 60
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        sys.exit("FFmpeg is needed (put it in ./bin or on PATH).")
    app = QGuiApplication(sys.argv)  # noqa: F841 - fonts need an application
    out = ROOT / "dist" / ("DupeSort-intro-vertical.mp4" if vertical else "DupeSort-intro.mp4")
    out.parent.mkdir(exist_ok=True)
    proc = subprocess.Popen([ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra",
                             "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-c:v", "libx264",
                             "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "slow",
                             "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    frames = int(DURATION_MS / 1000 * fps)
    img = QImage(w, h, QImage.Format_ARGB32)
    for i in range(frames + 1):
        p = QPainter(img)
        paint_intro(p, w, h, i / frames)
        p.end()
        proc.stdin.write(bytes(img.constBits()))
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("FFmpeg failed")
    print("Wrote", out)


if __name__ == "__main__":
    main()
