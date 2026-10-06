"""Unified macOS toolbar strip shown at the top of every content view."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..theme import font, palette, rgba
from .controls import on_theme_change

TOOLBAR_HEIGHT = 52
CAPTION_BUTTON_WIDTH = 46
# The window's minimize / maximize / close buttons sit over the right end of every toolbar.
CAPTION_RESERVE = 3 * CAPTION_BUTTON_WIDTH


class _ElidedLabel(QLabel):
    """Single-line label that truncates with "…" instead of forcing its parent wider."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = text
        self.setMinimumWidth(40)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._elide()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._full = text
        self._elide()
        self.updateGeometry()

    def text(self) -> str:
        return self._full

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.fontMetrics().horizontalAdvance(self._full) + 2, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(40, super().minimumSizeHint().height())

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._elide()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        super().setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, max(self.width(), 0)))


class Toolbar(QWidget):
    """52px strip: title + subtitle on the left, actions on the right.

    Empty areas act as the window's drag region (the window checks the `titleBarArea` property).
    """

    def __init__(self, title: str = "", subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(TOOLBAR_HEIGHT)
        self.setProperty("titleBarArea", True)
        self._separator = True

        row = QHBoxLayout(self)
        row.setContentsMargins(20, 0, 12 + CAPTION_RESERVE, 0)
        row.setSpacing(6)
        self.leading = QHBoxLayout()
        self.leading.setSpacing(6)
        row.addLayout(self.leading)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.setContentsMargins(0, 0, 0, 0)
        titles.addStretch(1)
        self._title = _ElidedLabel(title)
        self._title.setFont(font("title3", size=15))
        self._subtitle = _ElidedLabel(subtitle)
        self._subtitle.setFont(font("subheadline"))
        self._subtitle.setVisible(bool(subtitle))
        for lbl in (self._title, self._subtitle):
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            titles.addWidget(lbl)
        titles.addStretch(1)
        row.addLayout(titles)
        row.addStretch(1)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(4)
        row.addLayout(self.actions)
        on_theme_change(self, self._apply_theme)

    def set_title(self, title: str, subtitle: str = "") -> None:
        self._title.setText(title)
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))

    def add_action(self, widget: QWidget) -> QWidget:
        self.actions.addWidget(widget)
        return widget

    def add_leading(self, widget: QWidget) -> QWidget:
        self.leading.addWidget(widget)
        return widget

    def add_spacing(self, px: int = 8) -> None:
        self.actions.addSpacing(px)

    def set_separator(self, visible: bool) -> None:
        self._separator = visible
        self.update()

    def _apply_theme(self) -> None:
        pal = palette()
        self._title.setStyleSheet(f"color: {rgba(pal.label)};")
        self._subtitle.setStyleSheet(f"color: {rgba(pal.secondary_label)};")
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        pal = palette()
        p.fillRect(self.rect(), pal.window)
        if self._separator:
            p.fillRect(0, self.height() - 1, self.width(), 1, pal.separator)
