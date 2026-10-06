"""Frameless main window: Windows caption buttons, translucent sidebar and content stack."""
# TODO(branch5): implement the app shell, Home dashboard and actions.
from __future__ import annotations
import ctypes
from ctypes import wintypes
from PySide6.QtCore import QByteArray, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import QAbstractButton, QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox, QComboBox, QHBoxLayout, QLineEdit, QStackedWidget, QTabBar, QWidget
from .. import effects
from ..constants import APP_NAME, MODE_FACILITATOR, MODE_INTERN
from ..core import settings as S
from ..theme import palette, theme
from .toolbar import CAPTION_BUTTON_WIDTH
TITLEBAR_HEIGHT = 52
WM_NCMOUSEMOVE, WM_NCLBUTTONUP, WM_NCLBUTTONDBLCLK, WM_NCMOUSELEAVE = (160, 162, 163, 674)
HTMAXBUTTON = 9
SIDEBAR_MIN, SIDEBAR_MAX, SIDEBAR_DEFAULT = (200, 360, 240)
_INTERACTIVE = (QAbstractButton, QLineEdit, QAbstractSpinBox, QComboBox, QAbstractSlider, QTabBar, QAbstractScrollArea)
MINIMIZE, MAXIMIZE, CLOSE = range(3)
_CLOSE_RED = QColor('#C42B1C')

class CaptionButtons(QWidget):
    """Windows 11 minimize / maximize / close buttons. The maximize button is reported to Windows
    as HTMAXBUTTON, so hovering it opens Snap Layouts; its clicks arrive as non-client messages."""
    W = CAPTION_BUTTON_WIDTH

    def __init__(self, window: QWidget) -> None:
        ...

    def button_rect(self, index: int) -> QRect:
        ...

    def index_at(self, pos: QPoint) -> int:
        ...

    def hover_index(self) -> int:
        ...

    def set_hover(self, index: int) -> None:
        ...

    def set_pressed(self, index: int) -> None:
        ...

    def pressed_index(self) -> int:
        ...

    def trigger(self, index: int) -> None:
        ...

    def mouseMoveEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def mousePressEvent(self, e):
        ...

    def mouseReleaseEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

    def _draw_glyph(self, p: QPainter, index: int, r: QRect, color: QColor) -> None:
        ...

class FramelessWindow(QWidget):
    """Top-level window without a system title bar that keeps native snap, resize, shadow and
    rounded corners on Windows, with a live acrylic backdrop where we paint transparent pixels."""
    RESIZE_MARGIN = 6

    def __init__(self) -> None:
        ...

    def resizeEvent(self, e):
        ...

    def showEvent(self, e):
        ...

    def _on_theme(self) -> None:
        ...

    def changeEvent(self, e):
        ...

    def _is_caption(self, local: QPoint) -> bool:
        ...

    def nativeEvent(self, event_type, message):
        ...

    def paintEvent(self, _):
        ...

class _SidebarHandle(QWidget):
    """Invisible drag handle on the sidebar edge."""

    def __init__(self, owner: 'MainWindow') -> None:
        ...

    def mousePressEvent(self, e):
        ...

    def mouseMoveEvent(self, e):
        ...

    def mouseReleaseEvent(self, e):
        ...

class _Body(QWidget):
    """Holds sidebar + content; paints the hairline between them."""

    def __init__(self, owner: 'MainWindow') -> None:
        ...

    def paintEvent(self, _):
        ...

class MainWindow(FramelessWindow):

    def __init__(self, settings, library, git) -> None:
        ...

    def _wire(self) -> None:
        ...

    def _shortcuts(self) -> None:
        ...

    def _go(self, kind: str, arg=None) -> None:
        ...

    def _navigate(self, kind: str, arg) -> None:
        ...

    def _on_search(self, query: str) -> None:
        ...

    def _current_module(self):
        ...

    def _reload(self) -> None:
        ...

    def _show_welcome(self, visible: bool) -> None:
        ...

    def _on_mode_chosen(self, mode: str) -> None:
        ...

    def set_mode(self, mode: str) -> None:
        ...

    def _apply_mode(self, mode: str) -> None:
        ...

    def _facilitator(self) -> bool:
        ...

    def _add_resource(self, module_id, files) -> None:
        ...

    def _edit_resource(self, resource_id: str) -> None:
        ...

    def _log_classwork(self, module_id) -> None:
        ...

    def _edit_classwork(self, entry_id: str) -> None:
        ...

    def _open_syllabus(self) -> None:
        ...

    def _open_resource(self, resource_id: str) -> None:
        ...

    def _ask_assistant(self, prompt: str) -> None:
        ...

    def _explain_resource(self, resource_id: str) -> None:
        ...

    def _on_resource_saved(self, resource_id: str) -> None:
        ...

    def _commit(self, message: str, paths: list) -> None:
        ...

    def _git_failed(self, message: str) -> None:
        ...

    def set_sidebar_width(self, width: int) -> None:
        ...

    def save_sidebar_width(self) -> None:
        ...

    def _layout_children(self) -> None:
        ...

    def resizeEvent(self, e):
        ...

    def _restore_geometry(self) -> None:
        ...

    def closeEvent(self, e):
        ...
