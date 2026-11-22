"""Animated intro: two thin rings draw themselves, slide together into the
Twin Rings logo, and the DupeSort title and credit fade in. Monochrome, to
match the rest of the app.

``paint_intro`` draws one frame for time ``t`` in 0..1, so the same animation
plays at start-up (``IntroWindow``) and can be rendered to a video file
(packaging/render_intro.py).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .. import APP_NAME, AUTHOR

DURATION_MS = 3600
BG, FG, MUTED = QColor(10, 10, 10), QColor(255, 255, 255), QColor(143, 143, 140)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _seg(t: float, a: float, b: float) -> float:
    """Progress 0..1 of ``t`` through the window [a, b]."""
    return _clamp((t - a) / (b - a))


def _ease_out(x: float) -> float:
    return 1 - (1 - x) ** 3


def _ease_in_out(x: float) -> float:
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def _back_out(x: float) -> float:  # slight overshoot, like a gentle bounce
    c = 1.70158
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def paint_intro(p: QPainter, w: int, h: int, t: float) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    unit = min(w, h / 0.62) / 1000  # layout units, scales with the frame
    p.fillRect(QRectF(0, 0, w, h), BG)
    fade_out = 1 - _seg(t, 0.9, 1.0)

    # Each ring draws itself like a pen stroke, while the pair slides together,
    # then rises a little to make room for the title.
    draw = _ease_in_out(_seg(t, 0.02, 0.36))
    slide = _ease_out(_seg(t, 0.12, 0.46))
    rise = _ease_in_out(_seg(t, 0.52, 0.72))
    r = (150 - 40 * rise) * unit
    cy = h * (0.5 - 0.12 * rise)
    gap = r * 0.56  # final distance of each centre from the middle (as in the logo)
    start = r * 1.25
    ox = start + (gap - start) * slide
    left, right = QPointF(w / 2 - ox, cy), QPointF(w / 2 + ox, cy)
    stroke = max(1.0, 9 * unit)

    # The overlap ("the duplicate") glows softly once, then settles.
    lens_a = _seg(t, 0.4, 0.5) * (1 - _seg(t, 0.5, 0.75)) * fade_out
    if lens_a > 0:
        a, b = QPainterPath(), QPainterPath()
        a.addEllipse(left, r, r)
        b.addEllipse(right, r, r)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, int(70 * lens_a)))
        p.drawPath(a.intersected(b))

    ring = QColor(FG)
    ring.setAlpha(int(255 * fade_out))
    p.setPen(QPen(ring, stroke, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    span = int(-360 * 16 * draw)
    if span:
        p.drawArc(QRectF(left.x() - r, cy - r, 2 * r, 2 * r), 90 * 16, span)
        p.drawArc(QRectF(right.x() - r, cy - r, 2 * r, 2 * r), 270 * 16, span)

    # Title, tagline and credit rise and fade in, one after another.
    def text(s: str, size: float, weight: int, y: float, start_t: float, color: QColor,
             spacing: float = 0) -> None:
        k = _ease_out(_seg(t, start_t, start_t + 0.16))
        if k <= 0:
            return
        f = QFont()
        f.setPixelSize(max(1, int(size * unit)))
        f.setWeight(QFont.Weight(weight))
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing * unit)
        p.setFont(f)
        c = QColor(color)
        c.setAlpha(int(255 * k * fade_out))
        p.setPen(c)
        rect = QRectF(0, y + (1 - k) * 16 * unit, w, size * unit * 1.5)
        p.drawText(rect, Qt.AlignHCenter | Qt.AlignTop, s)

    base = cy + r + 44 * unit
    text(APP_NAME, 84, 300, base, 0.58, FG, 1)
    text("FIND DUPLICATES. KEEP THE BEST.", 20, 500, base + 118 * unit, 0.66, MUTED, 5)
    text(f"by {AUTHOR}", 20, 400, base + 160 * unit, 0.74, MUTED, 1)


class IntroWindow(QWidget):
    """Frameless start-up animation; click or press any key to skip."""

    finished = Signal()

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(760, 470)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        self.clock = QElapsedTimer()
        self.timer = QTimer(self, interval=16)
        self.timer.timeout.connect(self._tick)
        self._done = False

    def start(self) -> None:
        self.show()
        self.clock.start()
        self.timer.start()

    def progress(self) -> float:
        return self.clock.elapsed() / DURATION_MS if self.clock.isValid() else 0.0

    def _tick(self) -> None:
        if self.progress() >= 1:
            self.finish()
        else:
            self.update()

    def finish(self) -> None:
        if self._done:
            return
        self._done = True
        self.timer.stop()
        self.finished.emit()
        self.close()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        paint_intro(p, self.width(), self.height(), min(1.0, self.progress()))
        f = QFont()
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(QColor(143, 143, 140, 140))
        p.drawText(self.rect().adjusted(0, 0, -12, -8), Qt.AlignRight | Qt.AlignBottom,
                   "Click to skip")
        p.end()

    def mousePressEvent(self, _event) -> None:
        self.finish()

    def keyPressEvent(self, _event) -> None:
        self.finish()
