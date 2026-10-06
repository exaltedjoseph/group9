"""Home dashboard: greeting with an Assistant prompt, library stats, module cards and recent activity."""
from __future__ import annotations

import math
import time
from datetime import date, datetime

from PySide6.QtCore import QDate, QEasingCurve, QLocale, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (QAbstractButton, QBoxLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from .. import icons
from ..constants import MODE_FACILITATOR, MODE_INTERN
from ..core.library import Library
from ..core.models import ClassworkEntry, Module, Resource
from ..core.settings import Settings
from ..theme import font, palette, rgba, system_color, theme, with_alpha
from . import actions
from .classwork_view import draw_date_tile, wrap_lines
from .controls import IconButton, mix, on_theme_change
from .toolbar import Toolbar

MAX_WIDTH = 1100
_M = 5          # transparent inset around every card that leaves room for its shadow
_GAP = 6        # layout gap between cards (visual gap is _GAP + 2 * _M)
_RADIUS = 14.0

SUGGESTIONS = (
    ("branch", "Explain Git branching"),
    ("checklist", "Quiz me on Python loops"),
    ("calendar", "Summarize this week\u2019s classwork"),
)


def _canvas_color() -> QColor:
    pal = palette()
    return pal.window if pal.dark else pal.sheet


def _day_text(d: date | None) -> str:
    if d is None:
        return ""
    delta = (date.today() - d).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    if delta == -1:
        return "Tomorrow"
    if 1 < delta < 7:
        return QLocale().dayName(d.isoweekday(), QLocale.FormatType.LongFormat)
    return actions.medium_date(d, with_year=d.year != date.today().year)


def _greeting() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 18:
        return "Good afternoon"
    return "Good evening"


def _display_name(name: str) -> str:
    name = (name or "").strip()
    return name[:1].upper() + name[1:] if name.islower() else name


def _elide_lines(text: str, f: QFont, width: float, limit: int) -> list[str]:
    lines = wrap_lines(text, f, width)
    if len(lines) > limit:
        rest = " ".join(lines[limit - 1:])
        lines = lines[:limit - 1] + [QFontMetricsF(f).elidedText(rest, Qt.TextElideMode.ElideRight, width)]
    return lines


def _badge(p: QPainter, rect: QRectF, color: QColor, glyph: str, circle: bool = False) -> None:
    """Colored SF-style symbol badge with a soft top-to-bottom sheen and a white glyph."""
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g.setColorAt(0.0, color.lighter(118))
    g.setColorAt(1.0, color)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    if circle:
        p.drawEllipse(rect)
    else:
        p.drawPath(icons.squircle_path(rect, rect.width() * 0.26))
    inset = rect.width() * 0.22
    icons.draw_icon(p, glyph, rect.adjusted(inset, inset, -inset, -inset), QColor(255, 255, 255))


# --------------------------------------------------------------------------- building blocks

class _Card(QWidget):
    """Rounded widget card with a soft shadow; clickable cards lift slightly on hover."""

    clicked = Signal()

    def __init__(self, clickable: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._clickable = False
        self._lift = 0.0
        self._pressed = False
        self._anim = QVariantAnimation(self, duration=180, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_lift)
        self.set_clickable(clickable)
        on_theme_change(self, self.update, call_now=False)

    def set_clickable(self, on: bool) -> None:
        self._clickable = on
        if on:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
            self._set_lift(0.0)

    def _set_lift(self, v) -> None:
        self._lift = float(v)
        self.update()

    def _animate(self, target: float) -> None:
        if not self._clickable:
            return
        self._anim.stop()
        self._anim.setStartValue(self._lift)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, e):
        self._animate(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate(0.0)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if self._clickable and e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
            return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                self.clicked.emit()
            return
        super().mouseReleaseEvent(e)

    def card_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(_M, _M, -_M, -_M).translated(0, -1.5 * self._lift)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        pal = palette()
        r = self.card_rect()
        k = 2.6 if pal.dark else 1.0
        lift = self._lift
        for spread, a in ((3.5, 3), (2.0, 5), (0.8, 8)):
            sr = r.adjusted(-spread, -spread + 1.0 + lift, spread, spread + 1.0 + 1.5 * lift)
            p.fillPath(icons.squircle_path(sr, _RADIUS + spread), QColor(0, 0, 0, int(a * k * (1 + 0.9 * lift))))
        path = icons.squircle_path(r, _RADIUS)
        if pal.dark:
            p.fillPath(path, _canvas_color())
            p.fillPath(path, with_alpha(pal.group, pal.group.alpha() + int(8 * lift)))
        else:
            p.fillPath(path, pal.group)
        if self._pressed:
            p.fillPath(path, pal.hover)
        self.paint_content(p, r)
        p.setPen(QPen(pal.group_border, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(icons.squircle_path(r.adjusted(0.5, 0.5, -0.5, -0.5), _RADIUS - 0.5))

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        pass


class _Canvas(QWidget):
    def paintEvent(self, _):
        QPainter(self).fillRect(self.rect(), _canvas_color())


class _FlowGrid(QWidget):
    """Equal-width grid of fixed-height children; picks the largest allowed column count that fits."""

    def __init__(self, item_height: int, min_item_width: int, columns: tuple[int, ...],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._h = item_height
        self._min_w = min_item_width
        self._columns = sorted(columns, reverse=True)
        self._items: list[QWidget] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(item_height)

    def set_items(self, widgets: list[QWidget]) -> None:
        for w in self._items:
            if w not in widgets:
                w.hide()
                w.deleteLater()
        self._items = list(widgets)
        for w in self._items:
            w.setParent(self)
            w.show()
        self._relayout()

    def items(self) -> list[QWidget]:
        return list(self._items)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def _relayout(self) -> None:
        width = self.width()
        cols = next((c for c in self._columns if c * self._min_w + (c - 1) * _GAP <= width), self._columns[-1])
        cw = (width - (cols - 1) * _GAP) / cols
        for i, w in enumerate(self._items):
            row, col = divmod(i, cols)
            x = round(col * (cw + _GAP))
            w.setGeometry(x, row * (self._h + _GAP), round((col + 1) * (cw + _GAP) - _GAP) - x, self._h)
        rows = math.ceil(len(self._items) / cols)
        height = rows * self._h + max(0, rows - 1) * _GAP
        if self.height() != height:
            self.setFixedHeight(height)


class _SectionHeader(QWidget):
    """Bold section title with an optional count and a trailing "Show All" link."""

    def __init__(self, title: str, link_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(_M + 2, 0, _M - 2, 0)
        lay.setSpacing(8)
        self._title = QLabel(title)
        self._title.setFont(font("title2", weight=QFont.Weight.Bold, size=19))
        self._count = QLabel()
        self._count.setFont(font("title3", weight=QFont.Weight.Normal, size=15))
        lay.addWidget(self._title, 0, Qt.AlignmentFlag.AlignBaseline)
        lay.addWidget(self._count, 0, Qt.AlignmentFlag.AlignBaseline)
        lay.addStretch(1)
        self.link = actions.make_button(link_text, "plain")
        self.link.setVisible(bool(link_text))
        lay.addWidget(self.link, 0, Qt.AlignmentFlag.AlignBaseline)
        on_theme_change(self, self._apply_theme)

    def set_count(self, text: str) -> None:
        self._count.setText(text)

    def _apply_theme(self) -> None:
        pal = palette()
        self._title.setStyleSheet(f"color: {rgba(pal.label)};")
        self._count.setStyleSheet(f"color: {rgba(pal.tertiary_label)};")


# --------------------------------------------------------------------------- hero

class _Chip(QAbstractButton):
    """Pill-shaped suggestion button."""

    def __init__(self, icon: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon = icon
        self.setText(text)
        self.setFont(font("callout", weight=QFont.Weight.Medium))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedSize(self.sizeHint())
        on_theme_change(self, self.update, call_now=False)

    def sizeHint(self) -> QSize:
        return QSize(12 + 14 + 6 + math.ceil(QFontMetricsF(self.font()).horizontalAdvance(self.text())) + 14, 30)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        hover = self.underMouse()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if pal.dark:
            fill = with_alpha(pal.label, 46 if self.isDown() else 34 if hover else 22)
            border = with_alpha(pal.label, 28)
        else:
            fill = QColor(255, 255, 255, 255 if hover else 190)
            border = pal.group_border if not hover else pal.control_border
        if self.isDown():
            fill = mix(fill, pal.fill_pressed, 0.5) if not pal.dark else fill
        p.setPen(QPen(border, 1))
        p.setBrush(fill)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        tint = mix(pal.accent, system_color("indigo"), 0.35)
        icons.draw_icon(p, self._icon, QRectF(12, (self.height() - 14) / 2, 14, 14), tint)
        p.setFont(self.font())
        p.setPen(pal.label)
        p.drawText(QRectF(12 + 14 + 6, 0, self.width() - 32, self.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())


class _ChipRow(QWidget):
    """One line of chips; chips that don't fit are hidden rather than wrapped."""

    def __init__(self, chips: list[_Chip], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._chips = chips
        for c in chips:
            c.setParent(self)
        self.setFixedHeight(30)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(sum(c.width() for c in self._chips) + 8 * (len(self._chips) - 1), 30)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 30)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        x = 0
        for c in self._chips:
            fits = x + c.width() <= self.width()
            c.setVisible(fits)
            if fits:
                c.move(x, 0)
                x += c.width() + 8


class _SendButton(QAbstractButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("Ask the Assistant")
        self.active = False

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.active:
            color = pal.accent_pressed if self.isDown() else pal.accent_hover if self.underMouse() else pal.accent
            glyph = pal.on_accent
        else:
            color = pal.fill_hover if self.underMouse() else pal.fill
            glyph = pal.secondary_label
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(r)
        icons.draw_icon(p, "arrow_up", r.adjusted(7, 7, -7, -7), glyph, 1.15)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class _AskField(QLineEdit):
    """Pill-shaped "Ask the Assistant" field with a sparkles glyph and a round send button."""

    submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Ask the Assistant anything\u2026")
        self.setFont(font("message"))
        self.setFixedHeight(44)
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._send = _SendButton(self)
        self._send.clicked.connect(self._submit)
        self.returnPressed.connect(self._submit)
        self.textChanged.connect(self._on_text)
        on_theme_change(self, self._apply_theme)

    def _on_text(self, text: str) -> None:
        self._send.active = bool(text.strip())
        self._send.update()

    def _submit(self) -> None:
        text = self.text().strip()
        self.clear()
        self.submitted.emit(text)

    def _apply_theme(self) -> None:
        pal = palette()
        bg = pal.field if pal.dark else QColor(255, 255, 255)
        border = with_alpha(pal.label, 30) if pal.dark else pal.control_border
        self.setStyleSheet(
            f"QLineEdit {{ background: {rgba(bg)}; border: 1px solid {rgba(border)}; border-radius: 22px; "
            f"padding: 0 46px 0 42px; }}"
            f"QLineEdit:focus {{ border: 1px solid {rgba(with_alpha(pal.accent, 210))}; }}")
        self._send.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self.text():
            self.clear()
            return
        super().keyPressEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._send.move(self.width() - self._send.width() - 7, (self.height() - self._send.height()) // 2)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        pal = palette()
        tint = mix(pal.accent, system_color("purple"), 0.45)
        icons.draw_icon(p, "sparkles", QRectF(15, (self.height() - 18) / 2, 18, 18), tint)


class _Hero(_Card):
    """Greeting card with a soft blue-to-indigo tint, the Assistant field and suggestion chips."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(False, parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(_M + 28, _M + 26, _M + 28, _M + 24)
        lay.setSpacing(0)
        self.greeting = QLabel()
        self.greeting.setFont(font("large_title", size=28))
        self.subtitle = QLabel()
        self.subtitle.setFont(font("message"))
        self.subtitle.setWordWrap(True)
        lay.addWidget(self.greeting)
        lay.addSpacing(4)
        lay.addWidget(self.subtitle)
        lay.addSpacing(20)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.field = _AskField()
        self.field.setMaximumWidth(600)
        row.addWidget(self.field, 10)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(12)
        self.chips = [_Chip(icon, text) for icon, text in SUGGESTIONS]
        lay.addWidget(_ChipRow(self.chips))
        on_theme_change(self, self._apply_theme)

    def _apply_theme(self) -> None:
        pal = palette()
        self.greeting.setStyleSheet(f"color: {rgba(pal.label)};")
        self.subtitle.setStyleSheet(f"color: {rgba(pal.secondary_label)};")

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        pal = palette()
        path = icons.squircle_path(r, _RADIUS)
        blue, indigo, purple = system_color("blue"), system_color("indigo"), system_color("purple")
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        if pal.dark:
            g.setColorAt(0.0, with_alpha(blue, 74))
            g.setColorAt(0.55, with_alpha(indigo, 60))
            g.setColorAt(1.0, with_alpha(purple, 46))
        else:
            g.setColorAt(0.0, with_alpha(blue, 34))
            g.setColorAt(0.55, with_alpha(indigo, 26))
            g.setColorAt(1.0, with_alpha(purple, 22))
        p.fillPath(path, g)
        p.save()
        p.setClipPath(path)
        glow = QRadialGradient(QPointF(r.right() - r.width() * 0.12, r.top() + r.height() * 0.05), r.height() * 1.15)
        glow.setColorAt(0.0, with_alpha(system_color("cyan"), 56 if pal.dark else 44))
        glow.setColorAt(1.0, with_alpha(system_color("cyan"), 0))
        p.fillRect(r, glow)
        if r.width() > 760:
            side = min(120.0, r.height() * 0.55)
            gr = QRectF(r.right() - side - 44, r.top() + (r.height() - side) / 2 - 6, side, side)
            icons.draw_icon(p, "sparkles", gr, with_alpha(QColor(255, 255, 255) if pal.dark else indigo,
                                                          46 if pal.dark else 38))
        p.restore()


# --------------------------------------------------------------------------- stats and modules

class _StatTile(_Card):
    """Reminders-style tile: colored badge and big count on top, label and detail below."""

    HEIGHT = 96 + 2 * _M

    def __init__(self, icon: str, color: str, label: str, clickable: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(clickable, parent)
        self._icon, self._color, self._label = icon, color, label
        self._value = 0
        self._detail = ""
        self._f_value = font("large_title", size=28)
        self._f_label = font("headline")
        self._f_detail = font("subheadline")

    def set_value(self, value: int, detail: str = "") -> None:
        self._value, self._detail = value, detail
        self.update()

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        pal = palette()
        pad = 14
        badge = QRectF(r.left() + pad, r.top() + pad, 30, 30)
        _badge(p, badge, system_color(self._color), self._icon, circle=True)
        p.setFont(self._f_value)
        p.setPen(pal.label)
        p.drawText(QRectF(badge.right() + 8, r.top() + pad - 6, r.right() - pad - badge.right() - 8, 42),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, QLocale().toString(self._value))
        bottom = QRectF(r.left() + pad, r.bottom() - pad - 18, r.width() - 2 * pad, 18)
        p.setFont(self._f_label)
        p.setPen(pal.secondary_label)
        label_w = p.fontMetrics().horizontalAdvance(self._label)
        p.drawText(bottom, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)
        if self._detail:
            p.setFont(self._f_detail)
            p.setPen(pal.tertiary_label)
            avail = int(bottom.width() - label_w - 10)
            if avail > 24:
                p.drawText(bottom, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           p.fontMetrics().elidedText(self._detail, Qt.TextElideMode.ElideRight, avail))


class _ModuleCard(_Card):
    """Module summary: color badge, name, counts, two-line description, topic chips and a share bar."""

    HEIGHT = 166 + 2 * _M

    def __init__(self, module: Module, count: int, share: float, parent: QWidget | None = None) -> None:
        super().__init__(True, parent)
        self.module = module
        self._count = count
        self._share = share
        self._f_name = font("title3")
        self._f_meta = font("subheadline")
        self._f_desc = font("callout")
        self._f_chip = font("subheadline", weight=QFont.Weight.Medium)
        self._lines_key: tuple | None = None
        self._lines: list[str] = []
        self.setToolTip(module.description or module.name)

    def _desc_lines(self, width: float) -> list[str]:
        key = (self.module.description, int(width))
        if key != self._lines_key:
            self._lines_key = key
            self._lines = _elide_lines(self.module.description, self._f_desc, width, 2)
        return self._lines

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        pal = palette()
        m = self.module
        color = system_color(m.color)
        pad = 16
        badge = QRectF(r.left() + pad, r.top() + pad, 38, 38)
        _badge(p, badge, color, "folder_fill")
        chev = QRectF(r.right() - pad - 11, badge.center().y() - 5.5, 11, 11)
        icons.draw_icon(p, "chevron_right", chev, mix(pal.tertiary_label, pal.secondary_label, self._lift), 1.2)
        tx = badge.right() + 12
        tw = chev.left() - 8 - tx
        p.setFont(self._f_name)
        p.setPen(pal.label)
        p.drawText(QRectF(tx, badge.top(), tw, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(m.name, Qt.TextElideMode.ElideRight, int(tw)))
        meta = f"{actions.plural(self._count, 'resource')}  \u00b7  {actions.plural(len(m.topics), 'topic')}"
        p.setFont(self._f_meta)
        p.setPen(pal.secondary_label)
        p.drawText(QRectF(tx, badge.top() + 21, tw, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(meta, Qt.TextElideMode.ElideRight, int(tw)))

        x, w = r.left() + pad, r.width() - 2 * pad
        y = badge.bottom() + 12
        lh = QFontMetricsF(self._f_desc).lineSpacing() + 1
        p.setFont(self._f_desc)
        if m.description.strip():
            p.setPen(pal.secondary_label)
            for i, line in enumerate(self._desc_lines(w)):
                p.drawText(QRectF(x, y + i * lh, w, lh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           line)
        else:
            p.setPen(pal.tertiary_label)
            p.drawText(QRectF(x, y, w, lh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       "No description")

        bar_y = r.bottom() - pad - 4
        chip_y = bar_y - 14 - 22
        self._paint_chips(p, QRectF(x, chip_y, w, 22), color)
        track = QRectF(x, bar_y, w, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.fill)
        p.drawRoundedRect(track, 2, 2)
        if self._count > 0:
            filled = QRectF(track.left(), track.top(), max(track.height(), track.width() * self._share), 4)
            g = QLinearGradient(filled.topLeft(), filled.topRight())
            g.setColorAt(0.0, color.lighter(115))
            g.setColorAt(1.0, color)
            p.setBrush(g)
            p.drawRoundedRect(filled, 2, 2)

    def _paint_chips(self, p: QPainter, row: QRectF, color: QColor) -> None:
        pal = palette()
        topics = self.module.topics
        if not topics:
            p.setFont(self._f_meta)
            p.setPen(pal.tertiary_label)
            p.drawText(row, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "No topics yet")
            return
        p.setFont(self._f_chip)
        fm = p.fontMetrics()
        bg = with_alpha(color, 46 if pal.dark else 30)
        fg = color.lighter(135) if pal.dark else color.darker(135)
        x = row.left()
        shown = 0
        for t in topics[:3]:
            remaining = len(topics) - shown - 1
            more_w = fm.horizontalAdvance(f"+{remaining}") + 16 + 6 if remaining else 0
            avail = row.right() - x - more_w
            full_w = fm.horizontalAdvance(t.name) + 21
            if full_w > avail and (shown or avail < 64):
                break
            cw = min(full_w, avail)
            chip = QRectF(x, row.top(), cw, row.height())
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(chip, chip.height() / 2, chip.height() / 2)
            p.setPen(fg)
            p.drawText(chip.adjusted(9, 0, -9, 0), Qt.AlignmentFlag.AlignCenter,
                       fm.elidedText(t.name, Qt.TextElideMode.ElideRight, int(cw - 18)))
            x += cw + 6
            shown += 1
        rest = len(topics) - shown
        if rest > 0 and x + 30 <= row.right():
            text = f"+{rest}"
            chip = QRectF(x, row.top(), fm.horizontalAdvance(text) + 16, row.height())
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pal.fill)
            p.drawRoundedRect(chip, chip.height() / 2, chip.height() / 2)
            p.setPen(pal.secondary_label)
            p.drawText(chip, Qt.AlignmentFlag.AlignCenter, text)


# --------------------------------------------------------------------------- activity lists

class _Row(QWidget):
    """Hoverable list row inside a card, with an inset hairline separator."""

    clicked = Signal()
    HEIGHT = 52
    TEXT_X = 54

    def __init__(self, last: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._last = last
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._f_title = font("body", weight=QFont.Weight.Medium)
        self._f_meta = font("subheadline")
        on_theme_change(self, self.update, call_now=False)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        pal = palette()
        r = QRectF(self.rect())
        if self.underMouse():
            p.fillPath(icons.squircle_path(r.adjusted(0, 1, 0, -1), 9), pal.hover)
        elif not self._last:
            p.fillRect(QRectF(self.TEXT_X, r.bottom() - 0.5, r.width() - self.TEXT_X - 10, 0.5), pal.separator)
        self.paint_content(p, r)

    def _text(self, p: QPainter, r: QRectF, title: str, meta: str, dot: QColor | None, trailing: str) -> None:
        pal = palette()
        x = self.TEXT_X
        right = r.right() - 12
        p.setFont(self._f_meta)
        trail_w = p.fontMetrics().horizontalAdvance(trailing) + 12 if trailing else 0
        if trailing:
            p.setPen(pal.tertiary_label)
            p.drawText(QRectF(right - trail_w, r.top() + 9, trail_w, 18),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, trailing)
        w = right - trail_w - x
        p.setFont(self._f_title)
        p.setPen(pal.label)
        p.drawText(QRectF(x, r.top() + 9, w, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, int(w)))
        mx = x
        my = r.top() + 27
        if dot is not None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(dot)
            p.drawEllipse(QRectF(mx + 0.5, my + 8 - 3.5, 7, 7))
            mx += 13
        p.setFont(self._f_meta)
        p.setPen(pal.secondary_label)
        mw = right - mx
        p.drawText(QRectF(mx, my, mw, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(meta, Qt.TextElideMode.ElideRight, int(mw)))

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        pass


class _ResourceRow(_Row):
    def __init__(self, resource: Resource, module: Module | None, last: bool, parent: QWidget | None = None) -> None:
        super().__init__(last, parent)
        self.resource = resource
        self._module = module
        self.setToolTip(resource.filename)

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        res = self.resource
        icons.draw_file_icon(p, QRectF(12, (r.height() - 36) / 2, 36, 36), res.ext, palette().dark)
        module = self._module.name if self._module else "Unsorted"
        color = system_color(self._module.color) if self._module else system_color("gray")
        self._text(p, r, res.title or res.filename, f"{module}  \u00b7  {actions.relative_date(res.created_at)}",
                   color, actions.human_size(res.size))


class _ClassworkRow(_Row):
    HEIGHT = 56

    def __init__(self, entry: ClassworkEntry, module: Module | None, last: bool,
                 parent: QWidget | None = None) -> None:
        super().__init__(last, parent)
        self.entry = entry
        self._module = module
        self._day = actions.parse_iso(entry.date)
        if entry.description:
            self.setToolTip(entry.description)

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        draw_date_tile(p, QRectF(14, (r.height() - 38) / 2, 34, 38), self._day)
        m = self._module
        topic = m.topic(self.entry.topic_id) if m else None
        meta = (m.name if m else "Unsorted") + (f"  \u00b7  {topic.name}" if topic else "")
        self._text(p, r.adjusted(0, 2, 0, 0), self.entry.title, meta,
                   system_color(m.color) if m else system_color("gray"), _day_text(self._day))


class _ListCard(_Card):
    """Card holding a short list of rows, or a compact empty state."""

    action_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(False, parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(_M + 6, _M + 6, _M + 6, _M + 6)
        self._lay.setSpacing(0)
        self._rows: list[QWidget] = []
        self._empty = actions.EmptyState()
        self._empty.layout().setContentsMargins(16, 18, 16, 18)
        self._empty.action_clicked.connect(self.action_clicked)
        self._empty.hide()
        self._lay.addWidget(self._empty, 1)
        self._lay.addStretch(0)

    def set_rows(self, rows: list[QWidget]) -> None:
        for w in self._rows:
            w.hide()
            w.deleteLater()
        self._rows = rows
        for i, w in enumerate(rows):
            self._lay.insertWidget(i, w)
        self._empty.hide()

    def set_empty(self, icon: str, title: str, message: str, action_text: str = "") -> None:
        self.set_rows([])
        self._empty.set_content(icon, title, message, action_text)
        self._empty.show()


class _PairRow(QWidget):
    """Two equal columns side by side that stack vertically when the view is narrow."""

    BREAKPOINT = 680

    def __init__(self, left: QWidget, right: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._box.setSpacing(_GAP)
        self._box.addWidget(left, 1)
        self._box.addWidget(right, 1)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        wide = self.width() >= self.BREAKPOINT
        direction = QBoxLayout.Direction.LeftToRight if wide else QBoxLayout.Direction.TopToBottom
        if self._box.direction() != direction:
            self._box.setDirection(direction)
            self._box.setSpacing(_GAP if wide else 22)


def _column(header: _SectionHeader, body: QWidget) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lay.addWidget(header)
    lay.addWidget(body, 1)
    return w


class _LogClassworkButton(IconButton):
    """Toolbar button showing a calendar with a small plus badge cut into its corner."""

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        rect = QRectF(self.rect())
        plate = pal.fill_pressed if self.isDown() else with_alpha(pal.fill_hover,
                                                                 int(pal.fill_hover.alpha() * self._hover))
        if plate.alpha() > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(plate)
            p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        color = pal.tertiary_label if not self.isEnabled() else mix(pal.secondary_label, pal.label, self._hover * 0.6)
        s = self._icon_size
        dpr = self.devicePixelRatioF()
        pm = icons.icon_pixmap("calendar", color, s, dpr)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        badge = QRectF(s * 0.5, s * 0.5, s * 0.56, s * 0.56)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QColor(0, 0, 0))
        q.drawEllipse(badge.adjusted(-1.2, -1.2, 1.2, 1.2))
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        icons.draw_icon(q, "plus", badge.adjusted(0.5, 0.5, -0.5, -0.5), color, 1.3)
        q.end()
        p.drawPixmap(QPointF((rect.width() - s) / 2, (rect.height() - s) / 2), pm)


# --------------------------------------------------------------------------- view

class HomeView(QWidget):
    """Landing dashboard: greeting and Assistant prompt, stats, modules and recent activity."""

    navigate = Signal(str, object)
    open_resource_requested = Signal(str)
    add_resource_requested = Signal(object, list)
    log_classwork_requested = Signal(object)
    ask_assistant_requested = Signal(str)

    def __init__(self, library: Library, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library
        self.settings = settings
        self._mode = settings.mode() or MODE_INTERN
        self._dirty = False
        self._populated = False
        self._pending = QTimer(self, singleShot=True, interval=0)
        self._pending.timeout.connect(self.refresh)
        self._clock = QTimer(self, interval=60_000)
        self._clock.timeout.connect(self._update_clock)
        self._clock.start()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.toolbar = Toolbar("Home", self._date_text())
        self._log_btn = _LogClassworkButton("calendar", "Log Classwork\u2026")
        self._log_btn.clicked.connect(lambda: self.log_classwork_requested.emit(None))
        self._add_btn = IconButton("plus", "Add Resource\u2026")
        self._add_btn.clicked.connect(lambda: self.add_resource_requested.emit(None, []))
        self.toolbar.add_action(self._log_btn)
        self.toolbar.add_action(self._add_btn)
        root.addWidget(self.toolbar)

        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        canvas = _Canvas()
        outer = QHBoxLayout(canvas)
        outer.setContentsMargins(26 - _M, 22 - _M, 26 - _M, 30)
        outer.setSpacing(0)
        column = QWidget()
        column.setMaximumWidth(MAX_WIDTH + 2 * _M)
        column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        outer.addStretch(0)
        outer.addWidget(column, 1)
        outer.addStretch(0)
        self._scroll.setWidget(canvas)
        actions.smooth_scroll(self._scroll)
        root.addWidget(self._scroll, 1)

        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        self._hero = _Hero()
        self._hero.field.submitted.connect(self.ask_assistant_requested)
        for chip in self._hero.chips:
            chip.clicked.connect(lambda _=False, t=chip.text(): self.ask_assistant_requested.emit(t))
        col.addWidget(self._hero)
        col.addSpacing(_GAP)

        self._tiles = {
            "resources": _StatTile("books", "blue", "Resources", clickable=True),
            "modules": _StatTile("folder_fill", "orange", "Modules"),
            "classwork": _StatTile("calendar", "red", "Classwork", clickable=True),
            "keywords": _StatTile("tag", "purple", "Keywords"),
        }
        self._tiles["resources"].clicked.connect(lambda: self.navigate.emit("all", None))
        self._tiles["classwork"].clicked.connect(lambda: self.navigate.emit("classwork", None))
        self._tile_grid = _FlowGrid(_StatTile.HEIGHT, 150, (4, 2))
        self._tile_grid.set_items(list(self._tiles.values()))
        col.addWidget(self._tile_grid)
        col.addSpacing(26)

        self._modules_header = _SectionHeader("Modules")
        col.addWidget(self._modules_header)
        col.addSpacing(6)
        self._module_grid = _FlowGrid(_ModuleCard.HEIGHT, 230, (4, 3, 2))
        col.addWidget(self._module_grid)
        self._modules_empty = _ListCard()
        col.addWidget(self._modules_empty)
        col.addSpacing(26)

        self._recent_header = _SectionHeader("Recently Added", "Show All")
        self._recent_header.link.clicked.connect(lambda: self.navigate.emit("recent", None))
        self._recent = _ListCard()
        self._recent.action_clicked.connect(lambda: self.add_resource_requested.emit(None, []))
        self._classwork_header = _SectionHeader("Latest Classwork", "Show All")
        self._classwork_header.link.clicked.connect(lambda: self.navigate.emit("classwork", None))
        self._classwork = _ListCard()
        self._classwork.action_clicked.connect(lambda: self.log_classwork_requested.emit(None))
        col.addWidget(_PairRow(_column(self._recent_header, self._recent),
                               _column(self._classwork_header, self._classwork)))
        col.addStretch(1)

        library.changed.connect(lambda *_: self._pending.start())
        settings.changed.connect(lambda *_: self._update_hero())
        on_theme_change(self, self.update, call_now=False)
        self._apply_mode()
        self.refresh()

    # ------------------------------------------------------------------ public API
    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._apply_mode()
        self.refresh()

    def refresh(self) -> None:
        if not self.isVisible() and self._populated:
            self._dirty = True
            return
        self._dirty = False
        self._populated = True
        try:
            modules = self.library.modules()
            counts = self.library.counts()
            resources = self.library.resources()
            entries = self.library.classwork()
            keywords = self.library.all_keywords()
        except Exception:
            modules, counts, resources, entries, keywords = [], {}, [], [], []
        by_id = {m.id: m for m in modules}
        self._resource_total = counts.get("__all__", len(resources))
        self._update_clock()
        self._update_tiles(modules, resources, entries, keywords)
        self._update_modules(modules, counts)
        self._update_recent(resources, by_id)
        self._update_classwork(entries, by_id)

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _date_text() -> str:
        return QLocale().toString(QDate.currentDate(), "dddd, MMMM d")

    def _facilitator(self) -> bool:
        return self._mode == MODE_FACILITATOR

    def _apply_mode(self) -> None:
        self._log_btn.setVisible(self._facilitator())
        self._add_btn.setVisible(self._facilitator())

    def _update_clock(self) -> None:
        self.toolbar.set_title("Home", self._date_text())
        self._update_hero()

    def _update_hero(self) -> None:
        name = _display_name(self.settings.user_name())
        self._hero.greeting.setText(f"{_greeting()}, {name}" if name else _greeting())
        empty = getattr(self, "_resource_total", 0) == 0
        if self._facilitator():
            text = ("Your library is empty. Add your first resource to get started." if empty
                    else "Add materials, log today\u2019s class, or ask the Assistant for help.")
        else:
            text = ("Materials your facilitators add will appear here." if empty
                    else "Pick up where you left off, or ask the Assistant to explain a topic.")
        self._hero.subtitle.setText(text)

    def _update_tiles(self, modules: list[Module], resources: list[Resource], entries: list[ClassworkEntry],
                      keywords: list[str]) -> None:
        week_ago = time.time() - 7 * 86400
        new = sum(1 for r in resources if r.created_at >= week_ago)
        if new:
            res_detail = f"{new} this week"
        elif resources:
            res_detail = actions.human_size(sum(r.size for r in resources))
        else:
            res_detail = "None yet"
        self._tiles["resources"].set_value(len(resources), res_detail)
        topics = sum(len(m.topics) for m in modules)
        self._tiles["modules"].set_value(len(modules), actions.plural(topics, "topic"))
        latest = max(filter(None, (actions.parse_iso(e.date) for e in entries)), default=None)
        self._tiles["classwork"].set_value(len(entries), f"Latest: {_day_text(latest)}" if latest else "None yet")
        self._tiles["keywords"].set_value(len(keywords), f"Top: {keywords[0]}" if keywords else "None yet")

    def _update_modules(self, modules: list[Module], counts: dict[str, int]) -> None:
        top = max((counts.get(m.id, 0) for m in modules), default=0)
        cards = []
        for m in modules:
            n = counts.get(m.id, 0)
            card = _ModuleCard(m, n, n / top if top else 0.0)
            card.clicked.connect(lambda mid=m.id: self.navigate.emit("module", mid))
            cards.append(card)
        self._module_grid.set_items(cards)
        self._module_grid.setVisible(bool(cards))
        self._modules_header.set_count(str(len(modules)) if modules else "")
        if modules:
            self._modules_empty.hide()
        else:
            self._modules_empty.set_empty("folder", "No Modules",
                                          "Modules from the syllabus will appear here.")
            self._modules_empty.show()

    def _update_recent(self, resources: list[Resource], by_id: dict[str, Module]) -> None:
        latest = sorted(resources, key=lambda r: r.created_at, reverse=True)[:5]
        if not latest:
            if self._facilitator():
                self._recent.set_empty("tray_down", "No Resources Yet",
                                       "Notes, slides and exercises you add will show up here.",
                                       "Add your first resource")
            else:
                self._recent.set_empty("tray_down", "No Resources Yet",
                                       "Materials your facilitators add will show up here.")
            self._recent_header.link.hide()
            return
        rows = []
        for i, r in enumerate(latest):
            row = _ResourceRow(r, by_id.get(r.module_id), i == len(latest) - 1)
            row.clicked.connect(lambda rid=r.id: self.open_resource_requested.emit(rid))
            rows.append(row)
        self._recent.set_rows(rows)
        self._recent_header.link.show()

    def _update_classwork(self, entries: list[ClassworkEntry], by_id: dict[str, Module]) -> None:
        latest = sorted(entries, key=lambda e: (e.date or "", e.created_at), reverse=True)[:4]
        if not latest:
            if self._facilitator():
                self._classwork.set_empty("calendar", "No Classwork Yet",
                                          "Log a class session to build the timeline.", "Log Classwork\u2026")
            else:
                self._classwork.set_empty("calendar", "No Classwork Yet",
                                          "Sessions your facilitators log will appear here.")
            self._classwork_header.link.hide()
            return
        rows = []
        for i, e in enumerate(latest):
            row = _ClassworkRow(e, by_id.get(e.module_id), i == len(latest) - 1)
            row.clicked.connect(lambda: self.navigate.emit("classwork", None))
            rows.append(row)
        self._classwork.set_rows(rows)
        self._classwork_header.link.show()

    def showEvent(self, e):
        super().showEvent(e)
        if self._dirty:
            self.refresh()
        else:
            self._update_clock()

    def paintEvent(self, _):
        QPainter(self).fillRect(self.rect(), _canvas_color())
