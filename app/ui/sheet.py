"""macOS sheet overlay and System Settings-style grouped form rows."""
from __future__ import annotations

import shiboken6
from PySide6.QtCore import QEasingCurve, QEvent, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QLayout, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QTextEdit,
                               QVBoxLayout, QWidget)

from .. import icons
from ..theme import font, palette, rgba, with_alpha
from .controls import make_button, on_theme_change

TOOLBAR_HEIGHT = 52
_SHADOW = 28
_RADIUS = 12


class _Card(QWidget):
    """Sheet card: rounded squircle with a soft shadow painted around it."""

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        card = QRectF(self.rect()).adjusted(_SHADOW, _SHADOW - 8, -_SHADOW, -_SHADOW - 8)
        peak = 9 if not pal.dark else 20
        for i in range(_SHADOW, 0, -2):
            a = int(peak * (1 - i / _SHADOW))
            p.fillPath(icons.squircle_path(card.adjusted(-i, -i + 10, i, i + 10), _RADIUS + i), QColor(0, 0, 0, a))
        p.fillPath(icons.squircle_path(card, _RADIUS), pal.sheet)
        p.setPen(QPen(pal.group_border if not pal.dark else with_alpha(pal.label, 30), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(icons.squircle_path(card.adjusted(0.5, 0.5, -0.5, -0.5), _RADIUS))


class Sheet(QWidget):
    """Modal sheet over `host`: dims it and presents a card with title, scrollable body and footer.

    Subclasses add widgets to `self.body_layout` and buttons via `add_footer_buttons()`.
    """

    accepted = Signal()
    closed = Signal()  # after the close animation finishes

    def __init__(self, host: QWidget, title: str = "", width: int = 520) -> None:
        super().__init__(host)
        self._host = host
        self._width = width
        self._progress = 0.0
        self._closing = False
        self._accepted = False
        self._primary: QPushButton | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        host.installEventFilter(self)

        self._card = _Card(self)
        outer = QVBoxLayout(self._card)
        outer.setContentsMargins(_SHADOW, _SHADOW - 8, _SHADOW, _SHADOW + 8)
        outer.setSpacing(0)

        self._title = QLabel(title)
        self._title.setFont(font("title3"))
        self._title.setContentsMargins(24, 20, 24, 4)
        self._title.setVisible(bool(title))
        outer.addWidget(self._title)

        self._subtitle = QLabel()
        self._subtitle.setFont(font("callout"))
        self._subtitle.setWordWrap(True)
        self._subtitle.setContentsMargins(24, 0, 24, 2)
        self._subtitle.hide()
        outer.addWidget(self._subtitle)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("sheetBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(24, 12, 24, 16)
        self.body_layout.setSpacing(10)
        self._scroll.setWidget(self.body)
        outer.addWidget(self._scroll, 1)

        self._footer = QWidget()
        self.footer_layout = QHBoxLayout(self._footer)
        self.footer_layout.setContentsMargins(24, 12, 24, 18)
        self.footer_layout.setSpacing(10)
        outer.addWidget(self._footer)

        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._on_progress)
        self._anim.finished.connect(self._on_anim_done)
        self._fade: QGraphicsOpacityEffect | None = None
        on_theme_change(self, self._apply_theme)
        self.hide()

    # ------------------------------------------------------------------ public API
    def set_title(self, title: str, subtitle: str = "") -> None:
        self._title.setText(title)
        self._title.setVisible(bool(title))
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))

    def add_footer_buttons(self, primary: str, secondary: str | None = "Cancel",
                           leading: QWidget | None = None, destructive: bool = False
                           ) -> tuple[QPushButton, QPushButton | None]:
        """Right-aligned [secondary] [primary] buttons, optional `leading` widget on the left."""
        if leading is not None:
            self.footer_layout.addWidget(leading)
        self.footer_layout.addStretch(1)
        sec_btn = None
        if secondary:
            sec_btn = make_button(secondary)
            sec_btn.setMinimumWidth(84)
            sec_btn.clicked.connect(lambda: self.close_sheet(False))
            self.footer_layout.addWidget(sec_btn)
        pri_btn = make_button(primary, "destructive" if destructive else "primary")
        pri_btn.setMinimumWidth(84)
        self.footer_layout.addWidget(pri_btn)
        self._primary = pri_btn
        return pri_btn, sec_btn

    def open(self) -> None:
        self._closing = False
        self._accepted = False
        self.setGeometry(self._host.rect())
        self._layout_card()
        self.show()
        self.raise_()
        self._start_fade()
        self._animate(1.0, 260, QEasingCurve.Type.OutCubic)
        self.setFocus()
        self.on_open()

    def close_sheet(self, accepted: bool = False) -> None:
        if self._closing or not self.isVisible():
            return
        self._closing = True
        self._accepted = accepted
        self._start_fade()
        self._animate(0.0, 180, QEasingCurve.Type.InCubic)

    def accept(self) -> None:
        self.close_sheet(True)

    # hooks for subclasses
    def on_open(self) -> None:
        """Called right after the sheet starts opening (load current values here)."""

    # ------------------------------------------------------------------ internals
    def _apply_theme(self) -> None:
        pal = palette()
        self._title.setStyleSheet(f"color: {rgba(pal.label)};")
        self._subtitle.setStyleSheet(f"color: {rgba(pal.secondary_label)};")
        self.body.setStyleSheet("#sheetBody { background: transparent; }")
        self._scroll.viewport().setStyleSheet("background: transparent;")
        self.update()

    def _start_fade(self) -> None:
        if self._fade is None:
            self._fade = QGraphicsOpacityEffect(self._card)
            self._card.setGraphicsEffect(self._fade)
        self._fade.setOpacity(self._progress)

    def _animate(self, target: float, duration: int, curve: QEasingCurve.Type) -> None:
        self._anim.stop()
        self._anim.setDuration(duration)
        self._anim.setEasingCurve(curve)
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._anim.start()

    def _on_progress(self, v) -> None:
        self._progress = float(v)
        if self._fade is not None:
            self._fade.setOpacity(self._progress)
        self._layout_card()
        self.update()

    def _on_anim_done(self) -> None:
        if self._progress >= 1.0 and self._fade is not None:
            self._card.setGraphicsEffect(None)
            self._fade = None
        if self._closing:
            self.hide()
            self._closing = False
            if self._accepted:
                self.accepted.emit()
            self.closed.emit()

    def relayout(self) -> None:
        """Re-fit the card after rows inside the body are shown or hidden."""
        QTimer.singleShot(0, lambda: shiboken6.isValid(self) and self.isVisible() and not self._closing
                          and self._layout_card())

    def _layout_card(self) -> None:
        w = min(self._width, self.width() - 40) + 2 * _SHADOW
        self._card.setFixedWidth(w)
        natural = self._card.sizeHint().height()
        body_natural = self.body.sizeHint().height()
        chrome = natural - self._scroll.sizeHint().height()
        max_h = self.height() - TOOLBAR_HEIGHT - 8
        h = min(chrome + body_natural + 2, max_h)
        self._card.setFixedHeight(max(160, h))
        top = max(TOOLBAR_HEIGHT - _SHADOW + 12, int((self.height() - h) * 0.40))
        slide = int((1.0 - self._progress) * -18)
        self._card.move((self.width() - w) // 2, top + slide)

    def eventFilter(self, obj, event):
        if obj is self._host and event.type() == QEvent.Type.Resize:
            self.setGeometry(self._host.rect())
            self._layout_card()
        return super().eventFilter(obj, event)

    def paintEvent(self, _):
        p = QPainter(self)
        dim = QColor(palette().dim)
        dim.setAlpha(int(dim.alpha() * self._progress))
        p.fillRect(self.rect(), dim)

    def mousePressEvent(self, e):
        e.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close_sheet(False)
            return
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focus = self.focusWidget()
            if not isinstance(focus, (QPlainTextEdit, QTextEdit, QAbstractButton)):
                if self._primary is not None and self._primary.isEnabled():
                    self._primary.click()
                    return
        super().keyPressEvent(e)


# --------------------------------------------------------------------------- grouped form

class GroupBox(QWidget):
    """Rounded inset group of rows separated by hairlines (macOS System Settings)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[QWidget] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        on_theme_change(self, self.update)

    def add_row(self, label: str | None, control: QWidget | QLayout | None = None, *,
                description: str = "", icon: str | None = None, icon_color: QColor | None = None,
                stacked: bool = False) -> QWidget:
        """Add a row: label (+ optional description/icon) on the left, `control` on the right.

        `stacked=True` places the control below the label at full width (for text areas).
        `label=None` gives the control the whole row.
        """
        row = QWidget()
        row.setObjectName("groupRow")
        row.setStyleSheet("#groupRow { background: transparent; }")
        pal = palette()
        lay = QVBoxLayout(row) if stacked else QHBoxLayout(row)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(8 if stacked else 12)

        if label is not None:
            text_box = QVBoxLayout()
            text_box.setSpacing(1)
            head = QHBoxLayout()
            head.setSpacing(8)
            if icon:
                head.addWidget(SymbolBadge(icon, icon_color or pal.accent))
            lbl = QLabel(label)
            lbl.setFont(font("body"))
            lbl.setObjectName("rowLabel")
            head.addWidget(lbl)
            if stacked:
                head.addStretch(1)
            text_box.addLayout(head)
            if description:
                d = QLabel(description)
                d.setFont(font("subheadline"))
                d.setWordWrap(True)
                d.setObjectName("rowDescription")
                text_box.addWidget(d)
            lay.addLayout(text_box, 1 if not stacked else 0)
        if control is not None:
            if isinstance(control, QLayout):
                lay.addLayout(control)
            else:
                lay.addWidget(control, 0 if (label is not None and not stacked) else 1,
                              Qt.AlignmentFlag.AlignVCenter if not stacked else Qt.AlignmentFlag(0))
        row.setMinimumHeight(40)
        self._rows.append(row)
        self._layout.addWidget(row)
        _style_row_labels(row)
        on_theme_change(row, lambda r=row: _style_row_labels(r), call_now=False)
        return row

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = icons.squircle_path(r, 9)
        p.fillPath(path, pal.group)
        p.setPen(QPen(pal.group_border, 1))
        p.drawPath(path)
        p.setPen(QPen(pal.separator, 1))
        visible = [row for row in self._rows if row.isVisible()]
        for row in visible[:-1]:
            y = row.geometry().bottom() + 0.5
            p.drawLine(QPointF(12, y), QPointF(self.width() - 12, y))


def _style_row_labels(row: QWidget) -> None:
    pal = palette()
    for lbl in row.findChildren(QLabel, "rowLabel"):
        lbl.setStyleSheet(f"color: {rgba(pal.label)};")
    for lbl in row.findChildren(QLabel, "rowDescription"):
        lbl.setStyleSheet(f"color: {rgba(pal.secondary_label)};")


class SymbolBadge(QWidget):
    """System Settings style icon: white glyph on a colored rounded square."""

    def __init__(self, icon: str, color: QColor, size: int = 22, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon, self._color = icon, QColor(color)
        self.setFixedSize(size, size)

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.fillPath(icons.squircle_path(r, r.width() * 0.26), self._color)
        s = r.width() * 0.66
        icons.draw_icon(p, self._icon, QRectF((r.width() - s) / 2, (r.height() - s) / 2, s, s),
                        QColor("#FFFFFF"), 1.1)


def section_header(text: str) -> QLabel:
    """Bold header placed above a GroupBox."""
    lbl = QLabel(text)
    lbl.setFont(font("headline"))
    lbl.setContentsMargins(2, 6, 0, 0)
    on_theme_change(lbl, lambda: lbl.setStyleSheet(f"color: {rgba(palette().label)};"))
    return lbl


def footnote(text: str, rich: bool = False) -> QLabel:
    """Small secondary explanatory text placed under a GroupBox."""
    lbl = QLabel(text)
    lbl.setFont(font("subheadline"))
    lbl.setWordWrap(True)
    lbl.setContentsMargins(2, 0, 2, 0)
    if rich:
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setOpenExternalLinks(True)
    on_theme_change(lbl, lambda: lbl.setStyleSheet(f"color: {rgba(palette().secondary_label)};"))
    return lbl
