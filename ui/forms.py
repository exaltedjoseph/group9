"""Shared macOS-style form widgets for the sheets: tokens, drop zones, dates, colors and lists."""
# TODO(branch1): implement design system and shared controls.
from __future__ import annotations
import atexit
import math
import re
from pathlib import Path
from typing import Callable, Iterable
import shiboken6
from PySide6.QtCore import QCoreApplication, QDate, QEvent, QLocale, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFontMetrics, QFontMetricsF, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QDateEdit, QFileDialog, QHBoxLayout, QLabel, QLayout, QLineEdit, QListWidget, QSizePolicy, QStyle, QStyledItemDelegate, QToolTip, QVBoxLayout, QWidget, QWidgetItem
from .. import icons
from ..constants import MODULE_COLORS, RESOURCE_KINDS
from ..theme import font, palette, rgba, system_color, with_alpha
from .controls import IconButton, Separator, make_button, on_theme_change
ColorSource = QColor | Callable[[], QColor] | None
_KINDS = {'pdf': 'PDF document', 'doc': 'Word document', 'docx': 'Word document', 'rtf': 'Rich text document', 'odt': 'OpenDocument text', 'pages': 'Pages document', 'ppt': 'PowerPoint presentation', 'pptx': 'PowerPoint presentation', 'key': 'Keynote presentation', 'odp': 'OpenDocument presentation', 'xls': 'Excel spreadsheet', 'xlsx': 'Excel spreadsheet', 'csv': 'CSV document', 'numbers': 'Numbers spreadsheet', 'ods': 'OpenDocument spreadsheet', 'txt': 'Plain text', 'md': 'Markdown document', 'html': 'HTML document', 'htm': 'HTML document', 'json': 'JSON document', 'py': 'Python script', 'ipynb': 'Jupyter notebook', 'js': 'JavaScript file', 'ts': 'TypeScript file', 'java': 'Java source', 'c': 'C source', 'cpp': 'C++ source', 'sql': 'SQL file', 'css': 'CSS stylesheet', 'png': 'PNG image', 'jpg': 'JPEG image', 'jpeg': 'JPEG image', 'gif': 'GIF image', 'webp': 'WebP image', 'svg': 'SVG image', 'heic': 'HEIC image', 'bmp': 'BMP image', 'mp4': 'MPEG-4 movie', 'mov': 'QuickTime movie', 'mkv': 'Matroska video', 'webm': 'WebM video', 'mp3': 'MP3 audio', 'wav': 'WAV audio', 'm4a': 'MPEG-4 audio', 'zip': 'ZIP archive', 'rar': 'RAR archive', '7z': '7-Zip archive', 'gz': 'Gzip archive', 'tar': 'Tar archive'}

def file_kind(ext: str) -> str:
    """Finder-style kind description for a file extension ("PDF document")."""
    ...

def human_size(n: int) -> str:
    ...

def prettify_stem(stem: str) -> str:
    """'intro_to-python' -> 'Intro To Python' (keeps the casing of mixed-case names)."""
    ...

def merge_keywords(current: Iterable[str], extra: Iterable[str]) -> list[str]:
    ...
_last_dir: list[str] = []

def choose_file(parent: QWidget | None, title: str='Choose a File') -> Path | None:
    """Native open-file dialog; remembers the last folder."""
    ...

def local_files(mime) -> list[Path]:
    ...

def _resolve(color: ColorSource, default: Callable[[], QColor]) -> QColor:
    ...

def fit_row(row: QWidget, height: int=40) -> None:
    """Trim a GroupBox row's vertical padding so rows with fields stay `height` px tall."""
    ...

def add_label_accessory(row: QWidget, widget: QWidget) -> None:
    """Place `widget` right after a GroupBox row's label (e.g. a sparkle badge)."""
    ...

def _layout_containing(layout: QLayout | None, widget: QWidget) -> QLayout | None:
    ...

class _Reaper(QObject):
    """Holds Python references to running threads until they finish, then deletes them."""

    def __init__(self) -> None:
        ...

    def keep(self, thread: QThread) -> None:
        ...

    def shutdown(self) -> None:
        """Give running threads a moment; never let Python destroy one that is still running."""
        ...

    @Slot()
    def _release(self) -> None:
        ...
_reaper: _Reaper | None = None

def keep_thread(thread: QThread) -> QThread:
    """Start-and-forget safety: the thread object survives (even if its owner is closed) until finished."""
    ...

def tint_badges(row: QWidget, color_name: str) -> None:
    """Keep a row's SymbolBadge in the system color for the current appearance."""
    ...

class Glyph(QWidget):
    """A single SF-style glyph. `color` may be a QColor or a callable (resolved at paint time)."""

    def __init__(self, icon: str, color: ColorSource=None, size: int=16, parent: QWidget | None=None, weight: float=1.0) -> None:
        ...

    def set_icon(self, icon: str, color: ColorSource=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class SparkleBadge(Glyph):
    """Tiny purple sparkles shown next to a field Gemini filled in."""

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

class ElidedLabel(QLabel):
    """Single-line label that elides its text to the available width."""

    def __init__(self, text: str='', mode: Qt.TextElideMode=Qt.TextElideMode.ElideRight, parent: QWidget | None=None) -> None:
        ...

    def setText(self, text: str) -> None:
        ...

    def text(self) -> str:
        ...

    def sizeHint(self) -> QSize:
        ...

    def minimumSizeHint(self) -> QSize:
        ...

    def changeEvent(self, e):
        ...

    def resizeEvent(self, e):
        ...

    def _refresh(self) -> None:
        ...

class StatusLabel(QWidget):
    """Footnote with an optional leading glyph. kind: info | ok | error | ai."""

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def _glyph_color(self) -> QColor:
        ...

    def set_status(self, text: str, kind: str='info') -> None:
        ...

    def clear(self) -> None:
        ...

    def text(self) -> str:
        ...

    def kind(self) -> str:
        ...

    def _apply_theme(self) -> None:
        ...

class _FileIcon(QWidget):

    def __init__(self, size: int=40, parent: QWidget | None=None) -> None:
        ...

    def set_ext(self, ext: str) -> None:
        ...

    def paintEvent(self, _):
        ...

class FlowLayout(QLayout):
    """Left-to-right wrapping layout; an optional last "stretch" widget fills the rest of its line."""

    def __init__(self, parent: QWidget | None=None, spacing: int=4, line_spacing: int=4) -> None:
        ...

    def set_stretch_widget(self, widget: QWidget, min_width: int=80) -> None:
        ...

    def insert_widget(self, index: int, widget: QWidget) -> None:
        ...

    def addItem(self, item) -> None:
        ...

    def count(self) -> int:
        ...

    def itemAt(self, i: int):
        ...

    def takeAt(self, i: int):
        ...

    def expandingDirections(self) -> Qt.Orientation:
        ...

    def hasHeightForWidth(self) -> bool:
        ...

    def heightForWidth(self, width: int) -> int:
        ...

    def setGeometry(self, rect: QRect) -> None:
        ...

    def sizeHint(self) -> QSize:
        ...

    def minimumSize(self) -> QSize:
        ...

    def _do_layout(self, rect: QRect, test: bool) -> int:
        ...

class _Token(QWidget):
    remove_requested = Signal(object)
    pressed = Signal(object)
    H = 20

    def __init__(self, text: str, parent: QWidget | None=None) -> None:
        ...

    def sizeHint(self) -> QSize:
        ...

    def _close_rect(self) -> QRectF:
        ...

    def set_selected(self, on: bool) -> None:
        ...

    def enterEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def mousePressEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

class _TokenInput(QLineEdit):

    def __init__(self, owner: 'TokenField') -> None:
        ...

    def sizeHint(self) -> QSize:
        ...

    def minimumSizeHint(self) -> QSize:
        ...

    def event(self, e):
        ...

    def keyPressEvent(self, e: QKeyEvent):
        ...

class _SuggestionPopup(QWidget):
    """Non-activating rounded menu of keyword completions shown under a TokenField."""
    picked = Signal(str)
    M = 10
    ROW = 24
    MAX_ROWS = 8

    def __init__(self, parent: QWidget) -> None:
        ...

    def show_items(self, items: list[str], query: str, anchor: QWidget) -> None:
        ...

    def current(self) -> str | None:
        ...

    def move_selection(self, delta: int) -> None:
        ...

    def _row_at(self, y: float) -> int:
        ...

    def mouseMoveEvent(self, e):
        ...

    def mousePressEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

class TokenField(QWidget):
    """Keyword chips editor (macOS tag field) with wrapping tokens and autocompletion."""
    changed = Signal()

    def __init__(self, completions: Iterable[str]=(), placeholder: str='Add keywords', parent: QWidget | None=None) -> None:
        ...

    def tokens(self) -> list[str]:
        ...

    def set_tokens(self, tokens: Iterable[str]) -> None:
        ...

    def add_token(self, text: str) -> bool:
        ...

    def commit_pending(self) -> None:
        """Turn any typed-but-uncommitted text into a token."""
        ...

    def set_completions(self, words: Iterable[str]) -> None:
        ...

    def set_placeholder(self, text: str) -> None:
        ...

    def input(self) -> QLineEdit:
        ...

    def setFocus(self, *args) -> None:
        ...

    def _insert(self, text: str) -> None:
        ...

    def _remove(self, tok: _Token) -> None:
        ...

    def _on_token_pressed(self, tok: _Token) -> None:
        ...

    def _select(self, tok: _Token | None) -> None:
        ...

    def _backspace(self, select_only: bool=False) -> None:
        ...

    def _commit_input(self) -> None:
        ...

    def _on_completion(self, text: str) -> None:
        ...

    def _pick_suggestion(self) -> bool:
        """Accept the highlighted completion, if any."""
        ...

    def _matches(self, query: str) -> list[str]:
        ...

    def _on_text_edited(self, text: str) -> None:
        ...

    def hideEvent(self, e):
        ...

    def _after_change(self, emit: bool) -> None:
        ...

    def _update_placeholder(self) -> None:
        ...

    def _sync_height(self) -> None:
        ...

    def sizeHint(self) -> QSize:
        ...

    def minimumSizeHint(self) -> QSize:
        ...

    def resizeEvent(self, e):
        ...

    def mousePressEvent(self, e):
        ...

    def eventFilter(self, obj, event):
        ...

    def _apply_theme(self) -> None:
        ...

    def paintEvent(self, _):
        ...

class DropZone(QWidget):
    """Dashed drop target with "Choose File…", turning into a file card once a file is chosen."""
    file_changed = Signal(object)
    EMPTY_H = 112
    CARD_H = 64

    def __init__(self, parent: QWidget | None=None, prompt: str='Drop a file here') -> None:
        ...

    def path(self) -> Path | None:
        ...

    def set_path(self, path: Path | str | None) -> None:
        ...

    def set_existing(self, name: str | None, size: int=0, ext: str='') -> None:
        """Show a file that is already in the library (edit mode); `path()` stays None."""
        ...

    def has_file(self) -> bool:
        ...

    def set_clearable(self, on: bool) -> None:
        ...

    def set_prompt(self, text: str) -> None:
        ...

    def _pick(self) -> None:
        ...

    def _on_clear(self) -> None:
        ...

    def _refresh(self) -> None:
        ...

    def _apply_theme(self) -> None:
        ...

    def dragEnterEvent(self, e):
        ...

    def dragLeaveEvent(self, e):
        ...

    def dropEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

class AttachmentField(QWidget):
    """Compact optional attachment: "Attach File…" button, or a file chip with a remove button."""
    file_changed = Signal(object)

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def path(self) -> Path | None:
        ...

    def set_path(self, path: Path | str | None) -> None:
        ...

    def set_existing(self, name: str | None, size: int=0, ext: str='') -> None:
        ...

    def removed_existing(self) -> bool:
        """True when an existing attachment was removed or replaced."""
        ...

    def clear(self) -> None:
        ...

    def _shown(self) -> tuple[str, int, str] | None:
        ...

    def _pick(self) -> None:
        ...

    def _refresh(self) -> None:
        ...

    def _apply_theme(self) -> None:
        ...

    def dragEnterEvent(self, e):
        ...

    def dragLeaveEvent(self, e):
        ...

    def dropEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

def _medium_date_format() -> str:
    ...

class _TodayButton(IconButton):
    """The small dot between the month arrows that jumps to today."""

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class _CalendarPopup(QWidget):
    """Compact macOS-style month calendar shown below a DateField."""
    picked = Signal(QDate)
    M = 12
    CELL_W, CELL_H = (30, 26)

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def show_for(self, field: QWidget, date: QDate) -> None:
        ...

    def hideEvent(self, e):
        ...

    def _grid_origin(self) -> QPointF:
        ...

    def _grid_start(self) -> QDate:
        ...

    def _date_at(self, pos: QPointF) -> QDate | None:
        ...

    def _shift_month(self, n: int) -> None:
        ...

    def _go_today(self) -> None:
        ...

    def _set_focus_date(self, d: QDate) -> None:
        ...

    def mouseMoveEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def mouseReleaseEvent(self, e):
        ...

    def wheelEvent(self, e):
        ...

    def keyPressEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

class DateField(QDateEdit):
    """Date field ("6 Oct 2026") with keyboard editing and a macOS-style calendar popup."""
    date_changed = Signal(str)

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def date_iso(self) -> str:
        ...

    def set_date_iso(self, value: str | None) -> None:
        ...

    def _toggle_popup(self) -> None:
        ...

    def _on_picked(self, d: QDate) -> None:
        ...

    def keyPressEvent(self, e):
        ...

    def resizeEvent(self, e):
        ...

    def _apply_theme(self) -> None:
        ...

class ColorPicker(QWidget):
    """Row of circular system-color swatches (like the macOS accent color picker)."""
    color_changed = Signal(str)

    def __init__(self, colors: Iterable[str]=MODULE_COLORS, size: int=18, spacing: int=6, parent: QWidget | None=None) -> None:
        ...

    def color(self) -> str:
        ...

    def set_color(self, name: str) -> None:
        """Select without emitting `color_changed`."""
        ...

    def _rect(self, i: int) -> QRectF:
        ...

    def _index_at(self, pos: QPointF) -> int:
        ...

    def _choose(self, i: int) -> None:
        ...

    def event(self, e):
        ...

    def mouseMoveEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def mouseReleaseEvent(self, e):
        ...

    def keyPressEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

def _fit_combo(combo: QComboBox, min_width: int) -> None:
    ...

class ModuleCombo(QComboBox):
    """Pop-up button listing modules with colored folder glyphs."""

    def __init__(self, min_width: int=260, parent: QWidget | None=None) -> None:
        ...

    def set_modules(self, modules, current: str | None=None) -> None:
        ...

    def module_id(self) -> str | None:
        ...

    def set_module_id(self, module_id: str | None) -> None:
        ...

    def _repaint_icons(self) -> None:
        ...

class TopicCombo(QComboBox):
    """Pop-up button with "None" plus the topics of one module."""

    def __init__(self, min_width: int=260, parent: QWidget | None=None) -> None:
        ...

    def set_module(self, module, current: str | None=None) -> None:
        ...

    def topic_id(self) -> str | None:
        ...

    def set_topic_id(self, topic_id: str | None) -> None:
        ...

class KindCombo(QComboBox):
    """Pop-up button for the resource type."""

    def __init__(self, min_width: int=170, parent: QWidget | None=None) -> None:
        ...

    def kind(self) -> str:
        ...

    def set_kind(self, kind: str | None) -> None:
        ...

    def _repaint_icons(self) -> None:
        ...

class RowDelegate(QStyledItemDelegate):
    """Rounded selection plates for lists (accent when focused), optional glyph per row."""
    ROW_H = 28

    def __init__(self, view: QAbstractItemView, glyph: Callable | None=None) -> None:
        ...

    def sizeHint(self, option, index) -> QSize:
        ...

    def paint(self, p: QPainter, option, index) -> None:
        ...

    def createEditor(self, parent, option, index):
        ...

    def updateEditorGeometry(self, editor, option, index):
        ...

class _BarButton(QWidget):
    clicked = Signal()

    def __init__(self, icon: str, tooltip: str, parent: QWidget | None=None) -> None:
        ...

    def enterEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def mousePressEvent(self, e):
        ...

    def mouseReleaseEvent(self, e):
        ...

    def changeEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

class ListPane(QWidget):
    """Rounded bordered list with the classic macOS +/- button bar along its bottom edge."""
    add_clicked = Signal()
    remove_clicked = Signal()

    def __init__(self, view: QListWidget, empty_text: str='', parent: QWidget | None=None) -> None:
        ...

    def sizeHint(self) -> QSize:
        ...

    def update_hint(self) -> None:
        ...

    def set_empty_text(self, text: str) -> None:
        ...

    def eventFilter(self, obj, event):
        ...

    def _apply_theme(self) -> None:
        ...

    def paintEvent(self, _):
        ...
