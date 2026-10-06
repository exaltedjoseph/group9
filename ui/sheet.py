"""macOS sheet overlay and System Settings-style grouped form rows."""
# TODO(branch1): implement design system and shared controls.
from __future__ import annotations
import shiboken6
from PySide6.QtCore import QEasingCurve, QEvent, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLayout, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout, QWidget
from .. import icons
from ..theme import font, palette, rgba, with_alpha
from .controls import make_button, on_theme_change
TOOLBAR_HEIGHT = 52
_SHADOW = 28
_RADIUS = 12

class _Card(QWidget):
    """Sheet card: rounded squircle with a soft shadow painted around it."""

    def paintEvent(self, _):
        ...

class Sheet(QWidget):
    """Modal sheet over `host`: dims it and presents a card with title, scrollable body and footer.

    Subclasses add widgets to `self.body_layout` and buttons via `add_footer_buttons()`.
    """
    accepted = Signal()
    closed = Signal()

    def __init__(self, host: QWidget, title: str='', width: int=520) -> None:
        ...

    def set_title(self, title: str, subtitle: str='') -> None:
        ...

    def add_footer_buttons(self, primary: str, secondary: str | None='Cancel', leading: QWidget | None=None, destructive: bool=False) -> tuple[QPushButton, QPushButton | None]:
        """Right-aligned [secondary] [primary] buttons, optional `leading` widget on the left."""
        ...

    def open(self) -> None:
        ...

    def close_sheet(self, accepted: bool=False) -> None:
        ...

    def accept(self) -> None:
        ...

    def on_open(self) -> None:
        """Called right after the sheet starts opening (load current values here)."""
        ...

    def _apply_theme(self) -> None:
        ...

    def _start_fade(self) -> None:
        ...

    def _animate(self, target: float, duration: int, curve: QEasingCurve.Type) -> None:
        ...

    def _on_progress(self, v) -> None:
        ...

    def _on_anim_done(self) -> None:
        ...

    def relayout(self) -> None:
        """Re-fit the card after rows inside the body are shown or hidden."""
        ...

    def _layout_card(self) -> None:
        ...

    def eventFilter(self, obj, event):
        ...

    def paintEvent(self, _):
        ...

    def mousePressEvent(self, e):
        ...

    def keyPressEvent(self, e):
        ...

class GroupBox(QWidget):
    """Rounded inset group of rows separated by hairlines (macOS System Settings)."""

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def add_row(self, label: str | None, control: QWidget | QLayout | None=None, *, description: str='', icon: str | None=None, icon_color: QColor | None=None, stacked: bool=False) -> QWidget:
        """Add a row: label (+ optional description/icon) on the left, `control` on the right.

        `stacked=True` places the control below the label at full width (for text areas).
        `label=None` gives the control the whole row.
        """
        ...

    def paintEvent(self, _):
        ...

def _style_row_labels(row: QWidget) -> None:
    ...

class SymbolBadge(QWidget):
    """System Settings style icon: white glyph on a colored rounded square."""

    def __init__(self, icon: str, color: QColor, size: int=22, parent: QWidget | None=None) -> None:
        ...

    def set_color(self, color: QColor) -> None:
        ...

    def paintEvent(self, _):
        ...

def section_header(text: str) -> QLabel:
    """Bold header placed above a GroupBox."""
    ...

def footnote(text: str, rich: bool=False) -> QLabel:
    """Small secondary explanatory text placed under a GroupBox."""
    ...
