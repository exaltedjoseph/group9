"""History: the library's Git log as a day-grouped timeline."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime

from PySide6.QtCore import QAbstractListModel, QLocale, QModelIndex, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QListView, QStackedWidget, QStyle, QStyledItemDelegate,
                               QVBoxLayout, QWidget)

from .. import icons
from ..core.models import Commit
from ..theme import font, mono_font, palette, system_color, theme, with_alpha
from . import actions
from .controls import ActivityIndicator, IconButton
from .toolbar import Toolbar

ROW_ROLE = Qt.ItemDataRole.UserRole + 1

# (message prefix, glyph, system color)
_KINDS = [
    ("log classwork", "calendar", "orange"),
    ("delete", "trash", "red"),
    ("add", "plus", "green"),
    ("update", "pencil", "blue"),
    ("rename", "pencil", "blue"),
    ("reorder", "list", "blue"),
    ("merge", "branch", "purple"),
    ("initial", "star", "indigo"),
]


def _glyph_for(message: str) -> tuple[str, str]:
    low = message.lower()
    for prefix, glyph, color in _KINDS:
        if low.startswith(prefix):
            return glyph, color
    return "branch", "gray"


def relative_time(ts: float) -> str:
    """"Just now", "5 minutes ago", "2 hours ago", else the time of day."""
    delta = time.time() - ts
    if delta < 60:
        return "Just now"
    if delta < 3600:
        return actions.plural(int(delta // 60), "minute") + " ago"
    if datetime.fromtimestamp(ts).date() == date.today():
        return actions.plural(int(delta // 3600), "hour") + " ago"
    return actions.short_time(datetime.fromtimestamp(ts))


def day_title(d: date) -> str:
    delta = (date.today() - d).days
    loc = QLocale()
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    weekday = loc.dayName(d.isoweekday(), QLocale.FormatType.LongFormat)
    if 1 < delta < 7:
        return weekday
    return f"{weekday}, {actions.medium_date(d, with_year=d.year != date.today().year)}"


@dataclass
class _Row:
    header: bool
    text: str = ""
    commit: Commit | None = None
    glyph: str = "branch"
    color: str = "gray"
    first: bool = False
    line_above: bool = False
    line_below: bool = False


class _Model(QAbstractListModel):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[_Row] = []

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        row = self.rows[index.row()]
        if role == ROW_ROLE:
            return row
        if role == Qt.ItemDataRole.DisplayRole:
            return row.text if row.header else row.commit.message
        return None

    def flags(self, index):
        if not index.isValid() or self.rows[index.row()].header:
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def set_rows(self, rows: list[_Row]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()


class _Delegate(QStyledItemDelegate):
    ROW_H, HEADER_H, FIRST_HEADER_H = 52, 42, 32

    def __init__(self, view: QListView) -> None:
        super().__init__(view)
        self.view = view
        self.f_msg = font("body")
        self.f_sub = font("subheadline")
        self.f_head = font("headline")
        self.f_hash = mono_font(11)

    def sizeHint(self, option, index):  # noqa: N802
        row = index.data(ROW_ROLE)
        w = self.view.viewport().width()
        if row is not None and row.header:
            return QSize(w, self.FIRST_HEADER_H if row.first else self.HEADER_H)
        return QSize(w, self.ROW_H)

    def paint(self, p: QPainter, option, index):
        row: _Row | None = index.data(ROW_ROLE)
        if row is None:
            return
        pal = palette()
        rect = QRectF(option.rect)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if row.header:
            p.setFont(self.f_head)
            p.setPen(pal.label)
            p.drawText(rect.adjusted(20, 0, -20, -7), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                       row.text)
            p.restore()
            return
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        focused = selected and self.view.hasFocus() and self.view.isActiveWindow()
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        plate = rect.adjusted(10, 1, -10, -1)
        if selected:
            p.fillPath(icons.squircle_path(plate, 8), pal.selection if focused else pal.selection_inactive)
        elif hover:
            p.fillPath(icons.squircle_path(plate, 8), pal.hover)
        primary = pal.selection_text if focused else pal.label
        secondary = with_alpha(pal.selection_text, 210) if focused else pal.secondary_label
        tertiary = with_alpha(pal.selection_text, 170) if focused else pal.tertiary_label

        cx = plate.left() + 22
        cy = rect.center().y()
        line = QColor(255, 255, 255, 110) if focused else pal.separator
        p.setPen(QPen(line, 1.5))
        if row.line_above:
            p.drawLine(QPointF(cx, rect.top()), QPointF(cx, cy - 13))
        if row.line_below:
            p.drawLine(QPointF(cx, cy + 13), QPointF(cx, rect.bottom() + 1))
        badge = QRectF(cx - 11, cy - 11, 22, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(system_color(row.color))
        p.drawEllipse(badge)
        if focused:
            p.setPen(QPen(QColor(255, 255, 255, 190), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(badge.adjusted(-0.5, -0.5, 0.5, 0.5))
        icons.draw_icon(p, row.glyph, badge.adjusted(5, 5, -5, -5), QColor("#FFFFFF"), 1.2)

        c = row.commit
        right = plate.right() - 12
        p.setFont(self.f_hash)
        hash_w = p.fontMetrics().horizontalAdvance(c.short_hash) + 2
        p.setPen(tertiary)
        p.drawText(QRectF(right - hash_w, rect.top(), hash_w, rect.height()),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, c.short_hash)
        x = cx + 22
        w = right - hash_w - 16 - x
        top = cy - 17
        message = c.message.strip().splitlines()[0] if c.message.strip() else "(no message)"
        p.setFont(self.f_msg)
        p.setPen(primary)
        p.drawText(QRectF(x, top, w, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(message, Qt.TextElideMode.ElideRight, int(w)))
        p.setFont(self.f_sub)
        p.setPen(secondary)
        sub = " \u00b7 ".join(s for s in (c.author, relative_time(c.timestamp)) if s)
        p.drawText(QRectF(x, top + 18, w, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(sub, Qt.TextElideMode.ElideRight, int(w)))
        p.restore()


class _HistoryList(QListView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(26)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setViewportMargins(0, 0, 0, 10)
        actions.smooth_scroll(self)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.viewport().update()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.viewport().update()


class HistoryView(QWidget):
    """Timeline of the commits that recorded every library change."""

    def __init__(self, git, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.git = git
        self._loaded = False
        self._pending = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.toolbar = Toolbar("History", "Changes recorded with Git")
        self._spinner = ActivityIndicator(16)
        self._refresh_btn = IconButton("retry", "Refresh")
        self._refresh_btn.clicked.connect(self.refresh)
        self.toolbar.add_action(self._spinner)
        self.toolbar.add_spacing(6)
        self.toolbar.add_action(self._refresh_btn)
        root.addWidget(self.toolbar)

        self._stack = QStackedWidget()
        self.view = _HistoryList()
        self.model = _Model()
        self.view.setModel(self.model)
        self.view.setItemDelegate(_Delegate(self.view))
        self.view.customContextMenuRequested.connect(self._context_menu)
        self._empty = actions.EmptyState("history")
        self._stack.addWidget(self.view)
        self._stack.addWidget(self._empty)
        root.addWidget(self._stack, 1)

        self._debounce = QTimer(self, singleShot=True, interval=350)
        self._debounce.timeout.connect(self.refresh)
        if git is not None:
            # Not status_changed: it also fires after every log request, so refreshing on it would loop.
            for name, slot in (("log_ready", self._on_log), ("committed", self._schedule),
                               ("pulled", self._schedule)):
                sig = getattr(git, name, None)
                if sig is not None:
                    sig.connect(slot)
        theme().changed.connect(self.view.viewport().update)
        self._show_state()

    # ------------------------------------------------------------------ public API
    def refresh(self) -> None:
        if not self._git_available():
            self._spinner.stop()
            self._show_state()
            return
        if not self.isVisible():
            self._pending = True
            return
        self._pending = False
        self._spinner.start()
        try:
            self.git.request_log(200)
        except Exception:
            self._spinner.stop()
            self._show_state()

    # ------------------------------------------------------------------ internals
    def _git_available(self) -> bool:
        if self.git is None:
            return False
        try:
            return bool(self.git.available())
        except Exception:
            return False

    def _schedule(self, *_) -> None:
        if self.isVisible():
            self._debounce.start()
        else:
            self._pending = True

    def _on_log(self, commits) -> None:
        self._spinner.stop()
        self._loaded = True
        rows: list[_Row] = []
        current: date | None = None
        group: list[_Row] = []
        for c in commits or []:
            d = datetime.fromtimestamp(c.timestamp).date()
            if d != current:
                current = d
                rows.append(_Row(header=True, text=day_title(d), first=not rows))
                group = []
            glyph, color = _glyph_for(c.message)
            row = _Row(header=False, text=c.message, commit=c, glyph=glyph, color=color, line_above=bool(group))
            if group:
                group[-1].line_below = True
            group.append(row)
            rows.append(row)
        scroll = self.view.verticalScrollBar().value()
        self.model.set_rows(rows)
        self.view.verticalScrollBar().setValue(scroll)
        self._show_state()

    def _show_state(self) -> None:
        if not self._git_available():
            self._empty.set_content("branch", "Git Isn\u2019t Available",
                                    "Install Git to keep a history of every change to the library.")
            self._stack.setCurrentWidget(self._empty)
            self._refresh_btn.setEnabled(False)
            self.toolbar.set_title("History", "Git isn\u2019t available")
            return
        self._refresh_btn.setEnabled(True)
        n = sum(1 for r in self.model.rows if not r.header)
        if n:
            self.toolbar.set_title("History", f"Changes recorded with Git \u00b7 {actions.plural(n, 'change')}")
            self._stack.setCurrentWidget(self.view)
        else:
            self.toolbar.set_title("History", "Changes recorded with Git")
            self._empty.set_content("history", "No History Yet" if self._loaded else "",
                                    "Every upload, edit and classwork entry will be recorded here."
                                    if self._loaded else "")
            self._stack.setCurrentWidget(self._empty)

    def _context_menu(self, pos) -> None:
        idx = self.view.indexAt(pos)
        row = idx.data(ROW_ROLE) if idx.isValid() else None
        if row is None or row.header:
            return
        self.view.setCurrentIndex(idx)
        menu = actions.make_menu(self)
        c = row.commit
        menu.addAction("Copy Commit Hash", lambda: QGuiApplication.clipboard().setText(c.hash))
        menu.addAction("Copy Message", lambda: QGuiApplication.clipboard().setText(c.message))
        menu.exec(self.view.viewport().mapToGlobal(pos))

    def showEvent(self, e):
        super().showEvent(e)
        if self._pending or not self._loaded:
            QTimer.singleShot(0, self.refresh)

    def paintEvent(self, _):
        QPainter(self).fillRect(self.rect(), palette().window)
