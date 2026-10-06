"""Reusable macOS-style controls shared by every screen."""
from __future__ import annotations

import math
from typing import Callable

import shiboken6
from PySide6.QtCore import (Property, QEasingCurve, QEvent, QObject, QPointF, QPropertyAnimation, QRectF,
                            QSize, Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QApplication, QFrame, QGraphicsDropShadowEffect, QLineEdit,
                               QPushButton, QSizePolicy, QWidget)

from .. import icons
from ..theme import font, palette, theme, with_alpha


def on_theme_change(widget: QWidget, callback: Callable[[], None], call_now: bool = True) -> None:
    """Run `callback` whenever the theme changes (and once immediately)."""

    def handler() -> None:
        if shiboken6.isValid(widget):
            callback()

    theme().changed.connect(handler)
    widget.destroyed.connect(lambda *_: _safe_disconnect(handler))
    if call_now:
        callback()


def _safe_disconnect(handler) -> None:
    try:
        theme().changed.disconnect(handler)
    except Exception:
        pass


class _PopupStyler(QObject):
    """Makes combo box pop-up windows frameless and transparent so only the rounded list shows."""

    def eventFilter(self, obj, event):  # noqa: N802
        kind = event.type()
        if kind not in (QEvent.Type.Polish, QEvent.Type.Paint) or not isinstance(obj, QWidget) \
                or obj.metaObject().className() != "QComboBoxPrivateContainer":
            return False
        if kind == QEvent.Type.Paint:
            pal = palette()
            p = QPainter(obj)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(pal.menu_border, 1))
            p.setBrush(pal.menu)
            p.drawRoundedRect(QRectF(obj.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
            p.end()
            return True
        if not obj.property("_appleStyled"):
            obj.setProperty("_appleStyled", True)
            obj.setWindowFlags(obj.windowFlags() | Qt.WindowType.FramelessWindowHint
                               | Qt.WindowType.NoDropShadowWindowHint)
            obj.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            if isinstance(obj, QFrame):
                obj.setFrameShape(QFrame.Shape.NoFrame)
        return False


_popup_styler: _PopupStyler | None = None


def install_popup_styling(app: QApplication) -> None:
    global _popup_styler
    if _popup_styler is None:
        _popup_styler = _PopupStyler(app)
        app.installEventFilter(_popup_styler)


def make_button(text: str, variant: str = "secondary", large: bool = False) -> QPushButton:
    """QPushButton styled by the global QSS. variant: secondary | primary | destructive | plain."""
    btn = QPushButton(text)
    if variant != "secondary":
        btn.setProperty("variant", variant)
    if large and variant == "secondary":
        btn.setProperty("variant", "large")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFont(font("body", size=13 if not large else 14))
    btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    return btn


def mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


# --------------------------------------------------------------------------- IconButton

class IconButton(QAbstractButton):
    """Borderless toolbar button with an SF-style glyph and a rounded hover plate."""

    def __init__(self, icon_name: str, tooltip: str = "", size: int = 28, icon_size: int = 17,
                 parent: QWidget | None = None, weight: float = 1.0) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_size = icon_size
        self._weight = weight
        self._hover = 0.0
        self._color: QColor | None = None
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if tooltip:
            self.setToolTip(tooltip)
        self._anim = QVariantAnimation(self, duration=140, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_hover)
        theme().changed.connect(self.update)

    def setIconName(self, name: str) -> None:  # noqa: N802 (Qt naming)
        self._icon_name = name
        self.update()

    def iconName(self) -> str:  # noqa: N802
        return self._icon_name

    def setColor(self, color: QColor | None) -> None:  # noqa: N802
        """Override the glyph color (default: secondary label)."""
        self._color = color
        self.update()

    def _set_hover(self, v) -> None:
        self._hover = float(v)
        self.update()

    def _animate(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, e):
        self._animate(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate(0.0)
        super().leaveEvent(e)

    def sizeHint(self) -> QSize:
        return self.size()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        rect = QRectF(self.rect())
        if self.isEnabled():
            plate = pal.fill_pressed if self.isDown() else with_alpha(pal.fill_hover, int(pal.fill_hover.alpha() * self._hover))
            if self.isChecked():
                plate = pal.fill_hover
            if plate.alpha() > 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(plate)
                p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        if not self.isEnabled():
            color = pal.tertiary_label
        elif self._color is not None:
            color = self._color
        elif self.isChecked():
            color = pal.accent
        else:
            color = mix(pal.secondary_label, pal.label, self._hover * 0.6)
        s = self._icon_size
        icon_rect = QRectF((rect.width() - s) / 2, (rect.height() - s) / 2, s, s)
        icons.draw_icon(p, self._icon_name, icon_rect, color, self._weight)


# --------------------------------------------------------------------------- SearchField

class SearchField(QLineEdit):
    """Rounded macOS search field with a magnifying glass and a clear button."""

    def __init__(self, placeholder: str = "Search", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setFont(font("body"))
        self.setFixedHeight(28)
        self.setClearButtonEnabled(False)
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        self._clear = IconButton("xmark_circle_fill", "Clear", 20, 14, self)
        self._clear.setCursor(Qt.CursorShape.ArrowCursor)
        self._clear.clicked.connect(self._on_clear)
        self._clear.hide()
        self.textChanged.connect(lambda t: self._clear.setVisible(bool(t)))
        on_theme_change(self, self._apply_theme)

    def _on_clear(self) -> None:
        self.clear()
        self.setFocus()

    def _apply_theme(self) -> None:
        pal = palette()
        self._clear.setColor(pal.tertiary_label)
        self.setStyleSheet(
            f"QLineEdit {{ background: rgba({pal.search_field.red()}, {pal.search_field.green()}, "
            f"{pal.search_field.blue()}, {pal.search_field.alpha()}); border: 1px solid transparent; "
            f"border-radius: 7px; padding: 0 26px 0 27px; }}"
            f"QLineEdit:focus {{ border: 1px solid rgba({pal.accent.red()}, {pal.accent.green()}, "
            f"{pal.accent.blue()}, 200); }}"
        )

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._clear.move(self.width() - self._clear.width() - 4, (self.height() - self._clear.height()) // 2)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self.text():
            self.clear()
            return
        super().keyPressEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        icons.draw_icon(p, "search", QRectF(9, (self.height() - 14) / 2, 14, 14), palette().secondary_label)


# --------------------------------------------------------------------------- Switch

class Switch(QAbstractButton):
    """macOS toggle switch with an animated knob."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(38, 22)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._on_toggled)
        theme().changed.connect(self.update)

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _on_toggled(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on: bool) -> None:  # noqa: N802 - jump without animation
        super().setChecked(on)
        self._anim.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(38, 22)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        off = pal.fill_pressed if pal.dark else QColor(0, 0, 0, 30)
        track = mix(off, pal.accent, self._pos)
        if not self.isEnabled():
            track = with_alpha(track, track.alpha() // 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 3
        x = r.left() + 1.5 + (r.width() - d - 3) * self._pos
        knob = QRectF(x, r.top() + 1.5, d, d)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(knob.translated(0, 0.6))
        p.setBrush(QColor("#FFFFFF") if self.isEnabled() else QColor(245, 245, 245))
        p.drawEllipse(knob)


# --------------------------------------------------------------------------- SegmentedControl

class SegmentedControl(QWidget):
    """macOS segmented control with a sliding selection plate."""

    currentChanged = Signal(int)

    def __init__(self, segments: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._segments = list(segments)
        self._index = 0
        self._plate_x = 0.0
        self._hover = -1
        self.setFont(font("body"))
        self.setFixedHeight(26)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._anim = QVariantAnimation(self, duration=200, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        theme().changed.connect(self.update)

    def _on_anim(self, v) -> None:
        self._plate_x = float(v)
        self.update()

    def currentIndex(self) -> int:  # noqa: N802
        return self._index

    def setCurrentIndex(self, index: int, animate: bool = False) -> None:  # noqa: N802
        index = max(0, min(index, len(self._segments) - 1))
        if index == self._index and not animate:
            self._plate_x = float(index)
            self.update()
            return
        self._anim.stop()
        if animate:
            self._anim.setStartValue(self._plate_x)
            self._anim.setEndValue(float(index))
            self._anim.start()
        else:
            self._plate_x = float(index)
        changed = index != self._index
        self._index = index
        self.update()
        if changed:
            self.currentChanged.emit(index)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        w = max(fm.horizontalAdvance(s) for s in self._segments) + 28
        return QSize(w * len(self._segments) + 4, 26)

    def _seg_width(self) -> float:
        return (self.width() - 4) / max(1, len(self._segments))

    def _index_at(self, x: float) -> int:
        return max(0, min(len(self._segments) - 1, int((x - 2) // self._seg_width())))

    def mouseMoveEvent(self, e):
        i = self._index_at(e.position().x())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.setCurrentIndex(self._index_at(e.position().x()), animate=True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.fill)
        p.drawRoundedRect(r, 7, 7)
        sw = self._seg_width()
        # dividers between unselected segments
        p.setPen(QPen(pal.separator, 1))
        for i in range(1, len(self._segments)):
            if abs(i - self._plate_x) > 0.6 and abs(i - 1 - self._plate_x) > 0.6:
                x = 2 + sw * i
                p.drawLine(QPointF(x, 7), QPointF(x, self.height() - 7))
        plate = QRectF(2 + sw * self._plate_x, 2, sw, self.height() - 4)
        p.setPen(QPen(QColor(0, 0, 0, 20 if not pal.dark else 0), 0.5))
        p.setBrush(QColor(0, 0, 0, 22 if not pal.dark else 60))
        p.drawRoundedRect(plate.translated(0, 0.5), 5.5, 5.5)
        p.setBrush(pal.segment_selected)
        p.drawRoundedRect(plate, 5.5, 5.5)
        for i, text in enumerate(self._segments):
            seg = QRectF(2 + sw * i, 0, sw, self.height())
            selected = i == self._index
            p.setFont(font("body", weight=font("headline").weight() if selected else None))
            p.setPen(pal.label if selected or i == self._hover else pal.secondary_label)
            p.drawText(seg, Qt.AlignmentFlag.AlignCenter, text)


# --------------------------------------------------------------------------- Separator

class Separator(QWidget):
    """Hairline separator using the system separator color."""

    def __init__(self, vertical: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vertical = vertical
        if vertical:
            self.setFixedWidth(1)
        else:
            self.setFixedHeight(1)
        theme().changed.connect(self.update)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), palette().separator)


# --------------------------------------------------------------------------- ActivityIndicator

class ActivityIndicator(QWidget):
    """The classic macOS spinning "spokes" activity indicator."""

    def __init__(self, size: int = 16, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._step = 0
        self._timer = QTimer(self, interval=80)
        self._timer.timeout.connect(self._tick)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def start(self) -> None:
        self.show()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._step = (self._step + 1) % 12
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = palette().secondary_label
        c = QPointF(self.width() / 2, self.height() / 2)
        outer = self.width() / 2
        inner = outer * 0.45
        width = max(1.4, self.width() / 11)
        for i in range(12):
            alpha = 1.0 - ((i - self._step) % 12) / 12.0
            col = with_alpha(base, int(255 * (0.15 + 0.85 * alpha) * base.alphaF()))
            p.setPen(QPen(col, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            a = math.radians(i * 30 - 90)
            p.drawLine(QPointF(c.x() + inner * math.cos(a), c.y() + inner * math.sin(a)),
                       QPointF(c.x() + (outer - width / 2) * math.cos(a), c.y() + (outer - width / 2) * math.sin(a)))


# --------------------------------------------------------------------------- shadows

def add_shadow(widget: QWidget, blur: int = 30, y: int = 8, alpha: int | None = None) -> QGraphicsDropShadowEffect:
    """Soft macOS-like drop shadow."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)

    def apply():
        c = QColor(palette().shadow)
        if alpha is not None:
            c.setAlpha(alpha if not palette().dark else min(255, alpha * 2))
        effect.setColor(c)

    on_theme_change(widget, apply)
    widget.setGraphicsEffect(effect)
    return effect


def rounded_path(rect: QRectF, radius: float, continuous: bool = True) -> QPainterPath:
    if continuous:
        return icons.squircle_path(rect, radius)
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path
