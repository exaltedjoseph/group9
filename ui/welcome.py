"""First-launch welcome page: choose Facilitator or Intern mode (macOS Setup Assistant style)."""
# TODO(branch5): implement the app shell, Home dashboard and actions.
from __future__ import annotations
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
from .. import icons
from ..constants import MODE_FACILITATOR, MODE_INTERN
from ..core.settings import KEY_MODE, KEY_USER_NAME
from ..theme import font, palette, rgba, system_color, theme, with_alpha
from .controls import make_button, mix, on_theme_change
from .sheet import GroupBox
HEADER_HEIGHT = 52
COLUMN_WIDTH = 560
_RADIUS = 12
_CHOICES = [(MODE_FACILITATOR, 'Facilitator', 'Upload materials, log classwork and manage modules.', 'person', 'blue'), (MODE_INTERN, 'Intern', 'Browse modules, search topics and download resources.', 'graduationcap', 'green')]

class _AppIcon(QWidget):

    def __init__(self, size: int=96, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class _ChoiceCard(QWidget):
    """Large selectable card with a colored symbol badge, a title and a short description."""
    clicked = Signal()
    double_clicked = Signal()

    def __init__(self, title: str, subtitle: str, icon: str, color: str, parent: QWidget | None=None) -> None:
        ...

    def _set(self, attr: str, value) -> None:
        ...

    @staticmethod
    def _run(anim: QVariantAnimation, start: float, end: float) -> None:
        ...

    def set_selected(self, selected: bool) -> None:
        ...

    def enterEvent(self, e):
        ...

    def leaveEvent(self, e):
        ...

    def mousePressEvent(self, e):
        ...

    def mouseDoubleClickEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

class _Footnote(QWidget):
    """Centered glyph + tertiary text line."""

    def __init__(self, icon: str, text: str, parent: QWidget | None=None) -> None:
        ...

    def sizeHint(self) -> QSize:
        ...

    def paintEvent(self, _):
        ...

class WelcomeView(QWidget):
    """Full-window mode chooser shown on first launch."""
    mode_chosen = Signal(str)

    def __init__(self, settings, parent: QWidget | None=None) -> None:
        ...

    def _load(self) -> None:
        ...

    def _choose(self, mode: str | None) -> None:
        ...

    def _continue(self) -> None:
        ...

    def _apply_theme(self) -> None:
        ...

    def keyPressEvent(self, e):
        ...

    def showEvent(self, e):
        ...

    def _fade_in(self) -> None:
        ...

    def paintEvent(self, _):
        ...
