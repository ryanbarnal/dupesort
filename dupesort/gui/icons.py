"""Simple sidebar icons drawn in code, so they match light and dark themes."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

SIZE = 64


def _canvas():
    pm = QPixmap(SIZE, SIZE)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    return pm, p


def _draw(kind: str, p: QPainter, c: QColor) -> None:
    pen = QPen(c, 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if kind == "music":
        p.setBrush(c)
        p.drawEllipse(QRectF(10, 40, 18, 14))
        p.drawEllipse(QRectF(36, 34, 18, 14))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(26, 46), QPointF(26, 12))
        p.drawLine(QPointF(52, 40), QPointF(52, 6))
        p.drawLine(QPointF(26, 12), QPointF(52, 6))
    elif kind == "photos":
        p.drawRoundedRect(QRectF(7, 12, 50, 40), 7, 7)
        path = QPainterPath(QPointF(10, 48))
        path.lineTo(26, 30)
        path.lineTo(36, 40)
        path.lineTo(44, 33)
        path.lineTo(54, 48)
        p.drawPath(path)
        p.setBrush(c)
        p.drawEllipse(QRectF(39, 18, 8, 8))
    elif kind == "videos":
        p.drawRoundedRect(QRectF(5, 14, 40, 36), 7, 7)
        p.setBrush(c)
        tri = QPainterPath(QPointF(47, 26))
        tri.lineTo(59, 18)
        tri.lineTo(59, 46)
        tri.lineTo(47, 38)
        tri.closeSubpath()
        p.drawPath(tri)
    elif kind == "documents":
        path = QPainterPath(QPointF(14, 6))
        path.lineTo(38, 6)
        path.lineTo(50, 18)
        path.lineTo(50, 58)
        path.lineTo(14, 58)
        path.closeSubpath()
        p.drawPath(path)
        for y, w in ((28, 24), (37, 24), (46, 16)):
            p.drawLine(QPointF(21, y), QPointF(21 + w, y))
    elif kind == "history":
        p.drawArc(QRectF(9, 9, 46, 46), 100 * 16, 300 * 16)
        p.drawLine(QPointF(32, 20), QPointF(32, 33))
        p.drawLine(QPointF(32, 33), QPointF(41, 39))
        a = math.radians(100)
        tip = QPointF(32 + 23 * math.cos(a), 32 - 23 * math.sin(a))
        p.drawLine(tip, tip + QPointF(-9, -3))
        p.drawLine(tip, tip + QPointF(-2, 9))
    elif kind == "help":
        p.drawEllipse(QRectF(8, 8, 48, 48))
        path = QPainterPath(QPointF(24, 25))
        path.cubicTo(24, 13, 41, 13, 41, 24)
        path.cubicTo(41, 31, 32, 31, 32, 39)
        p.drawPath(path)
        p.setBrush(c)
        p.drawEllipse(QPointF(32, 47), 3.2, 3.2)


def make(kind: str, color: QColor, selected: QColor = QColor("white")) -> QIcon:
    icon = QIcon()
    for mode, col in ((QIcon.Normal, color), (QIcon.Selected, selected)):
        pm, p = _canvas()
        _draw(kind, p, col)
        p.end()
        icon.addPixmap(pm, mode)
    return icon
