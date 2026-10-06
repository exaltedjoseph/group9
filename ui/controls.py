"""Reusable macOS-style controls shared by every screen."""
# TODO(branch1): implement design system and shared controls.
from __future__ import annotations
import math
from typing import Callable
import shiboken6
from PySide6.QtCore import Property, QEasingCurve, QEvent, QObject, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QApplication, QFrame, QGraphicsDropShadowEffect, QLineEdit, QPushButton, QSizePolicy, QWidget
from .. import icons
from ..theme import font, palette, theme, with_alpha

def on_theme_change(widget: QWidget, callback: Callable[[], None], call_now: bool=True) -> None:
    """Run `callback` whenever the theme changes (and once immediately)."""
    ...

def _safe_disconnect(handler) -> None:
    ...

class _PopupStyler(QObject):
    """Makes combo box pop-up windows frameless and transparent so only the rounded list shows."""

    def eventFilter(self, obj, event):
        ...
_popup_styler: _PopupStyler | None = None

def install_popup_styling(app: QApplication) -> None:
    ...

def make_button(text: str, variant: str='secondary', large: bool=False) -> QPushButton:
    """QPushButton styled by the global QSS. variant: secondary | primary | destructive | plain."""
    ...

def mix(a: QColor, b: QColor, t: float) -> QColor:
    ...

class IconButton(QAbstractButton):
    """Borderless toolbar button with an SF-style glyph and a rounded hover plate."""

    def __init__(self, icon_name: str, tooltip: str='', size: int=28, icon_size: int=17, parent: QWidget | None=None, weight: float=1.0) -> None:
        ...

    def setIconName(self, name: str) -> None:
        ...

    def iconName(self) -> str:
        ...

    def setColor(self, color: QColor | None) -> None:
        """Override the glyph color (default: secondary label)."""
        ...

    def _set_hover(self, v) -> None:
        ...

    def _animate(self, target: float) -> None:
        ...

    def enterEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def sizeHint(self) -> QSize:
        ...

    def paintEvent(self, _):
        ...

class SearchField(QLineEdit):
    """Rounded macOS search field with a magnifying glass and a clear button."""

    def __init__(self, placeholder: str='Search', parent: QWidget | None=None) -> None:
        ...

    def _on_clear(self) -> None:
        ...

    def _apply_theme(self) -> None:
        ...

    def resizeEvent(self, e):
        ...

    def keyPressEvent(self, e):
        ...

    def paintEvent(self, e):
        ...

class Switch(QAbstractButton):
    """macOS toggle switch with an animated knob."""

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def _get_knob(self) -> float:
        ...

    def _set_knob(self, v: float) -> None:
        ...
    knob = Property(float, _get_knob, _set_knob)

    def _on_toggled(self, on: bool) -> None:
        ...

    def setChecked(self, on: bool) -> None:
        ...

    def sizeHint(self) -> QSize:
        ...

    def paintEvent(self, _):
        ...

class SegmentedControl(QWidget):
    """macOS segmented control with a sliding selection plate."""
    currentChanged = Signal(int)

    def __init__(self, segments: list[str], parent: QWidget | None=None) -> None:
        ...

    def _on_anim(self, v) -> None:
        ...

    def currentIndex(self) -> int:
        ...

    def setCurrentIndex(self, index: int, animate: bool=False) -> None:
        ...

    def sizeHint(self) -> QSize:
        ...

    def _seg_width(self) -> float:
        ...

    def _index_at(self, x: float) -> int:
        ...

    def mouseMoveEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def mouseReleaseEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

class Separator(QWidget):
    """Hairline separator using the system separator color."""

    def __init__(self, vertical: bool=False, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class ActivityIndicator(QWidget):
    """The classic macOS spinning "spokes" activity indicator."""

    def __init__(self, size: int=16, parent: QWidget | None=None) -> None:
        ...

    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def _tick(self) -> None:
        ...

    def paintEvent(self, _):
        ...

def add_shadow(widget: QWidget, blur: int=30, y: int=8, alpha: int | None=None) -> QGraphicsDropShadowEffect:
    """Soft macOS-like drop shadow."""
    ...

def rounded_path(rect: QRectF, radius: float, continuous: bool=True) -> QPainterPath:
    ...
