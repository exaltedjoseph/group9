"""macOS-style modal alert (app icon, bold title, message, side-by-side buttons)."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import icons
from ..theme import font, palette, rgba
from .controls import make_button

_SHADOW = 24


class _AppIcon(QWidget):
    def __init__(self, size: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        icons.draw_app_icon(p, QRectF(self.rect()))


class AlertDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, message: str, confirm_text: str,
                 cancel_text: str = "Cancel", destructive: bool = True) -> None:
        super().__init__(parent.window() if parent else None)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedWidth(260 + 2 * _SHADOW)
        pal = palette()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(_SHADOW + 16, _SHADOW + 20, _SHADOW + 16, _SHADOW + 16)
        lay.setSpacing(0)

        icon = _AppIcon(64)
        lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(12)

        t = QLabel(title)
        t.setFont(font("headline", size=13))
        t.setWordWrap(True)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet(f"color: {rgba(pal.label)};")
        lay.addWidget(t)
        if message:
            lay.addSpacing(6)
            m = QLabel(message)
            m.setFont(font("callout", size=11))
            m.setWordWrap(True)
            m.setAlignment(Qt.AlignmentFlag.AlignCenter)
            m.setStyleSheet(f"color: {rgba(pal.label)};")
            lay.addWidget(m)
        lay.addSpacing(18)

        row = QHBoxLayout()
        row.setSpacing(8)
        confirm = make_button(confirm_text, "destructive" if destructive else "primary")
        buttons = [confirm]
        if cancel_text:
            cancel = make_button(cancel_text)
            cancel.clicked.connect(self.reject)
            cancel.setDefault(destructive)
            buttons.insert(0, cancel)
        for b in buttons:
            b.setMinimumHeight(28)
            row.addWidget(b, 1)
        confirm.clicked.connect(self.accept)
        confirm.setDefault(not destructive or not cancel_text)
        lay.addLayout(row)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(160)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    def showEvent(self, e):
        super().showEvent(e)
        parent = self.parentWidget()
        if parent is not None:
            geo = parent.frameGeometry()
            self.adjustSize()
            self.move(geo.center().x() - self.width() // 2, geo.top() + max(60, geo.height() // 4) - _SHADOW)
        self.setWindowOpacity(0.0)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        card = QRectF(self.rect()).adjusted(_SHADOW, _SHADOW, -_SHADOW, -_SHADOW)
        for i in range(_SHADOW, 0, -2):
            a = int((7 if not pal.dark else 16) * (1 - i / _SHADOW))
            p.fillPath(icons.squircle_path(card.adjusted(-i, -i + 6, i, i + 6), 12 + i), QColor(0, 0, 0, a))
        p.fillPath(icons.squircle_path(card, 12), pal.sheet)
        p.setPen(pal.group_border)
        p.drawPath(icons.squircle_path(card.adjusted(0.5, 0.5, -0.5, -0.5), 12))


def confirm(parent: QWidget | None, title: str, message: str = "", confirm_text: str = "OK",
            cancel_text: str = "Cancel", destructive: bool = True) -> bool:
    """Show a modal alert; returns True if the user confirmed. `cancel_text=""` shows one button."""
    dlg = AlertDialog(parent, title, message, confirm_text, cancel_text, destructive)
    return dlg.exec() == QDialog.DialogCode.Accepted
