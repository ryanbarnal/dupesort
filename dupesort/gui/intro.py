"""Animated intro: the Twin Circles slide together, their overlap flashes, and
the DupeSort title and credit appear.

``paint_intro`` draws one frame for time ``t`` in 0..1, so the same animation
plays at start-up (``IntroWindow``) and can be rendered to a video file
(packaging/render_intro.py).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from .. import APP_NAME, AUTHOR

DURATION_MS = 3600
SKY, PINK = QColor(56, 189, 248), QColor(244, 114, 182)


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

    # Background: deep navy gradient (the logo's tile colours) with a soft glow.
    bg = QLinearGradient(0, 0, 0, h)
    bg.setColorAt(0, QColor(15, 23, 42))
    bg.setColorAt(1, QColor(30, 41, 59))
    p.fillRect(QRectF(0, 0, w, h), bg)
    glow_a = _seg(t, 0.3, 0.5) * (1 - _seg(t, 0.85, 1.0))
    if glow_a > 0:
        g = QRadialGradient(QPointF(w / 2, h * 0.42), 420 * unit)
        g.setColorAt(0, QColor(255, 255, 255, int(40 * glow_a)))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(QRectF(0, 0, w, h), g)

    # Circles slide in from the sides, then the pair rises and shrinks a little.
    slide = _ease_out(_seg(t, 0.04, 0.42))
    rise = _ease_in_out(_seg(t, 0.52, 0.72))
    r = (150 - 40 * rise) * unit
    cy = h * (0.5 - 0.12 * rise)
    gap = r * 0.74  # final distance of each centre from the middle
    start = w / 2 + r * 2.2
    ox = start + (gap - start) * slide
    left, right = QPointF(w / 2 - ox, cy), QPointF(w / 2 + ox, cy)
    fade_out = 1 - _seg(t, 0.9, 1.0)
    alpha = int(255 * _seg(t, 0.02, 0.18) * fade_out)

    for centre, col in ((left, SKY), (right, PINK)):
        c = QColor(col)
        c.setAlpha(int(alpha * 0.9))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawEllipse(centre, r, r)

    # The overlap ("the duplicate") lights up white once they meet.
    lens_a = _seg(t, 0.38, 0.48) * fade_out
    if lens_a > 0:
        a, b = QPainterPath(), QPainterPath()
        a.addEllipse(left, r, r)
        b.addEllipse(right, r, r)
        p.setBrush(QColor(255, 255, 255, int(255 * lens_a)))
        p.drawPath(a.intersected(b))

    # A burst of sparkles from the overlap at the moment of the flash.
    burst = _seg(t, 0.42, 0.75)
    if 0 < burst < 1:
        for i in range(14):
            ang = i / 14 * 2 * math.pi + 0.3
            dist = (r * 0.4 + 260 * unit * _ease_out(burst)) * (0.8 + 0.4 * ((i * 7) % 5) / 5)
            x, y = w / 2 + math.cos(ang) * dist, cy + math.sin(ang) * dist * 0.8
            size = (7 - 5 * burst) * unit * (1.4 if i % 3 == 0 else 1)
            col = QColor(SKY if i % 2 else PINK) if i % 3 else QColor(255, 255, 255)
            col.setAlpha(int(230 * (1 - burst) * fade_out))
            p.setBrush(col)
            p.drawEllipse(QPointF(x, y), size, size)

    # Title, tagline and credit slide up and fade in, one after another.
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
        rect = QRectF(0, y + (1 - k) * 30 * unit, w, size * unit * 1.5)
        p.drawText(rect, Qt.AlignHCenter | Qt.AlignTop, s)

    base = cy + r + 40 * unit
    text(APP_NAME, 96, 800, base, 0.58, QColor(255, 255, 255), 2)
    text("Find duplicates. Keep the best.", 30, 500, base + 125 * unit, 0.66,
         QColor(203, 213, 225))
    text(f"by {AUTHOR}", 22, 600, base + 180 * unit, 0.74, QColor(148, 163, 184), 3)


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
        p.setPen(QColor(148, 163, 184, 140))
        p.drawText(self.rect().adjusted(0, 0, -12, -8), Qt.AlignRight | Qt.AlignBottom,
                   "Click to skip")
        p.end()

    def mousePressEvent(self, _event) -> None:
        self.finish()

    def keyPressEvent(self, _event) -> None:
        self.finish()
