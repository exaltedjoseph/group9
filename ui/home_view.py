"""Home dashboard: greeting with an Assistant prompt, library stats, module cards and recent activity."""
# TODO(branch5): implement the app shell, Home dashboard and actions.
from __future__ import annotations
import math
import time
from datetime import date, datetime
from PySide6.QtCore import QDate, QEasingCurve, QLocale, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QAbstractButton, QBoxLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
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
_M = 5
_GAP = 6
_RADIUS = 14.0
SUGGESTIONS = (('branch', 'Explain Git branching'), ('checklist', 'Quiz me on Python loops'), ('calendar', 'Summarize this week’s classwork'))

def _canvas_color() -> QColor:
    ...

def _day_text(d: date | None) -> str:
    ...

def _greeting() -> str:
    ...

def _display_name(name: str) -> str:
    ...

def _elide_lines(text: str, f: QFont, width: float, limit: int) -> list[str]:
    ...

def _badge(p: QPainter, rect: QRectF, color: QColor, glyph: str, circle: bool=False) -> None:
    """Colored SF-style symbol badge with a soft top-to-bottom sheen and a white glyph."""
    ...

class _Card(QWidget):
    """Rounded widget card with a soft shadow; clickable cards lift slightly on hover."""
    clicked = Signal()

    def __init__(self, clickable: bool=False, parent: QWidget | None=None) -> None:
        ...

    def set_clickable(self, on: bool) -> None:
        ...

    def _set_lift(self, v) -> None:
        ...

    def _animate(self, target: float) -> None:
        ...

    def enterEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def mousePressEvent(self, e):
        ...

    def mouseReleaseEvent(self, e):
        ...

    def card_rect(self) -> QRectF:
        ...

    def paintEvent(self, _):
        ...

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        ...

class _Canvas(QWidget):

    def paintEvent(self, _):
        ...

class _FlowGrid(QWidget):
    """Equal-width grid of fixed-height children; picks the largest allowed column count that fits."""

    def __init__(self, item_height: int, min_item_width: int, columns: tuple[int, ...], parent: QWidget | None=None) -> None:
        ...

    def set_items(self, widgets: list[QWidget]) -> None:
        ...

    def items(self) -> list[QWidget]:
        ...

    def resizeEvent(self, e):
        ...

    def _relayout(self) -> None:
        ...

class _SectionHeader(QWidget):
    """Bold section title with an optional count and a trailing "Show All" link."""

    def __init__(self, title: str, link_text: str='', parent: QWidget | None=None) -> None:
        ...

    def set_count(self, text: str) -> None:
        ...

    def _apply_theme(self) -> None:
        ...

class _Chip(QAbstractButton):
    """Pill-shaped suggestion button."""

    def __init__(self, icon: str, text: str, parent: QWidget | None=None) -> None:
        ...

    def sizeHint(self) -> QSize:
        ...

    def enterEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

class _ChipRow(QWidget):
    """One line of chips; chips that don't fit are hidden rather than wrapped."""

    def __init__(self, chips: list[_Chip], parent: QWidget | None=None) -> None:
        ...

    def sizeHint(self) -> QSize:
        ...

    def minimumSizeHint(self) -> QSize:
        ...

    def resizeEvent(self, e):
        ...

class _SendButton(QAbstractButton):

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

    def enterEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

class _AskField(QLineEdit):
    """Pill-shaped "Ask the Assistant" field with a sparkles glyph and a round send button."""
    submitted = Signal(str)

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def _on_text(self, text: str) -> None:
        ...

    def _submit(self) -> None:
        ...

    def _apply_theme(self) -> None:
        ...

    def keyPressEvent(self, e):
        ...

    def resizeEvent(self, e):
        ...

    def paintEvent(self, e):
        ...

class _Hero(_Card):
    """Greeting card with a soft blue-to-indigo tint, the Assistant field and suggestion chips."""

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def _apply_theme(self) -> None:
        ...

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        ...

class _StatTile(_Card):
    """Reminders-style tile: colored badge and big count on top, label and detail below."""
    HEIGHT = 96 + 2 * _M

    def __init__(self, icon: str, color: str, label: str, clickable: bool=False, parent: QWidget | None=None) -> None:
        ...

    def set_value(self, value: int, detail: str='') -> None:
        ...

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        ...

class _ModuleCard(_Card):
    """Module summary: color badge, name, counts, two-line description, topic chips and a share bar."""
    HEIGHT = 166 + 2 * _M

    def __init__(self, module: Module, count: int, share: float, parent: QWidget | None=None) -> None:
        ...

    def _desc_lines(self, width: float) -> list[str]:
        ...

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        ...

    def _paint_chips(self, p: QPainter, row: QRectF, color: QColor) -> None:
        ...

class _Row(QWidget):
    """Hoverable list row inside a card, with an inset hairline separator."""
    clicked = Signal()
    HEIGHT = 52
    TEXT_X = 54

    def __init__(self, last: bool, parent: QWidget | None=None) -> None:
        ...

    def enterEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def mouseReleaseEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

    def _text(self, p: QPainter, r: QRectF, title: str, meta: str, dot: QColor | None, trailing: str) -> None:
        ...

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        ...

class _ResourceRow(_Row):

    def __init__(self, resource: Resource, module: Module | None, last: bool, parent: QWidget | None=None) -> None:
        ...

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        ...

class _ClassworkRow(_Row):
    HEIGHT = 56

    def __init__(self, entry: ClassworkEntry, module: Module | None, last: bool, parent: QWidget | None=None) -> None:
        ...

    def paint_content(self, p: QPainter, r: QRectF) -> None:
        ...

class _ListCard(_Card):
    """Card holding a short list of rows, or a compact empty state."""
    action_clicked = Signal()

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def set_rows(self, rows: list[QWidget]) -> None:
        ...

    def set_empty(self, icon: str, title: str, message: str, action_text: str='') -> None:
        ...

class _PairRow(QWidget):
    """Two equal columns side by side that stack vertically when the view is narrow."""
    BREAKPOINT = 680

    def __init__(self, left: QWidget, right: QWidget, parent: QWidget | None=None) -> None:
        ...

    def resizeEvent(self, e):
        ...

def _column(header: _SectionHeader, body: QWidget) -> QWidget:
    ...

class _LogClassworkButton(IconButton):
    """Toolbar button showing a calendar with a small plus badge cut into its corner."""

    def paintEvent(self, _):
        ...

class HomeView(QWidget):
    """Landing dashboard: greeting and Assistant prompt, stats, modules and recent activity."""
    navigate = Signal(str, object)
    open_resource_requested = Signal(str)
    add_resource_requested = Signal(object, list)
    log_classwork_requested = Signal(object)
    ask_assistant_requested = Signal(str)

    def __init__(self, library: Library, settings: Settings, parent: QWidget | None=None) -> None:
        ...

    def set_mode(self, mode: str) -> None:
        ...

    def refresh(self) -> None:
        ...

    @staticmethod
    def _date_text() -> str:
        ...

    def _facilitator(self) -> bool:
        ...

    def _apply_mode(self) -> None:
        ...

    def _update_clock(self) -> None:
        ...

    def _update_hero(self) -> None:
        ...

    def _update_tiles(self, modules: list[Module], resources: list[Resource], entries: list[ClassworkEntry], keywords: list[str]) -> None:
        ...

    def _update_modules(self, modules: list[Module], counts: dict[str, int]) -> None:
        ...

    def _update_recent(self, resources: list[Resource], by_id: dict[str, Module]) -> None:
        ...

    def _update_classwork(self, entries: list[ClassworkEntry], by_id: dict[str, Module]) -> None:
        ...

    def showEvent(self, e):
        ...

    def paintEvent(self, _):
        ...
