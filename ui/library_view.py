"""Resource browser: Finder-style list with topic pills, search results, drop target and an inspector."""
# TODO(branch2): implement the data layer and library browsing.
from __future__ import annotations
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from PySide6.QtCore import QAbstractListModel, QEasingCurve, QEvent, QItemSelectionModel, QModelIndex, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen, QPixmap, QStaticText, QTransform
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHBoxLayout, QLabel, QListView, QSizePolicy, QStackedWidget, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget
from .. import icons
from ..constants import KIND_NAMES, MODE_FACILITATOR, MODE_INTERN, RESOURCE_KINDS
from ..core.library import Library
from ..core.models import ClassworkEntry, Resource
from ..core.settings import Settings
from ..theme import font, palette, system_color, theme, with_alpha
from . import actions
from .classwork_view import ClassworkView, draw_date_tile
from .controls import IconButton, SegmentedControl
from .inspector import INSPECTOR_WIDTH, Inspector
from .toolbar import Toolbar
KEY_INSPECTOR_VISIBLE = 'inspector_visible'
ROW_ROLE = Qt.ItemDataRole.UserRole + 1
ROW_HEADER, ROW_RESOURCE, ROW_CLASSWORK = range(3)
SORTS = [('recent', 'Date Added'), ('title', 'Title'), ('kind', 'Type'), ('size', 'Size')]

@dataclass
class _Row:
    kind: int
    id: str = ''
    title: str = ''
    subtitle: str = ''
    ext: str = ''
    date: str = ''
    size: str = ''
    tags: list[str] = field(default_factory=list)
    snippet: list[tuple[str, bool]] = field(default_factory=list)
    count: int = 0
    first: bool = False
    day: object = None
    attachment: bool = False
    payload: Resource | ClassworkEntry | None = None

class _Model(QAbstractListModel):

    def __init__(self) -> None:
        ...

    def rowCount(self, parent=QModelIndex()):
        ...

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        ...

    def flags(self, index):
        ...

    def set_rows(self, rows: list[_Row]) -> None:
        ...

    def row_of(self, item_id: str) -> int:
        ...

def _snippet_segments(text: str, tokens: list[str]) -> list[tuple[str, bool]]:
    ...

class _Delegate(QStyledItemDelegate):
    ROW_H, SNIPPET_H, HEADER_H, FIRST_HEADER_H = (52, 68, 42, 32)
    SIZE_W, DATE_W, GAP = (62, 112, 16)

    def __init__(self, view: QListView) -> None:
        ...

    def _icon(self, kind: int, key, dark: bool, dpr: float) -> QPixmap:
        """32px file icon / date tile rendered once per (key, appearance, scale)."""
        ...

    def _text(self, p: QPainter, rect: QRectF, text: str, f: QFont, right: bool=False) -> None:
        """Elided single-line text drawn from a cached QStaticText layout (pen = current color)."""
        ...

    def _capsule(self, text: str, w: int, focused: bool, dpr: float) -> QPixmap:
        ...

    def clear_caches(self) -> None:
        ...

    def sizeHint(self, option, index):
        ...

    def _tag_layout(self, tags: list[str], max_w: float) -> list[tuple[str, float]]:
        ...

    def paint(self, p: QPainter, option, index):
        ...

    def _paint_header(self, p: QPainter, rect: QRectF, row: _Row) -> None:
        ...

    def _paint_snippet(self, p: QPainter, rect: QRectF, segments, color: QColor, strong: QColor) -> None:
        ...

class _ListView(QListView):
    open_requested = Signal(QModelIndex)
    delete_requested = Signal(QModelIndex)
    space_pressed = Signal()

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def keyPressEvent(self, e):
        ...

    def focusInEvent(self, e):
        ...

    def focusOutEvent(self, e):
        ...

class _PillBar(QWidget):
    """Row of capsule filters ("All" + topics) that scrolls horizontally when it overflows."""
    changed = Signal(object)

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def set_items(self, items: list[tuple[str, str]], selected: str | None=None) -> None:
        ...

    def selected(self) -> str | None:
        ...

    def items(self) -> list[tuple[str, str]]:
        ...

    def _rects(self) -> list[QRectF]:
        ...

    def _content_width(self) -> float:
        ...

    def minimumSizeHint(self):
        ...

    def sizeHint(self):
        ...

    def _index_at(self, x: float) -> int:
        ...

    def mouseMoveEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def mouseReleaseEvent(self, e):
        ...

    def wheelEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

class _ModuleGlyph(QWidget):

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def set_color(self, color: str) -> None:
        ...

    def paintEvent(self, _):
        ...

class _DropOverlay(QWidget):

    def __init__(self, parent: QWidget) -> None:
        ...

    def set_text(self, text: str) -> None:
        ...

    def paintEvent(self, _):
        ...

class _InspectorHost(QWidget):
    """Clips the inspector and animates its width when it is shown or hidden."""

    def __init__(self, inspector: Inspector, open_: bool, parent: QWidget | None=None) -> None:
        ...

    def is_open(self) -> bool:
        ...

    def set_open(self, on: bool, animate: bool=True) -> None:
        ...

    def resizeEvent(self, e):
        ...

class LibraryView(QWidget):
    """All Resources / Recently Added / module / search results, with an inspector pane."""
    add_resource_requested = Signal(object, list)
    edit_resource_requested = Signal(str)
    log_classwork_requested = Signal(object)
    edit_classwork_requested = Signal(str)
    explain_resource_requested = Signal(str)

    def __init__(self, library: Library, settings: Settings, parent: QWidget | None=None) -> None:
        ...

    def _build_toolbar(self) -> None:
        ...

    def _show_sort_menu(self) -> None:
        ...

    def _set_sort(self, sort: str) -> None:
        ...

    def _set_kind(self, kind: str | None) -> None:
        ...

    def set_mode(self, mode: str) -> None:
        ...

    def show_all(self) -> None:
        ...

    def show_recent(self) -> None:
        ...

    def show_module(self, module_id: str) -> None:
        ...

    def show_search(self, query: str) -> None:
        ...

    def select_resource(self, resource_id: str) -> None:
        ...

    def refresh(self, reset_scroll: bool=False) -> None:
        ...

    def _navigate(self, view: str, module_id: str | None=None) -> None:
        ...

    def _resource_rows(self, resources: list[Resource], modules: dict, show_module: bool, tokens: list[str] | None=None) -> list[_Row]:
        ...

    def _classwork_rows(self, entries: list[ClassworkEntry], modules: dict) -> list[_Row]:
        ...

    def _build_rows(self, modules: dict) -> tuple[list[_Row], int]:
        ...

    def _nearest_selectable(self, row: int) -> int:
        ...

    def _update_chrome(self, modules: dict, total: int) -> None:
        ...

    def _update_empty(self, m) -> None:
        ...

    def _apply_mode(self) -> None:
        ...

    def _row(self, idx: QModelIndex) -> _Row | None:
        ...

    def _current_id(self) -> str | None:
        ...

    def _on_current(self, *_) -> None:
        ...

    def _on_throttle(self) -> None:
        ...

    def _update_inspector(self) -> None:
        ...

    def _activate(self, idx: QModelIndex) -> None:
        ...

    def _on_delete_key(self, idx: QModelIndex) -> None:
        ...

    def _context_menu(self, pos) -> None:
        ...

    def _request_add(self) -> None:
        ...

    def _on_topic(self, topic_id: str | None) -> None:
        ...

    def _on_segment(self, index: int) -> None:
        ...

    def _on_inspector_toggled(self, on: bool) -> None:
        ...

    def _on_library_changed(self, _part: str) -> None:
        ...

    def _on_theme(self) -> None:
        ...

    @staticmethod
    def _dropped_files(event) -> list[Path]:
        ...

    def dragEnterEvent(self, e):
        ...

    def dragMoveEvent(self, e):
        ...

    def dragLeaveEvent(self, e):
        ...

    def dropEvent(self, e):
        ...

    def eventFilter(self, obj, event):
        ...

    def showEvent(self, e):
        ...

    def paintEvent(self, _):
        ...
