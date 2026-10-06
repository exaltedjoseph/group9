"""First-launch welcome page: choose Facilitator or Intern mode (macOS Setup Assistant style)."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from .. import icons
from ..constants import MODE_FACILITATOR, MODE_INTERN
from ..core.settings import KEY_MODE, KEY_USER_NAME
from ..theme import font, palette, rgba, system_color, theme, with_alpha
from .controls import make_button, mix, on_theme_change
from .sheet import GroupBox

HEADER_HEIGHT = 52
COLUMN_WIDTH = 560
_RADIUS = 12

_CHOICES = [
    (MODE_FACILITATOR, "Facilitator", "Upload materials, log classwork and manage modules.", "person", "blue"),
    (MODE_INTERN, "Intern", "Browse modules, search topics and download resources.", "graduationcap", "green"),
]


class _AppIcon(QWidget):
    def __init__(self, size: int = 96, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        icons.draw_app_icon(p, QRectF(self.rect()))


class _ChoiceCard(QWidget):
    """Large selectable card with a colored symbol badge, a title and a short description."""

    clicked = Signal()
    double_clicked = Signal()

    def __init__(self, title: str, subtitle: str, icon: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title, self._subtitle, self._icon, self._color = title, subtitle, icon, color
        self._selected = False
        self._hover = 0.0
        self._sel = 0.0
        self._title_font = font("title3")
        self._sub_font = font("callout")
        self.setFixedHeight(184)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(title)
        self._hover_anim = QVariantAnimation(self, duration=160, easingCurve=QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(lambda v: self._set("_hover", v))
        self._sel_anim = QVariantAnimation(self, duration=180, easingCurve=QEasingCurve.Type.OutCubic)
        self._sel_anim.valueChanged.connect(lambda v: self._set("_sel", v))
        theme().changed.connect(self.update)

    def _set(self, attr: str, value) -> None:
        setattr(self, attr, float(value))
        self.update()

    @staticmethod
    def _run(anim: QVariantAnimation, start: float, end: float) -> None:
        anim.stop()
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.start()

    def set_selected(self, selected: bool) -> None:
        if selected != self._selected:
            self._selected = selected
            self._run(self._sel_anim, self._sel, 1.0 if selected else 0.0)

    def enterEvent(self, e):
        self._run(self._hover_anim, self._hover, 1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._run(self._hover_anim, self._hover, 0.0)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        e.accept()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        e.accept()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        lift = self._hover
        card = QRectF(self.rect()).adjusted(6, 6 - 1.5 * lift, -6, -12 - 1.5 * lift)
        path = icons.squircle_path(card, _RADIUS)

        peak = (5 + 9 * lift) * (2.2 if pal.dark else 1.0)
        for i in range(8, 0, -1):
            a = int(peak * (1 - i / 9))
            spread = i * 0.75
            shadow = card.adjusted(-spread, -spread + 2 + 2 * lift, spread, spread + 2 + 2 * lift)
            p.fillPath(icons.squircle_path(shadow, _RADIUS + spread), QColor(0, 0, 0, a))
        p.fillPath(path, pal.window)
        p.fillPath(path, pal.group)
        border = with_alpha(pal.group_border, int(pal.group_border.alpha() * (1 + 1.2 * lift)))
        p.setPen(QPen(border, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(icons.squircle_path(card.adjusted(0.5, 0.5, -0.5, -0.5), _RADIUS))
        if self._sel > 0:
            p.setPen(QPen(with_alpha(pal.accent, int(255 * self._sel)), 2))
            p.drawPath(icons.squircle_path(card.adjusted(-1, -1, 1, 1), _RADIUS + 1))

        radio = QRectF(card.right() - 14 - 18, card.top() + 14, 18, 18)
        if self._sel > 0.01:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(pal.accent, int(255 * self._sel)))
            p.drawEllipse(radio)
            icons.draw_icon(p, "check", radio.adjusted(4, 4, -4, -4), with_alpha(QColor("#FFFFFF"), int(255 * self._sel)), 1.5)
        if self._sel < 0.99:
            ring = mix(pal.quaternary_label, pal.tertiary_label, 0.5 + 0.5 * lift)
            p.setPen(QPen(with_alpha(ring, int(ring.alpha() * (1 - self._sel))), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(radio.adjusted(0.6, 0.6, -0.6, -0.6))

        badge_size = 52
        badge = QRectF(card.center().x() - badge_size / 2, card.top() + 26, badge_size, badge_size)
        p.fillPath(icons.squircle_path(badge, badge_size * 0.26), system_color(self._color))
        g = badge_size * 0.6
        icons.draw_icon(p, self._icon, QRectF(badge.center().x() - g / 2, badge.center().y() - g / 2, g, g),
                        QColor("#FFFFFF"), 1.1)

        p.setFont(self._title_font)
        p.setPen(pal.label)
        title_rect = QRectF(card.left() + 16, badge.bottom() + 14, card.width() - 32, 22)
        p.drawText(title_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, self._title)
        p.setFont(self._sub_font)
        p.setPen(pal.secondary_label)
        sub_rect = QRectF(card.left() + 24, title_rect.bottom() + 4, card.width() - 48, card.bottom() - title_rect.bottom() - 14)
        p.drawText(sub_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                   self._subtitle)


class _Footnote(QWidget):
    """Centered glyph + tertiary text line."""

    def __init__(self, icon: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon, self._text = icon, text
        self._font = font("subheadline")
        self.setFixedHeight(18)
        theme().changed.connect(self.update)

    def sizeHint(self) -> QSize:
        return QSize(self.fontMetrics().horizontalAdvance(self._text) + 40, 18)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(self._font)
        color = palette().tertiary_label
        tw = p.fontMetrics().horizontalAdvance(self._text)
        total = 12 + 5 + tw
        x = (self.width() - total) / 2
        icons.draw_icon(p, self._icon, QRectF(x, (self.height() - 12) / 2, 12, 12), color)
        p.setPen(color)
        p.drawText(QRectF(x + 17, 0, tw + 2, self.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._text)


class WelcomeView(QWidget):
    """Full-window mode chooser shown on first launch."""

    mode_chosen = Signal(str)

    def __init__(self, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._mode: str | None = None
        self._fade: QPropertyAnimation | None = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        header = QWidget()
        header.setFixedHeight(HEADER_HEIGHT)
        header.setProperty("titleBarArea", True)
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.viewport().setObjectName("welcomeViewport")
        scroll.viewport().setStyleSheet("#welcomeViewport { background: transparent; }")
        page = QWidget()
        scroll.setWidget(page)
        page.setAutoFillBackground(False)
        outer.addWidget(scroll, 1)

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(32, 8, 32, HEADER_HEIGHT)
        page_layout.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self._column = QWidget()
        self._column.setMaximumWidth(COLUMN_WIDTH)
        self._column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(self._column, 100)
        row.addStretch(1)
        page_layout.addLayout(row)
        page_layout.addStretch(1)

        col = QVBoxLayout(self._column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(_AppIcon(96), 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(18)
        self._title = QLabel("Welcome to Study Library")
        self._title.setFont(font("large_title"))
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self._title)
        col.addSpacing(8)
        self._lead = QLabel("Training materials and classwork for the whole program, organized in one place.")
        self._lead.setFont(font("body"))
        self._lead.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lead.setWordWrap(True)
        col.addWidget(self._lead)
        col.addSpacing(28)

        cards = QHBoxLayout()
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(4)
        self._cards: dict[str, _ChoiceCard] = {}
        for mode, title, subtitle, icon, color in _CHOICES:
            card = _ChoiceCard(title, subtitle, icon, color)
            card.clicked.connect(lambda m=mode: self._choose(m))
            card.double_clicked.connect(lambda m=mode: (self._choose(m), self._continue()))
            self._cards[mode] = card
            cards.addWidget(card)
        col.addLayout(cards)
        col.addSpacing(14)

        self._name = QLineEdit()
        self._name.setFont(font("body"))
        self._name.setPlaceholderText("Full name")
        self._name.setMinimumWidth(240)
        self._name.returnPressed.connect(self._continue)
        group = GroupBox()
        group.add_row("Your Name", self._name, description="Shown on the materials and classwork you add.")
        group_row = QHBoxLayout()
        group_row.setContentsMargins(6, 0, 6, 0)
        group_row.addWidget(group)
        col.addLayout(group_row)
        col.addSpacing(28)

        self._button = make_button("Continue", "primary", large=True)
        self._button.setObjectName("welcomeContinue")
        self._button.setStyleSheet("#welcomeContinue { border-radius: 8px; padding: 6px 20px; }")
        self._button.setFixedSize(220, 34)
        self._button.setEnabled(False)
        self._button.clicked.connect(self._continue)
        col.addWidget(self._button, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(16)
        col.addWidget(_Footnote("lock", "Everything stays on this computer. Changes are tracked with Git."))

        on_theme_change(self, self._apply_theme)
        self._load()

    # ------------------------------------------------------------------ behaviour
    def _load(self) -> None:
        self._name.setText(self._settings.user_name())
        saved = self._settings.mode()
        self._choose(saved if saved in self._cards else None)

    def _choose(self, mode: str | None) -> None:
        self._mode = mode
        for m, card in self._cards.items():
            card.set_selected(m == mode)
        self._button.setEnabled(mode is not None)
        if mode is not None and not self._name.hasFocus():
            self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _continue(self) -> None:
        if self._mode is None:
            return
        name = self._name.text().strip()
        self._settings.set(KEY_USER_NAME, name or None)
        self._settings.set(KEY_MODE, self._mode)
        self.mode_chosen.emit(self._mode)

    def _apply_theme(self) -> None:
        pal = palette()
        self._title.setStyleSheet(f"color: {rgba(pal.label)};")
        self._lead.setStyleSheet(f"color: {rgba(pal.secondary_label)};")
        self.update()

    def keyPressEvent(self, e):
        key = e.key()
        if key == Qt.Key.Key_Left:
            self._choose(MODE_FACILITATOR)
        elif key == Qt.Key.Key_Right:
            self._choose(MODE_INTERN)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._continue()
        else:
            super().keyPressEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        self._load()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._fade_in()

    def _fade_in(self) -> None:
        if self._fade is not None:
            self._fade.stop()
        effect = QGraphicsOpacityEffect(self._column)
        effect.setOpacity(0.0)
        self._column.setGraphicsEffect(effect)
        self._fade = QPropertyAnimation(effect, b"opacity", self)
        self._fade.setDuration(250)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.finished.connect(lambda: self._column.setGraphicsEffect(None))
        self._fade.start()

    def paintEvent(self, _):
        QPainter(self).fillRect(self.rect(), palette().window)
