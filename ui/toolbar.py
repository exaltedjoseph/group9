"""Unified macOS toolbar strip shown at the top of every content view."""
# TODO(branch1): implement design system and shared controls.
from __future__ import annotations
from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from ..theme import font, palette, rgba
from .controls import on_theme_change
TOOLBAR_HEIGHT = 52
CAPTION_BUTTON_WIDTH = 46
CAPTION_RESERVE = 3 * CAPTION_BUTTON_WIDTH

class _ElidedLabel(QLabel):
    """Single-line label that truncates with "…" instead of forcing its parent wider."""

    def __init__(self, text: str='', parent: QWidget | None=None) -> None:
        ...

    def setText(self, text: str) -> None:
        ...

    def text(self) -> str:
        ...

    def sizeHint(self) -> QSize:
        ...

    def minimumSizeHint(self) -> QSize:
        ...

    def changeEvent(self, event) -> None:
        ...

    def resizeEvent(self, event) -> None:
        ...

    def _elide(self) -> None:
        ...

class Toolbar(QWidget):
    """52px strip: title + subtitle on the left, actions on the right.

    Empty areas act as the window's drag region (the window checks the `titleBarArea` property).
    """

    def __init__(self, title: str='', subtitle: str='', parent: QWidget | None=None) -> None:
        ...

    def set_title(self, title: str, subtitle: str='') -> None:
        ...

    def add_action(self, widget: QWidget) -> QWidget:
        ...

    def add_leading(self, widget: QWidget) -> QWidget:
        ...

    def add_spacing(self, px: int=8) -> None:
        ...

    def set_separator(self, visible: bool) -> None:
        ...

    def _apply_theme(self) -> None:
        ...

    def paintEvent(self, _):
        ...
