"""macOS source-list sidebar: search, library sections, modules and the mode switcher."""
# TODO(branch5): implement the app shell, Home dashboard and actions.
from __future__ import annotations
import math
import sqlite3
from dataclasses import dataclass, field
from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
from .. import icons
from ..constants import APP_NAME, MODE_FACILITATOR, MODE_INTERN
from ..core.library import LibraryError
from ..core.settings import KEY_USER_NAME
from ..theme import font, palette, rgba, system_color, theme, with_alpha
from .controls import IconButton, SearchField, mix, on_theme_change
HEADER_HEIGHT = 52
FOOTER_HEIGHT = 48
ROW_HEIGHT = 28
SECTION_HEIGHT = 26
SECTION_GAP = 10
INSET = 8
SEARCH_DEBOUNCE_MS = 200
_COLLAPSED_KEY = 'sidebar_collapsed'
_NAV_KINDS = ('home', 'assistant', 'all', 'recent', 'classwork', 'history', 'module')
_MODE_INFO = {MODE_FACILITATOR: ('Facilitator', 'person', 'blue'), MODE_INTERN: ('Intern', 'graduationcap', 'green')}

def popup_menu(parent: QWidget) -> QMenu:
    """QMenu with rounded translucent corners (styled by the global QSS)."""
    ...

def _check_icon(checked: bool) -> QIcon:
    """Menu checkmark that turns white on the highlighted item (blank when unchecked)."""
    ...

@dataclass
class _Row:
    kind: str
    arg: object = None
    title: str = ''
    icon: str = ''
    color: str | None = None
    count: int = 0

    @property
    def key(self) -> tuple[str, object]:
        ...

    @property
    def selectable(self) -> bool:
        ...

@dataclass
class _Section:
    key: str
    title: str
    rows: list[_Row] = field(default_factory=list)

class _SourceList(QWidget):
    """Custom-painted list of collapsible sections with selectable rows."""
    activated = Signal(object)
    menu_requested = Signal(object, QPoint)
    collapse_changed = Signal()

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def set_sections(self, sections: list[_Section]) -> None:
        ...

    def set_selected(self, key: tuple[str, object] | None) -> None:
        ...

    def selected(self) -> tuple[str, object] | None:
        ...

    def set_context(self, key: tuple[str, object] | None) -> None:
        ...

    def has(self, key: tuple[str, object]) -> bool:
        ...

    def collapsed(self) -> set[str]:
        ...

    def set_collapsed(self, keys: set[str]) -> None:
        ...

    def set_edit_visible(self, visible: bool) -> None:
        ...

    def toggle_section(self, key: str) -> None:
        ...

    def _set_factor(self, key: str, value: float) -> None:
        ...

    def _relayout(self) -> None:
        ...

    def _place_edit_button(self) -> None:
        ...

    def resizeEvent(self, e):
        ...

    def _hit(self, pos: QPointF) -> tuple[str, _Section, _Row | None] | None:
        ...

    def _row_rect(self, key: tuple[str, object]) -> QRectF | None:
        ...

    def _navigable(self) -> list[_Row]:
        ...

    def ensure_visible(self, key: tuple[str, object]) -> None:
        ...

    def paintEvent(self, _):
        ...

    def _paint_header(self, p: QPainter, s: _Section, rect: QRectF) -> None:
        ...

    def _paint_row(self, p: QPainter, row: _Row, rect: QRectF, active: bool) -> None:
        ...

    def event(self, e):
        ...

    def mousePressEvent(self, e):
        ...

    def mouseMoveEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def contextMenuEvent(self, e):
        ...

    def keyPressEvent(self, e):
        ...

    def focusInEvent(self, e):
        ...

    def focusOutEvent(self, e):
        ...

class _ModeButton(QAbstractButton):
    """Account-style pop-up button: colored badge, mode name and the user's name."""

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def set_info(self, mode: str, user_name: str) -> None:
        ...

    def sizeHint(self) -> QSize:
        ...

    def _set_hover(self, v) -> None:
        ...

    def _animate(self, target: float) -> None:
        ...

    def enterEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

class _Footer(QWidget):

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class Sidebar(QWidget):
    """Finder-style source list with search, library sections, modules and a mode switcher."""
    navigate = Signal(str, object)
    search_changed = Signal(str)
    settings_requested = Signal()
    mode_switch_requested = Signal(str)
    manage_syllabus_requested = Signal()

    def __init__(self, library, settings, parent: QWidget | None=None) -> None:
        ...

    def set_mode(self, mode: str) -> None:
        ...

    def select(self, kind: str, arg: object=None) -> None:
        """Highlight a row without emitting `navigate` (unknown targets clear the selection)."""
        ...

    def focus_search(self) -> None:
        ...

    def clear_search(self) -> None:
        """Empty the search field without emitting `search_changed`."""
        ...

    def refresh(self) -> None:
        """Rebuild modules and counts, keeping the selection when it still exists."""
        ...

    def _apply_mode(self) -> None:
        ...

    def _on_library_changed(self, _part: str='') -> None:
        ...

    def _on_setting_changed(self, key: str) -> None:
        ...

    def _save_collapsed(self) -> None:
        ...

    def _on_activated(self, row: _Row) -> None:
        ...

    def _on_search_text(self, text: str) -> None:
        ...

    def _emit_search(self) -> None:
        ...

    def _on_menu(self, target: object, pos: QPoint) -> None:
        ...

    def _show_mode_menu(self) -> None:
        ...

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        ...

    def sizeHint(self) -> QSize:
        ...

    def paintEvent(self, _):
        ...
