"""macOS-style modal alert (app icon, bold title, message, side-by-side buttons)."""
# TODO(branch1): implement design system and shared controls.
from __future__ import annotations
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from .. import icons
from ..theme import font, palette, rgba
from .controls import make_button
_SHADOW = 24

class _AppIcon(QWidget):

    def __init__(self, size: int, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class AlertDialog(QDialog):

    def __init__(self, parent: QWidget | None, title: str, message: str, confirm_text: str, cancel_text: str='Cancel', destructive: bool=True) -> None:
        ...

    def showEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

def confirm(parent: QWidget | None, title: str, message: str='', confirm_text: str='OK', cancel_text: str='Cancel', destructive: bool=True) -> bool:
    """Show a modal alert; returns True if the user confirmed. `cancel_text=""` shows one button."""
    ...
