"""Inspector pane: details of the selected resource or classwork entry (Finder "Get Info" feel)."""
# TODO(branch2): implement the data layer and library browsing.
from __future__ import annotations
from PySide6.QtCore import QLocale, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLayout, QScrollArea, QStackedWidget, QVBoxLayout, QWidget
from .. import icons
from ..constants import KIND_NAMES, MODE_FACILITATOR, MODE_INTERN
from ..core.library import Library
from ..core.models import ClassworkEntry, Resource
from ..core.settings import Settings
from ..theme import font, palette, rgba, system_color, with_alpha
from . import actions
from .classwork_view import draw_date_tile
from .controls import IconButton, make_button, on_theme_change
from .sheet import GroupBox, section_header
INSPECTOR_WIDTH = 300
_VALUE_WIDTH = 158

class FlowLayout(QLayout):
    """Left-to-right layout that wraps its items onto new lines."""

    def __init__(self, parent: QWidget | None=None, spacing: int=6) -> None:
        ...

    def addItem(self, item):
        ...

    def count(self):
        ...

    def itemAt(self, i):
        ...

    def takeAt(self, i):
        ...

    def hasHeightForWidth(self):
        ...

    def heightForWidth(self, width):
        ...

    def setGeometry(self, rect):
        ...

    def sizeHint(self):
        ...

    def minimumSize(self):
        ...

    def _arrange(self, rect: QRect, apply: bool) -> int:
        ...

class Tag(QWidget):
    """Keyword capsule."""

    def __init__(self, text: str, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class _Picture(QWidget):
    """Large file icon (or calendar tile) at the top of the inspector."""

    def __init__(self, ext: str | None=None, day=None, size: int=64, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class _Dot(QWidget):

    def __init__(self, color: QColor, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class _Badge(QWidget):
    """Capsule with a glyph and a short text (AI suggestion, missing-file warning)."""

    def __init__(self, icon: str, text: str, color: QColor, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

def _label(text: str, style: str='body', color: str='label', wrap: bool=False, align: Qt.AlignmentFlag | None=None, selectable: bool=False) -> QLabel:
    ...

def _value(text: str, elide: bool=False) -> QLabel:
    ...

def _module_value(name: str, color: str) -> QWidget:
    ...

class Inspector(QWidget):
    """Right-hand detail pane shown next to the resource list."""
    edit_requested = Signal(str)
    edit_classwork_requested = Signal(str)
    explain_requested = Signal(str)

    def __init__(self, library: Library, settings: Settings, parent: QWidget | None=None) -> None:
        ...

    def set_mode(self, mode: str) -> None:
        ...

    def set_resource(self, r: Resource | None) -> None:
        ...

    def set_classwork(self, entry: ClassworkEntry | None) -> None:
        ...

    def clear(self) -> None:
        ...

    def current_id(self) -> str | None:
        ...

    def refresh(self) -> None:
        """Reload the shown item from the library (it may have been edited or deleted)."""
        ...

    def _on_theme(self) -> None:
        ...

    def _rebuild(self, keep_scroll: bool=False) -> None:
        ...

    def _base(self) -> tuple[QWidget, QVBoxLayout]:
        ...

    def _header(self, lay: QVBoxLayout, picture: QWidget, title: str, meta: str) -> None:
        ...

    def _file_buttons(self, lay: QVBoxLayout, available: bool, on_open, on_download, on_reveal) -> None:
        ...

    def _footer(self, lay: QVBoxLayout, on_edit, on_delete) -> None:
        ...

    @staticmethod
    def _section(lay: QVBoxLayout, title: str) -> None:
        ...

    @staticmethod
    def _info(group: GroupBox, label: str, control: QWidget) -> None:
        ...

    def _build_resource(self, r: Resource) -> QWidget:
        ...

    def _mini_entry(self, e: ClassworkEntry) -> QWidget:
        ...

    def _build_classwork(self, e: ClassworkEntry) -> QWidget:
        ...

    def paintEvent(self, _):
        ...
