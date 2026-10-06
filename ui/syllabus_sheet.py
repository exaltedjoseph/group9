"""Manage the syllabus: modules (name, description, color, order) and their topics."""
# TODO(branch3): implement Git, text extraction, classwork and syllabus.
from __future__ import annotations
from typing import Callable
from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QAbstractItemView, QBoxLayout, QDialog, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit, QVBoxLayout, QWidget
from .. import icons
from ..core.library import LibraryError
from ..theme import font, palette, system_color
from .alert import AlertDialog, confirm
from .forms import ColorPicker, ListPane, RowDelegate, StatusLabel, fit_row
from .sheet import GroupBox, Sheet, section_header
_ID = Qt.ItemDataRole.UserRole
_COLOR = Qt.ItemDataRole.UserRole + 1
_NAME = Qt.ItemDataRole.UserRole + 2

def _plural(n: int, one: str, many: str) -> str:
    ...

def _confirm(parent: QWidget, title: str, message: str, confirm_text: str, destructive: bool=True) -> bool:
    """The standard alert; long button titles stack vertically like on macOS."""
    ...

def _unique_name(base: str, existing: list[str]) -> str:
    ...

class _ModuleList(QListWidget):
    """Module list with drag-to-reorder; emits `reordered(module_id, new_index)`."""
    reordered = Signal(str, int)
    delete_pressed = Signal()

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def dropEvent(self, e):
        ...

    def keyPressEvent(self, e):
        ...

    def focusInEvent(self, e):
        ...

    def focusOutEvent(self, e):
        ...

class _TopicList(_ModuleList):

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def keyPressEvent(self, e):
        ...

class SyllabusSheet(Sheet):
    """The 'Modules' sheet: two panes, changes apply immediately (each one is committed to Git)."""

    def __init__(self, host: QWidget, library) -> None:
        ...

    def _build(self) -> None:
        ...

    def _module_glyph(self, index) -> tuple[str, object]:
        ...

    def on_open(self) -> None:
        ...

    def _reload(self, select: str | None=None) -> None:
        ...

    def _load_module(self) -> None:
        ...

    def _load_topics(self, module, select: str | None=None) -> None:
        ...

    def _update_buttons(self) -> None:
        ...

    def _on_library_changed(self, part: str) -> None:
        ...

    def _on_module_selected(self, _row: int) -> None:
        ...

    def _run(self, fn: Callable[[], object]) -> bool:
        ...

    def _show_error(self, message: str) -> None:
        ...

    def _relayout(self) -> None:
        ...

    def _current_item(self) -> QListWidgetItem | None:
        ...

    def _save_name(self) -> None:
        ...

    def _save_desc(self) -> None:
        ...

    def _save_color(self, color: str) -> None:
        ...

    def _commit_pending(self) -> None:
        ...

    def _done(self) -> None:
        ...

    def eventFilter(self, obj, event):
        ...

    def _add_module(self) -> None:
        ...

    def _delete_module(self) -> None:
        ...

    def _move_module(self, delta: int) -> None:
        ...

    def _on_reordered(self, module_id: str, index: int) -> None:
        ...

    def _module_menu(self, pos) -> None:
        ...

    def _add_topic(self) -> None:
        ...

    def _on_topic_edited(self, item: QListWidgetItem) -> None:
        ...

    def _delete_topic(self) -> None:
        ...

    def _topic_menu(self, pos) -> None:
        ...
