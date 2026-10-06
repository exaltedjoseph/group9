"""Vector icons drawn in the spirit of SF Symbols (24-unit design grid)."""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath,
                           QPainterPathStroker, QPen, QPixmap, QRadialGradient, QTransform)

STROKE = 1.7  # regular weight in grid units


# --------------------------------------------------------------------------- geometry helpers

def squircle_path(rect: QRectF, radius: float) -> QPainterPath:
    """Rounded rect with Apple-style continuous ("squircle") corners."""
    path = QPainterPath()
    w, h = rect.width(), rect.height()
    r = max(0.0, min(radius, min(w, h) / 2.0))
    if r <= 0.0:
        path.addRect(rect)
        return path
    if 1.52866 * r > min(w, h) / 2.0:
        path.addRoundedRect(rect, r, r)
        return path

    left, top = rect.x(), rect.y()
    right, bottom = left + w, top + h
    k = r

    path.moveTo(left + 1.52866 * k, top)
    path.lineTo(right - 1.52866 * k, top)
    path.cubicTo(right - 1.08849 * k, top, right - 0.86840 * k, top, right - 0.63149 * k, top + 0.07491 * k)
    path.cubicTo(right - 0.37282 * k, top + 0.16906 * k, right - 0.16906 * k, top + 0.37282 * k,
                 right - 0.07491 * k, top + 0.63149 * k)
    path.cubicTo(right, top + 0.86840 * k, right, top + 1.08849 * k, right, top + 1.52866 * k)

    path.lineTo(right, bottom - 1.52866 * k)
    path.cubicTo(right, bottom - 1.08849 * k, right, bottom - 0.86840 * k, right - 0.07491 * k, bottom - 0.63149 * k)
    path.cubicTo(right - 0.16906 * k, bottom - 0.37282 * k, right - 0.37282 * k, bottom - 0.16906 * k,
                 right - 0.63149 * k, bottom - 0.07491 * k)
    path.cubicTo(right - 0.86840 * k, bottom, right - 1.08849 * k, bottom, right - 1.52866 * k, bottom)

    path.lineTo(left + 1.52866 * k, bottom)
    path.cubicTo(left + 1.08849 * k, bottom, left + 0.86840 * k, bottom, left + 0.63149 * k, bottom - 0.07491 * k)
    path.cubicTo(left + 0.37282 * k, bottom - 0.16906 * k, left + 0.16906 * k, bottom - 0.37282 * k,
                 left + 0.07491 * k, bottom - 0.63149 * k)
    path.cubicTo(left, bottom - 0.86840 * k, left, bottom - 1.08849 * k, left, bottom - 1.52866 * k)

    path.lineTo(left, top + 1.52866 * k)
    path.cubicTo(left, top + 1.08849 * k, left, top + 0.86840 * k, left + 0.07491 * k, top + 0.63149 * k)
    path.cubicTo(left + 0.16906 * k, top + 0.37282 * k, left + 0.37282 * k, top + 0.16906 * k,
                 left + 0.63149 * k, top + 0.07491 * k)
    path.cubicTo(left + 0.86840 * k, top, left + 1.08849 * k, top, left + 1.52866 * k, top)
    path.closeSubpath()
    return path


def _stroke(path: QPainterPath, width: float) -> QPainterPath:
    s = QPainterPathStroker()
    s.setWidth(width)
    s.setCapStyle(Qt.PenCapStyle.RoundCap)
    s.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return s.createStroke(path)


def _poly(*pts: tuple[float, float], close: bool = False) -> QPainterPath:
    path = QPainterPath(QPointF(*pts[0]))
    for pt in pts[1:]:
        path.lineTo(QPointF(*pt))
    if close:
        path.closeSubpath()
    return path


def _circle(cx: float, cy: float, r: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), r, r)
    return path


def _rrect(x: float, y: float, w: float, h: float, r: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), r, r)
    return path


def _star(cx: float, cy: float, r: float, pinch: float = 0.12) -> QPainterPath:
    """Four-pointed sparkle (Gemini-like) with concave sides."""
    path = QPainterPath(QPointF(cx, cy - r))
    pts = [(cx + r, cy), (cx, cy + r), (cx - r, cy), (cx, cy - r)]
    prev = (cx, cy - r)
    for pt in pts:
        c1 = (prev[0] + (cx - prev[0]) * 0.55 + (pt[0] - cx) * pinch,
              prev[1] + (cy - prev[1]) * 0.55 + (pt[1] - cy) * pinch)
        c2 = (pt[0] + (cx - pt[0]) * 0.55 + (prev[0] - cx) * pinch,
              pt[1] + (cy - pt[1]) * 0.55 + (prev[1] - cy) * pinch)
        path.cubicTo(QPointF(*c1), QPointF(*c2), QPointF(*pt))
        prev = pt
    path.closeSubpath()
    return path


def _gear(cx: float, cy: float, outer: float, inner: float, teeth: int = 8) -> QPainterPath:
    pts = []
    step = 360.0 / teeth
    for i in range(teeth):
        base = i * step
        for ang, rad in ((base - step * 0.22, outer), (base + step * 0.22, outer),
                         (base + step * 0.34, inner), (base + step * 0.66, inner)):
            a = math.radians(ang)
            pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return _poly(*pts, close=True)


# --------------------------------------------------------------------------- icon shapes

def _shape(name: str, weight: float) -> QPainterPath:
    w = STROKE * weight
    parts: list[QPainterPath] = []

    def stroke(path: QPainterPath, width: float | None = None):
        parts.append(_stroke(path, width or w))

    def fill(path: QPainterPath):
        parts.append(path)

    if name == "compose":  # square.and.pencil
        box = QPainterPath(QPointF(11.5, 4.5))
        box.lineTo(7.5, 4.5)
        box.arcTo(QRectF(4.5, 4.5, 6, 6), 90, 90)
        box.lineTo(4.5, 16.5)
        box.arcTo(QRectF(4.5, 13.5, 6, 6), 180, 90)
        box.lineTo(16.5, 19.5)
        box.arcTo(QRectF(13.5, 13.5, 6, 6), 270, 90)
        box.lineTo(19.5, 12.5)
        stroke(box)
        stroke(_poly((10.0, 14.0), (10.6, 11.4), (18.2, 3.8), (20.2, 5.8), (12.6, 13.4), close=True), w * 0.95)
    elif name == "pencil":
        stroke(_poly((5.0, 19.0), (5.8, 15.6), (16.6, 4.8), (19.2, 7.4), (8.4, 18.2), close=True))
        stroke(_poly((14.6, 6.8), (17.2, 9.4)))
    elif name == "search":
        stroke(_circle(10.5, 10.5, 6.2))
        stroke(_poly((15.2, 15.2), (20.0, 20.0)), w * 1.15)
    elif name == "gear":
        g = _gear(12, 12, 9.4, 7.3, 8)
        stroke(g, w * 0.95)
        stroke(_circle(12, 12, 2.9), w * 0.95)
    elif name == "arrow_up":
        stroke(_poly((12, 19), (12, 5.5)))
        stroke(_poly((6, 11.5), (12, 5.5), (18, 11.5)))
    elif name == "stop":
        fill(_rrect(7, 7, 10, 10, 2.4))
    elif name == "copy":  # doc.on.doc
        back = _stroke(_rrect(8.5, 3.5, 11, 13, 2.5), w)
        front_area = _rrect(4.5 - w, 7.5 - w, 11 + 2 * w, 13 + 2 * w, 2.5 + w)
        fill(back.subtracted(front_area))
        stroke(_rrect(4.5, 7.5, 11, 13, 2.5))
    elif name == "check":
        stroke(_poly((5, 12.5), (10, 17.5), (19, 6.5)))
    elif name == "xmark":
        stroke(_poly((6.5, 6.5), (17.5, 17.5)))
        stroke(_poly((17.5, 6.5), (6.5, 17.5)))
    elif name == "xmark_circle_fill":
        cross = _stroke(_poly((9, 9), (15, 15)), 1.9)
        cross.addPath(_stroke(_poly((15, 9), (9, 15)), 1.9))
        fill(_circle(12, 12, 9).subtracted(cross))
    elif name == "sidebar":
        stroke(_rrect(3, 5, 18, 14, 3.2))
        stroke(_poly((9.5, 5.5), (9.5, 18.5)))
    elif name == "sidebar_right":
        stroke(_rrect(3, 5, 18, 14, 3.2))
        stroke(_poly((14.5, 5.5), (14.5, 18.5)))
    elif name == "sparkle":
        fill(_star(12, 12, 9.5, 0.10))
    elif name == "sparkles":
        fill(_star(10.5, 13, 8.5, 0.10))
        fill(_star(19, 5, 3.4, 0.10))
    elif name == "trash":
        stroke(_poly((4.5, 6.5), (19.5, 6.5)))
        stroke(_poly((9.5, 6.5), (9.5, 4.0), (14.5, 4.0), (14.5, 6.5)))
        body = QPainterPath(QPointF(6.5, 6.5))
        body.lineTo(7.4, 18.0)
        body.quadTo(7.6, 20.0, 9.5, 20.0)
        body.lineTo(14.5, 20.0)
        body.quadTo(16.4, 20.0, 16.6, 18.0)
        body.lineTo(17.5, 6.5)
        stroke(body)
        stroke(_poly((10.2, 10), (10.5, 16.5)), w * 0.85)
        stroke(_poly((13.8, 10), (13.5, 16.5)), w * 0.85)
    elif name == "pin":
        stroke(_poly((8.5, 3.5), (15.5, 3.5)))
        stroke(_poly((9.5, 3.5), (9.0, 10.0), (6.5, 13.0), (17.5, 13.0), (15.0, 10.0), (14.5, 3.5)))
        stroke(_poly((12, 13), (12, 20.5)))
    elif name == "pin_slash":
        stroke(_poly((8.5, 3.5), (15.5, 3.5)))
        stroke(_poly((9.5, 3.5), (9.0, 10.0), (6.5, 13.0), (17.5, 13.0), (15.0, 10.0), (14.5, 3.5)))
        stroke(_poly((12, 13), (12, 20.5)))
        stroke(_poly((4, 4), (20, 20)))
    elif name == "eye":
        eye = QPainterPath(QPointF(2.5, 12))
        eye.cubicTo(5.5, 6.5, 8.5, 5.5, 12, 5.5)
        eye.cubicTo(15.5, 5.5, 18.5, 6.5, 21.5, 12)
        eye.cubicTo(18.5, 17.5, 15.5, 18.5, 12, 18.5)
        eye.cubicTo(8.5, 18.5, 5.5, 17.5, 2.5, 12)
        stroke(eye)
        fill(_circle(12, 12, 3.2))
    elif name == "eye_slash":
        eye = QPainterPath(QPointF(2.5, 12))
        eye.cubicTo(5.5, 6.5, 8.5, 5.5, 12, 5.5)
        eye.cubicTo(15.5, 5.5, 18.5, 6.5, 21.5, 12)
        eye.cubicTo(18.5, 17.5, 15.5, 18.5, 12, 18.5)
        eye.cubicTo(8.5, 18.5, 5.5, 17.5, 2.5, 12)
        shape = _stroke(eye, w)
        shape.addPath(_circle(12, 12, 3.2))
        slash_gap = _stroke(_poly((4, 3.5), (20, 20.5)), w * 3.2)
        fill(shape.subtracted(slash_gap))
        stroke(_poly((4, 3.5), (20, 20.5)))
    elif name == "ellipsis":
        for x in (6, 12, 18):
            fill(_circle(x, 12, 1.7))
    elif name == "ellipsis_circle":
        stroke(_circle(12, 12, 9))
        for x in (8, 12, 16):
            fill(_circle(x, 12, 1.3))
    elif name == "chevron_down":
        stroke(_poly((6.5, 9.5), (12, 15), (17.5, 9.5)))
    elif name == "chevron_right":
        stroke(_poly((9.5, 6.5), (15, 12), (9.5, 17.5)))
    elif name == "chevron_left":
        stroke(_poly((14.5, 6.5), (9, 12), (14.5, 17.5)))
    elif name == "chevron_up_down":
        stroke(_poly((7.5, 9.5), (12, 5), (16.5, 9.5)), w * 1.25)
        stroke(_poly((7.5, 14.5), (12, 19), (16.5, 14.5)), w * 1.25)
    elif name == "key":
        stroke(_circle(7.5, 12, 4.2))
        stroke(_poly((11.7, 12), (21, 12)))
        stroke(_poly((17.5, 12), (17.5, 15.2)))
        stroke(_poly((20.5, 12), (20.5, 14.5)))
    elif name == "lock":
        stroke(_rrect(5.5, 10.5, 13, 10, 2.4))
        shackle = QPainterPath(QPointF(8.5, 10.5))
        shackle.lineTo(8.5, 7.5)
        shackle.arcTo(QRectF(8.5, 4.0, 7, 7), 180, -180)
        shackle.lineTo(15.5, 10.5)
        stroke(shackle)
    elif name == "plus":
        stroke(_poly((12, 5), (12, 19)))
        stroke(_poly((5, 12), (19, 12)))
    elif name == "minus":
        stroke(_poly((5, 12), (19, 12)))
    elif name == "retry":  # arrow.clockwise
        arc = QPainterPath()
        rect = QRectF(5, 5, 14, 14)
        arc.arcMoveTo(rect, 40)
        arc.arcTo(rect, 40, -300)
        stroke(arc)
        end = arc.currentPosition()
        stroke(_poly((end.x() - 0.8, end.y() - 3.4), (end.x() + 2.6, end.y()), (end.x() - 0.8, end.y() + 3.4)))
    elif name == "warning":  # exclamationmark.triangle
        tri = QPainterPath(QPointF(10.3, 4.8))
        tri.quadTo(12, 2.2, 13.7, 4.8)
        tri.lineTo(20.6, 17.0)
        tri.quadTo(21.9, 19.8, 18.8, 19.8)
        tri.lineTo(5.2, 19.8)
        tri.quadTo(2.1, 19.8, 3.4, 17.0)
        tri.closeSubpath()
        stroke(tri)
        stroke(_poly((12, 9.0), (12, 13.6)))
        fill(_circle(12, 16.7, 1.15))
    elif name == "appearance":  # circle.lefthalf.filled
        stroke(_circle(12, 12, 8.5))
        half = QPainterPath(QPointF(12, 3.5))
        half.arcTo(QRectF(3.5, 3.5, 17, 17), 90, 180)
        half.closeSubpath()
        fill(half)
    elif name == "text_bubble":
        bubble = QPainterPath(QPointF(7.5, 4.5))
        bubble.lineTo(16.5, 4.5)
        bubble.arcTo(QRectF(14.0, 4.5, 6, 6), 90, -90)
        bubble.lineTo(20.0, 13.0)
        bubble.arcTo(QRectF(14.0, 10.5, 6, 6), 0, -90)
        bubble.lineTo(10.0, 16.5)
        bubble.lineTo(6.0, 20.0)
        bubble.lineTo(6.5, 16.3)
        bubble.arcTo(QRectF(4.0, 10.5, 6, 6), 250, -70)
        bubble.lineTo(4.0, 7.5)
        bubble.arcTo(QRectF(4.0, 4.5, 6, 6), 180, -90)
        bubble.closeSubpath()
        stroke(bubble)
        stroke(_poly((8, 9), (16, 9)), w * 0.9)
        stroke(_poly((8, 12.5), (13.5, 12.5)), w * 0.9)
    elif name == "bubble":
        bubble = QPainterPath()
        bubble.addEllipse(QRectF(3, 4, 18, 14))
        tail = _poly((6.5, 15), (4.5, 20.5), (11, 17.2), close=True)
        stroke(bubble.united(tail))
    elif name == "arrow_up_right":
        stroke(_poly((7.5, 16.5), (16.5, 7.5)))
        stroke(_poly((9.5, 7.5), (16.5, 7.5), (16.5, 14.5)))
    elif name == "cpu":
        stroke(_rrect(6.5, 6.5, 11, 11, 2.2))
        fill(_rrect(9.5, 9.5, 5, 5, 1))
        for t in (9.5, 14.5):
            stroke(_poly((t, 3.5), (t, 6.5)), w * 0.85)
            stroke(_poly((t, 17.5), (t, 20.5)), w * 0.85)
            stroke(_poly((3.5, t), (6.5, t)), w * 0.85)
            stroke(_poly((17.5, t), (20.5, t)), w * 0.85)
    elif name == "exclamation_circle":
        stroke(_circle(12, 12, 9))
        stroke(_poly((12, 7.5), (12, 13)))
        fill(_circle(12, 16.3, 1.15))
    elif name == "checkmark_circle_fill":
        tick = _stroke(_poly((7.8, 12.3), (10.8, 15.3), (16.4, 8.8)), 2.0)
        fill(_circle(12, 12, 9).subtracted(tick))
    elif name == "folder":
        f = QPainterPath(QPointF(3.5, 7.0))
        f.quadTo(3.5, 5.0, 5.5, 5.0)
        f.lineTo(9.2, 5.0)
        f.quadTo(10.2, 5.0, 10.9, 5.8)
        f.lineTo(12.0, 7.0)
        f.lineTo(18.5, 7.0)
        f.quadTo(20.5, 7.0, 20.5, 9.0)
        f.lineTo(20.5, 17.0)
        f.quadTo(20.5, 19.0, 18.5, 19.0)
        f.lineTo(5.5, 19.0)
        f.quadTo(3.5, 19.0, 3.5, 17.0)
        f.closeSubpath()
        stroke(f)
        stroke(_poly((3.5, 10.0), (20.5, 10.0)))
    elif name == "folder_fill":
        f = QPainterPath(QPointF(3.0, 7.0))
        f.quadTo(3.0, 4.5, 5.5, 4.5)
        f.lineTo(9.2, 4.5)
        f.quadTo(10.4, 4.5, 11.1, 5.4)
        f.lineTo(12.2, 6.6)
        f.lineTo(18.5, 6.6)
        f.quadTo(21.0, 6.6, 21.0, 9.1)
        f.lineTo(21.0, 17.0)
        f.quadTo(21.0, 19.5, 18.5, 19.5)
        f.lineTo(5.5, 19.5)
        f.quadTo(3.0, 19.5, 3.0, 17.0)
        f.closeSubpath()
        fill(f)
    elif name == "folder_plus":
        f = QPainterPath(QPointF(12.0, 19.0))
        f.lineTo(5.5, 19.0)
        f.quadTo(3.5, 19.0, 3.5, 17.0)
        f.lineTo(3.5, 7.0)
        f.quadTo(3.5, 5.0, 5.5, 5.0)
        f.lineTo(9.2, 5.0)
        f.quadTo(10.2, 5.0, 10.9, 5.8)
        f.lineTo(12.0, 7.0)
        f.lineTo(18.5, 7.0)
        f.quadTo(20.5, 7.0, 20.5, 9.0)
        f.lineTo(20.5, 11.5)
        stroke(f)
        stroke(_poly((18, 14), (18, 21)))
        stroke(_poly((14.5, 17.5), (21.5, 17.5)))
    elif name == "doc":
        d = QPainterPath(QPointF(13.5, 3.5))
        d.lineTo(7.5, 3.5)
        d.quadTo(5.5, 3.5, 5.5, 5.5)
        d.lineTo(5.5, 18.5)
        d.quadTo(5.5, 20.5, 7.5, 20.5)
        d.lineTo(16.5, 20.5)
        d.quadTo(18.5, 20.5, 18.5, 18.5)
        d.lineTo(18.5, 8.5)
        d.closeSubpath()
        stroke(d)
        stroke(_poly((13.5, 3.5), (13.5, 8.5), (18.5, 8.5)), w * 0.9)
        stroke(_poly((8.8, 12.5), (15.2, 12.5)), w * 0.85)
        stroke(_poly((8.8, 16.0), (13.5, 16.0)), w * 0.85)
    elif name == "rectangle_stack":  # all resources
        stroke(_rrect(4, 8.5, 16, 11.5, 2.4))
        stroke(_poly((6, 6), (18, 6)), w * 0.9)
        stroke(_poly((8, 3.6), (16, 3.6)), w * 0.8)
    elif name == "book":
        b = QPainterPath(QPointF(12, 6.5))
        b.cubicTo(9.5, 4.8, 6.5, 4.5, 3.5, 5.2)
        b.lineTo(3.5, 18.5)
        b.cubicTo(6.5, 17.8, 9.5, 18.1, 12, 19.8)
        b.cubicTo(14.5, 18.1, 17.5, 17.8, 20.5, 18.5)
        b.lineTo(20.5, 5.2)
        b.cubicTo(17.5, 4.5, 14.5, 4.8, 12, 6.5)
        b.closeSubpath()
        stroke(b)
        stroke(_poly((12, 6.5), (12, 19.5)))
    elif name == "books":  # books.vertical
        stroke(_rrect(3.5, 4.5, 4.5, 15, 1.2))
        stroke(_rrect(9.5, 6.5, 4.5, 13, 1.2))
        tilted = QPainterPath()
        tilted.addRoundedRect(QRectF(-2.2, -6.8, 4.4, 13.6), 1.2, 1.2)
        stroke(QTransform().translate(18.2, 12.6).rotate(-14).map(tilted))
    elif name == "graduationcap":
        stroke(_poly((12, 5), (22, 9.5), (12, 14), (2, 9.5), close=True))
        cap = QPainterPath(QPointF(6, 11.5))
        cap.lineTo(6, 16)
        cap.cubicTo(9, 19, 15, 19, 18, 16)
        cap.lineTo(18, 11.5)
        stroke(cap)
        stroke(_poly((21, 10), (21, 15)), w * 0.9)
    elif name == "person":
        stroke(_circle(12, 8, 3.8))
        body = QPainterPath(QPointF(4.5, 20))
        body.cubicTo(4.5, 15.5, 8, 13.8, 12, 13.8)
        body.cubicTo(16, 13.8, 19.5, 15.5, 19.5, 20)
        stroke(body)
    elif name == "calendar":
        stroke(_rrect(3.5, 5, 17, 15, 3))
        stroke(_poly((3.5, 9.5), (20.5, 9.5)))
        stroke(_poly((8, 3), (8, 6.5)))
        stroke(_poly((16, 3), (16, 6.5)))
        for x, y in ((8, 13), (12, 13), (16, 13), (8, 16.5), (12, 16.5)):
            fill(_circle(x, y, 0.95))
    elif name == "clock":
        stroke(_circle(12, 12, 8.5))
        stroke(_poly((12, 7), (12, 12), (15.5, 14)))
    elif name == "history":  # clock.arrow.circlepath
        arc = QPainterPath()
        rect = QRectF(4, 4, 16, 16)
        arc.arcMoveTo(rect, 200)
        arc.arcTo(rect, 200, -320)
        stroke(arc)
        start = QPointF(12 + 8 * math.cos(math.radians(200)), 12 - 8 * math.sin(math.radians(200)))
        stroke(_poly((start.x() - 3.0, start.y() - 2.2), (start.x(), start.y() + 0.6), (start.x() + 2.6, start.y() - 2.4)))
        stroke(_poly((12, 8), (12, 12), (14.8, 14)))
    elif name == "branch":  # git branch
        stroke(_circle(7, 5.5, 2.2))
        stroke(_circle(7, 18.5, 2.2))
        stroke(_circle(17, 7.5, 2.2))
        stroke(_poly((7, 7.7), (7, 16.3)))
        b = QPainterPath(QPointF(17, 9.7))
        b.cubicTo(17, 13.5, 7, 12.5, 7, 16.3)
        stroke(b)
    elif name == "tag":
        t = QPainterPath(QPointF(4, 5.8))
        t.quadTo(4, 4, 5.8, 4)
        t.lineTo(11.4, 4)
        t.quadTo(12.2, 4, 12.8, 4.6)
        t.lineTo(19.6, 11.4)
        t.quadTo(20.6, 12.4, 19.6, 13.4)
        t.lineTo(13.4, 19.6)
        t.quadTo(12.4, 20.6, 11.4, 19.6)
        t.lineTo(4.6, 12.8)
        t.quadTo(4, 12.2, 4, 11.4)
        t.closeSubpath()
        stroke(t)
        fill(_circle(8.3, 8.3, 1.5))
    elif name == "download":  # arrow.down.circle
        stroke(_circle(12, 12, 9))
        stroke(_poly((12, 7), (12, 16.5)))
        stroke(_poly((8, 12.8), (12, 16.8), (16, 12.8)))
    elif name == "upload":  # square.and.arrow.up
        stroke(_poly((12, 3.5), (12, 14)))
        stroke(_poly((8.2, 7.2), (12, 3.4), (15.8, 7.2)))
        box = QPainterPath(QPointF(9, 9.5))
        box.lineTo(7, 9.5)
        box.quadTo(5, 9.5, 5, 11.5)
        box.lineTo(5, 18.5)
        box.quadTo(5, 20.5, 7, 20.5)
        box.lineTo(17, 20.5)
        box.quadTo(19, 20.5, 19, 18.5)
        box.lineTo(19, 11.5)
        box.quadTo(19, 9.5, 17, 9.5)
        box.lineTo(15, 9.5)
        stroke(box)
    elif name == "tray_down":  # square.and.arrow.down
        stroke(_poly((12, 3.5), (12, 14)))
        stroke(_poly((8.2, 10.4), (12, 14.2), (15.8, 10.4)))
        box = QPainterPath(QPointF(9, 9.5))
        box.lineTo(7, 9.5)
        box.quadTo(5, 9.5, 5, 11.5)
        box.lineTo(5, 18.5)
        box.quadTo(5, 20.5, 7, 20.5)
        box.lineTo(17, 20.5)
        box.quadTo(19, 20.5, 19, 18.5)
        box.lineTo(19, 11.5)
        box.quadTo(19, 9.5, 17, 9.5)
        box.lineTo(15, 9.5)
        stroke(box)
    elif name == "open":  # arrow.up.forward.square
        box = QPainterPath(QPointF(11, 4.5))
        box.lineTo(7, 4.5)
        box.quadTo(4.5, 4.5, 4.5, 7)
        box.lineTo(4.5, 17)
        box.quadTo(4.5, 19.5, 7, 19.5)
        box.lineTo(17, 19.5)
        box.quadTo(19.5, 19.5, 19.5, 17)
        box.lineTo(19.5, 13)
        stroke(box)
        stroke(_poly((11, 13), (19.5, 4.5)))
        stroke(_poly((14, 4.5), (19.5, 4.5), (19.5, 10)))
    elif name == "list":  # list.bullet
        for y in (6.5, 12, 17.5):
            fill(_circle(5, y, 1.4))
            stroke(_poly((9, y), (20, y)))
    elif name == "grid":  # square.grid.2x2
        for x, y in ((4, 4), (13, 4), (4, 13), (13, 13)):
            stroke(_rrect(x, y, 7, 7, 1.8))
    elif name == "filter":  # line.3.horizontal.decrease.circle
        stroke(_circle(12, 12, 9))
        stroke(_poly((7.5, 9), (16.5, 9)), w * 0.9)
        stroke(_poly((9, 12.2), (15, 12.2)), w * 0.9)
        stroke(_poly((10.6, 15.4), (13.4, 15.4)), w * 0.9)
    elif name == "plus_circle":
        stroke(_circle(12, 12, 9))
        stroke(_poly((12, 7.5), (12, 16.5)))
        stroke(_poly((7.5, 12), (16.5, 12)))
    elif name == "wand":  # wand.and.stars
        stroke(_poly((4, 20), (14.5, 9.5)), w * 1.1)
        stroke(_poly((13, 8), (16, 11)), w * 0.9)
        fill(_star(18, 5.5, 3.2, 0.1))
        fill(_star(9, 4.5, 2.0, 0.1))
        fill(_star(19.5, 14, 2.0, 0.1))
    elif name == "paperclip":
        clip = QPainterPath(QPointF(16.5, 9.5))
        clip.lineTo(10.2, 15.8)
        clip.cubicTo(8.9, 17.1, 7.1, 15.3, 8.4, 14.0)
        clip.lineTo(15.4, 7.0)
        clip.cubicTo(17.6, 4.8, 20.9, 8.1, 18.7, 10.3)
        clip.lineTo(11.3, 17.7)
        clip.cubicTo(8.3, 20.7, 3.6, 16.0, 6.6, 13.0)
        clip.lineTo(12.5, 7.1)
        stroke(clip)
    elif name == "info_circle":
        stroke(_circle(12, 12, 9))
        stroke(_poly((12, 11), (12, 16.5)))
        fill(_circle(12, 7.8, 1.15))
    elif name == "sync":  # arrow.triangle.2.circlepath
        top = QPainterPath()
        rect = QRectF(4.5, 4.5, 15, 15)
        top.arcMoveTo(rect, 160)
        top.arcTo(rect, 160, -150)
        bottom = QPainterPath()
        bottom.arcMoveTo(rect, 340)
        bottom.arcTo(rect, 340, -150)
        stroke(top)
        stroke(bottom)
        e1 = top.currentPosition()
        stroke(_poly((e1.x() - 3.2, e1.y() - 1.0), (e1.x(), e1.y() + 0.4), (e1.x() + 0.9, e1.y() - 2.8)))
        e2 = bottom.currentPosition()
        stroke(_poly((e2.x() + 3.2, e2.y() + 1.0), (e2.x(), e2.y() - 0.4), (e2.x() - 0.9, e2.y() + 2.8)))
    elif name == "internaldrive":
        stroke(_rrect(3.5, 7, 17, 10, 2.6))
        fill(_circle(16.5, 12, 1.1))
        stroke(_poly((6.5, 12), (11.5, 12)), w * 0.9)
    elif name == "checklist":
        stroke(_poly((3.8, 6.8), (5.4, 8.4), (8.2, 5.2)))
        stroke(_poly((3.8, 15.8), (5.4, 17.4), (8.2, 14.2)))
        stroke(_poly((11, 7), (20.5, 7)))
        stroke(_poly((11, 16), (20.5, 16)))
    elif name == "star":
        pts = []
        for i in range(10):
            a = math.radians(-90 + i * 36)
            rad = 9 if i % 2 == 0 else 3.9
            pts.append((12 + rad * math.cos(a), 12.6 + rad * math.sin(a)))
        stroke(_poly(*pts, close=True))
    elif name == "square_pencil":
        stroke(_poly((10.0, 14.0), (10.6, 11.4), (18.2, 3.8), (20.2, 5.8), (12.6, 13.4), close=True), w * 0.95)
    else:
        stroke(_circle(12, 12, 8))

    out = QPainterPath()
    for part in parts:
        out = out.united(part)
    return out


@lru_cache(maxsize=256)
def _cached_shape(name: str, weight: float) -> QPainterPath:
    return _shape(name, weight)


def draw_icon(painter: QPainter, name: str, rect: QRectF, color: QColor, weight: float = 1.0) -> None:
    """Paint icon `name` into `rect` (square) with `color`."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    side = min(rect.width(), rect.height())
    painter.translate(rect.x() + (rect.width() - side) / 2, rect.y() + (rect.height() - side) / 2)
    painter.scale(side / 24.0, side / 24.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(color))
    painter.drawPath(_cached_shape(name, round(weight, 3)))
    painter.restore()


def icon_pixmap(name: str, color: QColor, size: int, dpr: float = 2.0, weight: float = 1.0) -> QPixmap:
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    draw_icon(p, name, QRectF(0, 0, size, size), color, weight)
    p.end()
    return pm


def make_icon(name: str, color: QColor, size: int = 16, weight: float = 1.0) -> QIcon:
    icon = QIcon()
    for dpr in (1.0, 1.5, 2.0, 3.0):
        icon.addPixmap(icon_pixmap(name, color, size, dpr, weight))
    return icon


# --------------------------------------------------------------------------- file icons

_FILE_COLORS = {
    "pdf": "#E5352B",
    "ppt": "#E8692A", "pptx": "#E8692A", "key": "#E8692A", "odp": "#E8692A",
    "doc": "#2B6DE5", "docx": "#2B6DE5", "pages": "#2B6DE5", "odt": "#2B6DE5", "rtf": "#2B6DE5",
    "xls": "#22A355", "xlsx": "#22A355", "csv": "#22A355", "numbers": "#22A355", "ods": "#22A355",
    "png": "#A550D8", "jpg": "#A550D8", "jpeg": "#A550D8", "gif": "#A550D8", "webp": "#A550D8",
    "svg": "#A550D8", "heic": "#A550D8", "bmp": "#A550D8",
    "mp4": "#5856D6", "mov": "#5856D6", "mkv": "#5856D6", "avi": "#5856D6", "webm": "#5856D6",
    "mp3": "#E0367A", "wav": "#E0367A", "m4a": "#E0367A",
    "zip": "#8E8E93", "rar": "#8E8E93", "7z": "#8E8E93", "tar": "#8E8E93", "gz": "#8E8E93",
    "py": "#14A0B4", "ipynb": "#F37726", "js": "#C9A800", "ts": "#2F74C0", "html": "#E4572E",
    "css": "#2965F1", "java": "#B07219", "c": "#555555", "cpp": "#00599C", "sql": "#D18A00",
    "json": "#8E8E93", "md": "#6E6E73", "txt": "#6E6E73",
}


def file_color(ext: str) -> QColor:
    return QColor(_FILE_COLORS.get(ext.lower().lstrip("."), "#8E8E93"))


def draw_file_icon(painter: QPainter, rect: QRectF, ext: str, dark: bool = False) -> None:
    """macOS-style document icon: white page, folded corner and a colored extension label."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    side = min(rect.width(), rect.height())
    w = side * 0.76
    h = side * 0.96
    x = rect.x() + (rect.width() - w) / 2
    y = rect.y() + (rect.height() - h) / 2
    fold = w * 0.30
    r = w * 0.08

    page = QPainterPath(QPointF(x + r, y))
    page.lineTo(x + w - fold, y)
    page.lineTo(x + w, y + fold)
    page.lineTo(x + w, y + h - r)
    page.quadTo(x + w, y + h, x + w - r, y + h)
    page.lineTo(x + r, y + h)
    page.quadTo(x, y + h, x, y + h - r)
    page.lineTo(x, y + r)
    page.quadTo(x, y, x + r, y)
    page.closeSubpath()

    painter.fillPath(page.translated(0, side * 0.012), QColor(0, 0, 0, 40))
    painter.fillPath(page, QColor("#FFFFFF") if not dark else QColor("#F2F2F4"))
    painter.setPen(QPen(QColor(0, 0, 0, 38), max(0.6, side / 96)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(page)

    corner = QPainterPath(QPointF(x + w - fold, y))
    corner.lineTo(x + w - fold, y + fold - r * 0.6)
    corner.quadTo(x + w - fold, y + fold, x + w - fold + r * 0.6, y + fold)
    corner.lineTo(x + w, y + fold)
    corner.closeSubpath()
    painter.fillPath(corner, QColor(226, 226, 230))
    painter.drawPath(corner)

    color = file_color(ext)
    label = ext.upper().lstrip(".")[:4] or "FILE"
    if side >= 34:
        band_h = h * 0.22
        band = QRectF(x + w * 0.10, y + h * 0.62, w * 0.80, band_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(band, band_h * 0.22, band_h * 0.22)
        f = QFont(painter.font())
        f.setBold(True)
        f.setPixelSize(max(6, int(band_h * 0.62)))
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 104)
        painter.setFont(f)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(band, Qt.AlignmentFlag.AlignCenter, label)
        line_pen = QPen(QColor(0, 0, 0, 30), max(0.8, side / 64), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(line_pen)
        for i in range(3):
            ly = y + h * (0.30 + i * 0.09)
            painter.drawLine(QPointF(x + w * 0.16, ly), QPointF(x + w * (0.70 if i else 0.52), ly))
    else:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(x + w * 0.16, y + h * 0.56, w * 0.68, h * 0.24), 1.5, 1.5)
    painter.restore()


# --------------------------------------------------------------------------- app icon

def draw_app_icon(painter: QPainter, rect: QRectF) -> None:
    """macOS-style app icon: blue-indigo squircle with a white open book."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    side = min(rect.width(), rect.height())
    r = QRectF(rect.x() + (rect.width() - side) / 2, rect.y() + (rect.height() - side) / 2, side, side)
    inset = side * 0.098  # macOS icon grid: 824/1024 body
    body = r.adjusted(inset, inset, -inset, -inset)
    path = squircle_path(body, body.width() * 0.225)

    # drop shadow
    for i, alpha in enumerate((26, 18, 10)):
        off = side * (0.008 + i * 0.008)
        shadow = squircle_path(body.translated(0, off).adjusted(-i * 0.5, -i * 0.5, i * 0.5, i * 0.5),
                               body.width() * 0.225)
        painter.fillPath(shadow, QColor(0, 0, 0, alpha))

    grad = QLinearGradient(body.topLeft(), body.bottomLeft())
    grad.setColorAt(0.0, QColor("#4FA8FF"))
    grad.setColorAt(1.0, QColor("#3F5BF2"))
    painter.fillPath(path, QBrush(grad))

    glow = QRadialGradient(body.center().x(), body.top() + body.height() * 0.15, body.width() * 0.85)
    glow.setColorAt(0.0, QColor(255, 255, 255, 60))
    glow.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillPath(path, QBrush(glow))

    glyph = body.width() * 0.64
    glyph_rect = QRectF(body.center().x() - glyph / 2, body.center().y() - glyph / 2 + body.height() * 0.02,
                        glyph, glyph)
    draw_icon(painter, "book", glyph_rect, QColor(255, 255, 255, 250), weight=1.25 if side >= 32 else 1.6)
    spark = body.width() * 0.2
    draw_icon(painter, "sparkle", QRectF(body.right() - spark * 1.45, body.top() + spark * 0.45, spark, spark),
              QColor(255, 255, 255, 235))
    painter.restore()


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        draw_app_icon(p, QRectF(0, 0, size, size))
        p.end()
        icon.addPixmap(pm)
    return icon
