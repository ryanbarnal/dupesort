"""Thin outline icons drawn in code, so they follow light and dark themes.

Every icon is drawn on a 24-unit grid with a 1.5-unit round-capped stroke
(the same quiet line style as the logo). ``make`` builds a sidebar icon;
``attach`` puts an icon on a button and keeps it in step with the theme.
"""

from __future__ import annotations

import math
import weakref

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QApplication

STROKE = 1.5
RENDER = 96  # pixels per icon image; Qt scales it down smoothly


def _pt(x: float, y: float) -> QPointF:
    return QPointF(x, y)


def _poly(p: QPainter, *pts, close: bool = False) -> None:
    path = QPainterPath(_pt(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(x, y)
    if close:
        path.closeSubpath()
    p.drawPath(path)


def _lines(p: QPainter, *segs) -> None:
    for x1, y1, x2, y2 in segs:
        p.drawLine(_pt(x1, y1), _pt(x2, y2))


def _arrow_tip(p: QPainter, x: float, y: float, ang: float, size: float = 4) -> None:
    """Open arrow head at (x, y) pointing in direction ``ang`` (radians)."""
    for side in (-1, 1):
        a = ang + math.pi + side * math.radians(45)
        p.drawLine(_pt(x, y), _pt(x + size * math.cos(a), y + size * math.sin(a)))


# --- the icons, all on a 24 x 24 grid ------------------------------------------------
def _music(p):
    p.drawEllipse(QRectF(3.5, 15, 5, 5))
    p.drawEllipse(QRectF(15.5, 13, 5, 5))
    _poly(p, (8.5, 17.5), (8.5, 5.5), (20.5, 3.5), (20.5, 15.5))
    _lines(p, (8.5, 9.5, 20.5, 7.5))


def _photos(p):
    p.drawRoundedRect(QRectF(3, 4, 18, 16), 2.5, 2.5)
    p.drawEllipse(QRectF(7, 7.5, 3.5, 3.5))
    _poly(p, (21, 15), (16, 10), (5, 20))


def _videos(p):
    p.drawRoundedRect(QRectF(2.5, 6, 13.5, 12), 2.5, 2.5)
    _poly(p, (16, 10.5), (21.5, 7.5), (21.5, 16.5), (16, 13.5))


def _documents(p):
    _poly(p, (14, 2.5), (6, 2.5), (4.5, 4), (4.5, 20), (6, 21.5), (18, 21.5), (19.5, 20),
          (19.5, 8), (14, 2.5))
    _poly(p, (14, 2.5), (14, 8), (19.5, 8))
    _lines(p, (8.5, 13, 15.5, 13), (8.5, 17, 13, 17))


def _history(p):
    p.drawArc(QRectF(3, 3, 18, 18), 150 * 16, 300 * 16)
    a = math.radians(150)
    _arrow_tip(p, 12 + 9 * math.cos(a), 12 - 9 * math.sin(a), math.radians(250), 3.5)
    _poly(p, (12, 7.5), (12, 12), (15, 14))


def _help(p):
    p.drawEllipse(QRectF(3, 3, 18, 18))
    path = QPainterPath(_pt(9.5, 9.5))
    path.cubicTo(9.5, 6.5, 14.5, 6.5, 14.5, 9.5)
    path.cubicTo(14.5, 11.5, 12, 11.8, 12, 13.8)
    p.drawPath(path)
    p.drawPoint(_pt(12, 17))


def _scan(p):  # magnifier
    p.drawEllipse(QRectF(4, 4, 13, 13))
    _lines(p, (15, 15, 20.5, 20.5))


def _move(p):  # into a folder
    _poly(p, (3, 7), (3, 19), (4.5, 20.5), (19.5, 20.5), (21, 19), (21, 9.5), (19.5, 8),
          (11.5, 8), (9.5, 5.5), (4.5, 5.5), (3, 7))
    _lines(p, (8, 14.25, 16, 14.25))
    _arrow_tip(p, 16, 14.25, 0, 3)


def _folder(p):
    _poly(p, (3, 7), (3, 19), (4.5, 20.5), (19.5, 20.5), (21, 19), (21, 9.5), (19.5, 8),
          (11.5, 8), (9.5, 5.5), (4.5, 5.5), (3, 7))


def _folder_plus(p):
    _folder(p)
    _lines(p, (12, 11, 12, 17.5), (8.75, 14.25, 15.25, 14.25))


def _file_plus(p):
    _poly(p, (14, 2.5), (6, 2.5), (4.5, 4), (4.5, 20), (6, 21.5), (18, 21.5), (19.5, 20),
          (19.5, 8), (14, 2.5))
    _poly(p, (14, 2.5), (14, 8), (19.5, 8))
    _lines(p, (12, 11.5, 12, 18), (8.75, 14.75, 15.25, 14.75))


def _plus(p):
    _lines(p, (12, 5, 12, 19), (5, 12, 19, 12))


def _minus(p):
    _lines(p, (5, 12, 19, 12))


def _close(p):
    _lines(p, (6, 6, 18, 18), (18, 6, 6, 18))


def _trash(p):
    _lines(p, (3.5, 6.5, 20.5, 6.5))
    _poly(p, (9, 6.5), (9, 3.5), (15, 3.5), (15, 6.5))
    _poly(p, (5.5, 6.5), (6.5, 20), (8, 21.5), (16, 21.5), (17.5, 20), (18.5, 6.5))
    _lines(p, (10, 10.5, 10, 17.5), (14, 10.5, 14, 17.5))


def _eye(p):
    path = QPainterPath(_pt(2, 12))
    path.cubicTo(5, 5.5, 19, 5.5, 22, 12)
    path.cubicTo(19, 18.5, 5, 18.5, 2, 12)
    p.drawPath(path)
    p.drawEllipse(QRectF(9, 9, 6, 6))


def _check(p):
    _poly(p, (4.5, 12.5), (9.5, 17.5), (19.5, 6.5))


def _globe(p):
    p.drawEllipse(QRectF(3, 3, 18, 18))
    p.drawEllipse(QRectF(8, 3, 8, 18))
    _lines(p, (3, 12, 21, 12))


def _pencil(p):
    _poly(p, (4, 20), (4.5, 16), (16, 4.5), (19.5, 8), (8, 19.5), (4, 20), close=True)
    _lines(p, (13.5, 7, 17, 10.5))


def _undo(p):
    path = QPainterPath(_pt(4, 9.5))
    path.lineTo(15, 9.5)
    path.cubicTo(18.5, 9.5, 20.5, 12, 20.5, 14.5)
    path.cubicTo(20.5, 17, 18.5, 19.5, 15, 19.5)
    path.lineTo(9, 19.5)
    p.drawPath(path)
    _arrow_tip(p, 4, 9.5, math.pi, 4)


def _external(p):  # open
    _poly(p, (11, 4.5), (6, 4.5), (4.5, 6), (4.5, 18), (6, 19.5), (18, 19.5), (19.5, 18),
          (19.5, 13))
    _lines(p, (11, 13, 19.5, 4.5))
    _poly(p, (14, 4.5), (19.5, 4.5), (19.5, 10))


def _mail(p):
    p.drawRoundedRect(QRectF(2.5, 5, 19, 14), 2.5, 2.5)
    _poly(p, (3, 6.5), (12, 13), (21, 6.5))


def _book(p):
    _poly(p, (12, 6.5), (12, 20.5))
    _poly(p, (12, 6.5), (9, 4.5), (2.5, 4.5), (2.5, 18), (9, 18), (12, 20.5), (15, 18),
          (21.5, 18), (21.5, 4.5), (15, 4.5), (12, 6.5))


def _heart(p):
    path = QPainterPath(_pt(12, 20))
    path.cubicTo(5, 15.5, 2.5, 12, 2.5, 8.8)
    path.cubicTo(2.5, 6, 4.6, 4, 7.2, 4)
    path.cubicTo(9.2, 4, 11, 5.2, 12, 7)
    path.cubicTo(13, 5.2, 14.8, 4, 16.8, 4)
    path.cubicTo(19.4, 4, 21.5, 6, 21.5, 8.8)
    path.cubicTo(21.5, 12, 19, 15.5, 12, 20)
    p.drawPath(path)


def _convert(p):  # two arrows swapping
    _lines(p, (4, 8, 19, 8))
    _arrow_tip(p, 19, 8, 0, 3.5)
    _lines(p, (20, 16, 5, 16))
    _arrow_tip(p, 5, 16, math.pi, 3.5)


def _sparkle(p):  # tidy / organize
    path = QPainterPath(_pt(11, 3))
    path.quadTo(11, 10, 4, 10.5)
    path.quadTo(11, 11, 11, 18)
    path.quadTo(11, 11, 18, 10.5)
    path.quadTo(11, 10, 11, 3)
    p.drawPath(path)
    _lines(p, (18.5, 15, 18.5, 21), (15.5, 18, 21.5, 18))


def _more(p):  # "…" browse
    for x in (6, 12, 18):
        p.drawPoint(_pt(x, 12))


def _stop(p):
    p.drawEllipse(QRectF(3, 3, 18, 18))
    p.drawRoundedRect(QRectF(9, 9, 6, 6), 1, 1)


def _play(p):
    _poly(p, (7, 4.5), (19, 12), (7, 19.5), close=True)


def _pause(p):
    p.drawRoundedRect(QRectF(6, 4.5, 4, 15), 1, 1)
    p.drawRoundedRect(QRectF(14, 4.5, 4, 15), 1, 1)


def _tag(p):
    _poly(p, (3, 4.5), (3, 11), (13, 21), (21, 13), (11, 3), (4.5, 3), (3, 4.5))
    p.drawEllipse(QRectF(6.5, 6.5, 3, 3))


_ICONS = {
    "music": _music, "photos": _photos, "videos": _videos, "documents": _documents,
    "history": _history, "help": _help, "scan": _scan, "move": _move, "folder": _folder,
    "folder-plus": _folder_plus, "file-plus": _file_plus, "plus": _plus, "minus": _minus,
    "close": _close, "trash": _trash, "eye": _eye, "check": _check, "globe": _globe,
    "pencil": _pencil, "undo": _undo, "open": _external, "mail": _mail, "book": _book,
    "heart": _heart, "convert": _convert, "sparkle": _sparkle, "more": _more, "stop": _stop,
    "tag": _tag, "play": _play, "pause": _pause,
}
KINDS = tuple(_ICONS)


def _pixmap(kind: str, color: QColor) -> QPixmap:
    pm = QPixmap(RENDER, RENDER)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(RENDER / 24, RENDER / 24)
    p.setPen(QPen(color, STROKE, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    _ICONS[kind](p)
    p.end()
    return pm


def make(kind: str, color: QColor, selected: QColor | None = None,
         disabled: QColor | None = None) -> QIcon:
    icon = QIcon()
    icon.addPixmap(_pixmap(kind, color), QIcon.Normal)
    icon.addPixmap(_pixmap(kind, selected or color), QIcon.Selected)
    if disabled is not None:
        icon.addPixmap(_pixmap(kind, disabled), QIcon.Disabled)
    return icon


# --- button icons that follow the theme ----------------------------------------------
_buttons: "weakref.WeakKeyDictionary[QAbstractButton, str]" = weakref.WeakKeyDictionary()


def _paint_button(btn: QAbstractButton, kind: str) -> None:
    from .theme import current

    pal = QApplication.palette()
    primary = getattr(btn, "isDefault", lambda: False)()
    color = pal.color(QPalette.ButtonText)
    if primary and current.get("on_accent"):
        color = QColor(current["on_accent"])
    disabled = pal.color(QPalette.Disabled, QPalette.ButtonText)
    btn.setIcon(make(kind, color, disabled=disabled))


def attach(btn: QAbstractButton, kind: str, size: int = 16) -> QAbstractButton:
    """Give ``btn`` a thin outline icon that is redrawn when the theme changes."""
    _buttons[btn] = kind
    btn.setIconSize(QSize(size, size))
    _paint_button(btn, kind)
    return btn


def refresh_buttons() -> None:
    for btn, kind in list(_buttons.items()):
        try:
            _paint_button(btn, kind)
        except RuntimeError:  # the C++ widget is already gone
            _buttons.pop(btn, None)
