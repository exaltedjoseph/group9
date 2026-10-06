"""Classwork log: a month-grouped timeline of class sessions with Calendar-style date tiles."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from PySide6.QtCore import QAbstractListModel, QLocale, QModelIndex, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QTextLayout, QTextOption
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QListView, QStackedWidget, QStyle, QStyledItemDelegate,
                               QToolTip, QVBoxLayout, QWidget)

from .. import icons
from ..constants import MODE_FACILITATOR, MODE_INTERN
from ..core.library import Library
from ..core.models import ClassworkEntry
from ..core.settings import Settings
from ..theme import font, palette, system_color, theme, with_alpha
from . import actions
from .controls import IconButton
from .toolbar import Toolbar

ROW_ROLE = Qt.ItemDataRole.UserRole + 1


def draw_date_tile(p: QPainter, rect: QRectF, d: date | None) -> None:
    """Calendar-icon tile: red month strip on top and a large day number."""
    pal = palette()
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(rect)
    path = icons.squircle_path(r, r.width() * 0.22)
    p.fillPath(path.translated(0, 0.7), QColor(0, 0, 0, 30 if not pal.dark else 70))
    p.fillPath(path, QColor("#FFFFFF") if not pal.dark else QColor("#3A3A3C"))
    strip_h = round(r.height() * 0.30)
    strip = QRectF(r.x(), r.y(), r.width(), strip_h)
    p.save()
    p.setClipPath(path)
    p.fillRect(strip, system_color("red"))
    p.restore()
    if d is not None:
        month = QLocale().monthName(d.month, QLocale.FormatType.ShortFormat).upper().rstrip(".")[:3]
        f = font("headline", weight=QFont.Weight.Bold, size=max(7, int(strip_h * 0.64)))
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 106)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(strip.adjusted(0, 0.5, 0, 0), Qt.AlignmentFlag.AlignCenter, month)
        body = QRectF(r.x(), r.y() + strip_h, r.width(), r.height() - strip_h)
        p.setFont(font("title2", weight=QFont.Weight.Normal, size=max(10, int(body.height() * 0.66))))
        p.setPen(QColor("#1D1D1F") if not pal.dark else QColor(255, 255, 255, 230))
        p.drawText(body.adjusted(0, -1, 0, 0), Qt.AlignmentFlag.AlignCenter, str(d.day))
    if not pal.dark:
        p.setPen(QPen(QColor(0, 0, 0, 28), 0.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(icons.squircle_path(r.adjusted(0.4, 0.4, -0.4, -0.4), r.width() * 0.22))
    p.restore()


def wrap_lines(text: str, f: QFont, width: float) -> list[str]:
    """Word-wrap `text` into display lines for `width` pixels."""
    out: list[str] = []
    opt = QTextOption()
    opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    for para in text.splitlines():
        if not para.strip():
            continue
        layout = QTextLayout(para, f)
        layout.setTextOption(opt)
        layout.beginLayout()
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(10.0, width))
            out.append(para[line.textStart(): line.textStart() + line.textLength()].rstrip())
        layout.endLayout()
    return out


# --------------------------------------------------------------------------- model

@dataclass
class _Row:
    header: bool
    text: str = ""
    entry: ClassworkEntry | None = None
    day: date | None = None
    weekday: str = ""
    module: str = ""
    color: str = "blue"
    topic: str = ""
    first: bool = False


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
            return row.text if row.header else row.entry.title
        return None

    def flags(self, index):
        if not index.isValid() or self.rows[index.row()].header:
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def set_rows(self, rows: list[_Row]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def row_of(self, entry_id: str) -> int:
        return next((i for i, r in enumerate(self.rows) if not r.header and r.entry.id == entry_id), -1)


# --------------------------------------------------------------------------- delegate

_PAD = 11
_TILE_W, _TILE_H = 40, 44


class _Delegate(QStyledItemDelegate):
    def __init__(self, view: "_TimelineView") -> None:
        super().__init__(view)
        self.view = view
        self.hover_chip = -1
        self._wrap_cache: dict[tuple, list[str]] = {}
        self._f_title = font("headline")
        self._f_meta = font("subheadline")
        self._f_desc = font("callout")
        self._f_head = font("title3", size=14)
        self._lh = int(QFontMetricsF(self._f_desc).lineSpacing()) + 1

    def clear_cache(self) -> None:
        self._wrap_cache.clear()

    def _selected(self, index: QModelIndex) -> bool:
        sm = self.view.selectionModel()
        return sm is not None and sm.isSelected(index)

    def _desc_lines(self, row: _Row, width: float) -> list[str]:
        key = (row.entry.id, row.entry.updated_at, int(width))
        lines = self._wrap_cache.get(key)
        if lines is None:
            lines = wrap_lines(row.entry.description, self._f_desc, width)
            self._wrap_cache[key] = lines
        return lines

    def layout(self, rect: QRectF, row: _Row, expanded: bool) -> dict:
        plate = rect.adjusted(10, 2, -10, -2)
        tile = QRectF(plate.left() + 10, plate.top() + _PAD, _TILE_W, _TILE_H)
        x = tile.right() + 12
        w = plate.right() - 12 - x
        y = plate.top() + _PAD - 1
        out = {"plate": plate, "tile": tile, "x": x, "w": w}
        out["title"] = QRectF(x, y, w, 18)
        y += 19
        out["meta"] = QRectF(x, y, w, 16)
        y += 18
        lines = self._desc_lines(row, w) if row.entry.description else []
        shown = lines if expanded else lines[:2]
        out["lines"], out["truncated"] = shown, len(lines) > len(shown)
        if out["truncated"]:
            fm = QFontMetricsF(self._f_desc)
            rest = " ".join(lines[len(shown) - 1:])
            shown = shown[:-1] + [fm.elidedText(rest, Qt.TextElideMode.ElideRight, w)]
            out["lines"] = shown
        if shown:
            y += 2
            out["desc"] = QRectF(x, y, w, len(shown) * self._lh)
            y += len(shown) * self._lh
        chip = None
        if row.entry.facilitator or row.entry.attachment:
            y += 7
            fx = x
            if row.entry.facilitator:
                fm = QFontMetricsF(self._f_meta)
                tw = min(math.ceil(fm.horizontalAdvance(row.entry.facilitator)) + 2, w * 0.45)
                out["person"] = QRectF(fx, y, 14 + 4 + tw, 20)
                fx += 14 + 4 + tw + 14
            if row.entry.attachment:
                fm = QFontMetricsF(self._f_meta)
                name = row.entry.attachment_name or "Attachment"
                cw = min(math.ceil(fm.horizontalAdvance(name)) + 2 + 8 + 14 + 5 + 10,
                         max(60.0, plate.right() - 12 - fx))
                chip = QRectF(fx, y, cw, 20)
            y += 20
        out["chip"] = chip
        out["height"] = max(tile.bottom() + _PAD, y + _PAD) - rect.top() + 2
        return out

    def chip_rect(self, index: QModelIndex) -> QRectF | None:
        row = index.data(ROW_ROLE)
        if row is None or row.header or not row.entry.attachment:
            return None
        rect = QRectF(self.view.visualRect(index))
        return self.layout(rect, row, self._selected(index))["chip"]

    def sizeHint(self, option, index):  # noqa: N802
        row = index.data(ROW_ROLE)
        width = self.view.viewport().width()
        if row is None:
            return QSize(width, 0)
        if row.header:
            return QSize(width, 34 if row.first else 44)
        lay = self.layout(QRectF(0, 0, width, 100), row, self._selected(index))
        return QSize(width, int(lay["height"]))

    def helpEvent(self, event, view, option, index):  # noqa: N802
        row = index.data(ROW_ROLE)
        if row is not None and not row.header:
            lay = self.layout(QRectF(option.rect), row, self._selected(index))
            chip = lay["chip"]
            if chip is not None and chip.contains(QPointF(event.pos())):
                QToolTip.showText(event.globalPos(), f"Open \u201c{row.entry.attachment_name}\u201d", view)
                return True
            if lay["truncated"]:
                QToolTip.showText(event.globalPos(), row.entry.description, view)
                return True
        QToolTip.hideText()
        return True

    def paint(self, p: QPainter, option, index):
        row = index.data(ROW_ROLE)
        if row is None:
            return
        pal = palette()
        rect = QRectF(option.rect)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if row.header:
            p.setFont(self._f_head)
            p.setPen(pal.label)
            p.drawText(rect.adjusted(22, 0, -20, -7), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                       row.text)
            p.restore()
            return
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        focused = selected and self.view.hasFocus() and self.view.isActiveWindow()
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        lay = self.layout(rect, row, self._selected(index))
        plate = lay["plate"]
        if selected:
            p.fillPath(icons.squircle_path(plate, 10), pal.selection if focused else pal.selection_inactive)
        elif hover:
            p.fillPath(icons.squircle_path(plate, 10), pal.hover)
        primary = pal.selection_text if focused else pal.label
        secondary = with_alpha(pal.selection_text, 205) if focused else pal.secondary_label

        draw_date_tile(p, lay["tile"], row.day)

        title_r = lay["title"]
        p.setFont(self._f_meta)
        wd_w = p.fontMetrics().horizontalAdvance(row.weekday) + 4
        p.setPen(secondary)
        p.drawText(title_r, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, row.weekday)
        p.setFont(self._f_title)
        p.setPen(primary)
        p.drawText(title_r.adjusted(0, 0, -wd_w - 8, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(row.entry.title, Qt.TextElideMode.ElideRight,
                                              int(title_r.width() - wd_w - 8)))

        meta = lay["meta"]
        dot = QRectF(meta.left() + 1, meta.center().y() - 3.5, 7, 7)
        p.setPen(QPen(QColor(255, 255, 255, 200), 1) if focused else Qt.PenStyle.NoPen)
        p.setBrush(system_color(row.color))
        p.drawEllipse(dot)
        text = row.module + (f"  \u00b7  {row.topic}" if row.topic else "")
        p.setFont(self._f_meta)
        p.setPen(secondary)
        mr = meta.adjusted(14, 0, 0, 0)
        p.drawText(mr, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(mr.width())))

        lines = lay["lines"]
        if lines:
            p.setFont(self._f_desc)
            p.setPen(primary)
            dr = lay["desc"]
            for i, line in enumerate(lines):
                p.drawText(QRectF(dr.left(), dr.top() + i * self._lh, dr.width(), self._lh),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)

        p.setFont(self._f_meta)
        if "person" in lay:
            pr = lay["person"]
            icons.draw_icon(p, "person", QRectF(pr.left(), pr.center().y() - 6.5, 13, 13), secondary)
            p.setPen(secondary)
            tr = pr.adjusted(18, 0, 0, 0)
            p.drawText(tr, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(row.entry.facilitator, Qt.TextElideMode.ElideRight, int(tr.width())))
        chip = lay["chip"]
        if chip is not None:
            chip_hover = self.hover_chip == index.row()
            if focused:
                fill = QColor(255, 255, 255, 70 if chip_hover else 45)
            else:
                fill = pal.fill_hover if chip_hover else pal.fill
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(chip, chip.height() / 2, chip.height() / 2)
            icons.draw_icon(p, "paperclip", QRectF(chip.left() + 8, chip.center().y() - 6.5, 13, 13),
                            primary if focused else pal.accent)
            p.setPen(primary)
            tr = chip.adjusted(8 + 14 + 5, 0, -10, 0)
            p.drawText(tr, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(row.entry.attachment_name or "Attachment",
                                                  Qt.TextElideMode.ElideMiddle, int(tr.width())))
        p.restore()


# --------------------------------------------------------------------------- view

class _TimelineView(QListView):
    open_requested = Signal(QModelIndex)
    delete_requested = Signal(QModelIndex)
    chip_clicked = Signal(QModelIndex)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setViewportMargins(0, 0, 0, 10)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        actions.smooth_scroll(self)

    def delegate(self) -> _Delegate:
        return self.itemDelegate()  # type: ignore[return-value]

    def keyPressEvent(self, e):
        idx = self.currentIndex()
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and idx.isValid():
            self.open_requested.emit(idx)
            return
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and idx.isValid():
            self.delete_requested.emit(idx)
            return
        super().keyPressEvent(e)

    def mouseMoveEvent(self, e):
        super().mouseMoveEvent(e)
        idx = self.indexAt(e.position().toPoint())
        chip = self.delegate().chip_rect(idx) if idx.isValid() else None
        over = chip is not None and chip.contains(e.position())
        row = idx.row() if over else -1
        if row != self.delegate().hover_chip:
            self.delegate().hover_chip = row
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)
            self.viewport().update()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        if self.delegate().hover_chip != -1:
            self.delegate().hover_chip = -1
            self.viewport().unsetCursor()
            self.viewport().update()

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if e.button() == Qt.MouseButton.LeftButton:
            idx = self.indexAt(e.position().toPoint())
            chip = self.delegate().chip_rect(idx) if idx.isValid() else None
            if chip is not None and chip.contains(e.position()):
                self.chip_clicked.emit(idx)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.viewport().update()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.viewport().update()


class ClassworkView(QWidget):
    """Timeline of logged class sessions, grouped by month."""

    log_classwork_requested = Signal(object)
    edit_classwork_requested = Signal(str)

    def __init__(self, library: Library, settings: Settings, parent: QWidget | None = None,
                 embedded: bool = False) -> None:
        super().__init__(parent)
        self.library = library
        self.settings = settings
        self._mode = settings.mode() or MODE_INTERN
        self._module_id: str | None = None
        self._topic_id: str | None = None
        self._scoped = False
        self._dirty = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.toolbar = Toolbar("Classwork")
        self._filter_btn = IconButton("filter", "Filter by Module")
        self._filter_btn.clicked.connect(self._show_filter_menu)
        self._add_btn = IconButton("plus", "Log Classwork\u2026")
        self._add_btn.clicked.connect(lambda: self.log_classwork_requested.emit(self._module_id))
        self.toolbar.add_action(self._filter_btn)
        self.toolbar.add_action(self._add_btn)
        root.addWidget(self.toolbar)

        self._stack = QStackedWidget()
        self.view = _TimelineView()
        self.model = _Model()
        self.view.setModel(self.model)
        self.delegate = _Delegate(self.view)
        self.view.setItemDelegate(self.delegate)
        self.view.selectionModel().selectionChanged.connect(self._on_selection)
        self.view.doubleClicked.connect(self._on_double_click)
        self.view.open_requested.connect(self._on_double_click)
        self.view.delete_requested.connect(self._on_delete_key)
        self.view.chip_clicked.connect(lambda idx: self._open_attachment(self._entry(idx)))
        self.view.customContextMenuRequested.connect(self._context_menu)
        self._empty = actions.EmptyState("calendar")
        self._empty.action_clicked.connect(lambda: self.log_classwork_requested.emit(self._module_id))
        self._stack.addWidget(self.view)
        self._stack.addWidget(self._empty)
        root.addWidget(self._stack, 1)

        self.set_toolbar_visible(not embedded)
        library.changed.connect(self._on_library_changed)
        theme().changed.connect(self._on_theme)
        self._apply_mode()
        self.refresh()

    # ------------------------------------------------------------------ public API
    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._apply_mode()
        self.refresh()

    def show_all(self) -> None:
        self._scoped = False
        self._module_id = None
        self._topic_id = None
        self.refresh()

    def show_module(self, module_id: str, topic_id: str | None = None) -> None:
        self._scoped = True
        self._module_id = module_id
        self._topic_id = topic_id
        self.refresh()

    def set_topic(self, topic_id: str | None) -> None:
        self._topic_id = topic_id
        self.refresh()

    def set_toolbar_visible(self, visible: bool) -> None:
        self.toolbar.setVisible(visible)

    def select_entry(self, entry_id: str) -> None:
        row = self.model.row_of(entry_id)
        if row >= 0:
            idx = self.model.index(row)
            self.view.setCurrentIndex(idx)
            self.view.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)

    def entry_count(self) -> int:
        return sum(1 for r in self.model.rows if not r.header)

    def refresh(self) -> None:
        if not self.isVisible() and self.model.rows:
            self._dirty = True
            return
        self._dirty = False
        selected = self._selected_entry()
        scroll = self.view.verticalScrollBar().value()
        modules = {m.id: m for m in self.library.modules()}
        if self._module_id and self._module_id not in modules:
            self._module_id, self._topic_id = None, None
        try:
            entries = self.library.classwork(module_id=self._module_id, topic_id=self._topic_id)
        except Exception:
            entries = []
        loc = QLocale()
        rows: list[_Row] = []
        month_key = None
        for e in entries:
            d = actions.parse_iso(e.date)
            key = (d.year, d.month) if d else None
            if key != month_key:
                month_key = key
                text = f"{loc.standaloneMonthName(d.month)} {d.year}" if d else "Undated"
                rows.append(_Row(header=True, text=text, first=not rows))
            m = modules.get(e.module_id)
            topic = m.topic(e.topic_id) if m else None
            rows.append(_Row(header=False, entry=e, day=d,
                             weekday=loc.dayName(d.isoweekday(), QLocale.FormatType.LongFormat) if d else "",
                             module=m.name if m else "Unsorted", color=m.color if m else "gray",
                             topic=topic.name if topic else ""))
        self.delegate.clear_cache()
        self.model.set_rows(rows)
        self._update_titles(len(entries), modules)
        self._update_empty(entries, modules)
        if selected is not None:
            self.select_entry(selected.id)
        QTimer.singleShot(0, lambda: self.view.verticalScrollBar().setValue(scroll))

    # ------------------------------------------------------------------ internals
    def _apply_mode(self) -> None:
        self._add_btn.setVisible(self._mode == MODE_FACILITATOR)
        self._filter_btn.setVisible(not self._scoped)

    def _update_titles(self, n: int, modules: dict) -> None:
        sub = actions.plural(n, "entry", "entries") if n else "No entries"
        if self._module_id and self._module_id in modules:
            sub += f" \u00b7 {modules[self._module_id].name}"
        self.toolbar.set_title("Classwork", sub)
        self._filter_btn.setVisible(not self._scoped)
        self._filter_btn.setColor(palette().accent if (self._module_id and not self._scoped) else None)

    def _update_empty(self, entries: list, modules: dict) -> None:
        if entries:
            self._stack.setCurrentWidget(self.view)
            return
        facilitator = self._mode == MODE_FACILITATOR
        m = modules.get(self._module_id) if self._module_id else None
        if self._topic_id:
            message = "Nothing has been logged for this topic yet."
        elif m is not None:
            message = f"Nothing has been logged for {m.name} yet."
        elif facilitator:
            message = "Click + to log your first class session."
        else:
            message = "Sessions your facilitators log will appear here."
        self._empty.set_content("calendar", "No Classwork Logged", message,
                                "Log Classwork\u2026" if facilitator else "")
        self._stack.setCurrentWidget(self._empty)

    def _entry(self, idx: QModelIndex) -> ClassworkEntry | None:
        row = idx.data(ROW_ROLE) if idx.isValid() else None
        return row.entry if row is not None and not row.header else None

    def _selected_entry(self) -> ClassworkEntry | None:
        sm = self.view.selectionModel()
        rows = sm.selectedRows() if sm else []
        return self._entry(rows[0]) if rows else None

    def _on_selection(self, selected, deselected) -> None:
        for rng in list(selected) + list(deselected):
            for idx in rng.indexes():
                self.delegate.sizeHintChanged.emit(idx)

    def _on_double_click(self, idx: QModelIndex) -> None:
        entry = self._entry(idx)
        if entry is None:
            return
        if self._mode == MODE_FACILITATOR:
            self.edit_classwork_requested.emit(entry.id)
        elif entry.attachment:
            self._open_attachment(entry)

    def _on_delete_key(self, idx: QModelIndex) -> None:
        entry = self._entry(idx)
        if entry is not None and self._mode == MODE_FACILITATOR:
            actions.delete_classwork(self.library, entry, self)

    def _open_attachment(self, entry: ClassworkEntry | None) -> None:
        if entry is not None:
            actions.open_attachment(self.library, entry, self)

    def _context_menu(self, pos) -> None:
        idx = self.view.indexAt(pos)
        entry = self._entry(idx)
        if entry is None:
            return
        self.view.setCurrentIndex(idx)
        menu = actions.make_menu(self)
        if entry.attachment:
            menu.addAction("Open Attachment", lambda: actions.open_attachment(self.library, entry, self))
            menu.addAction("Download Attachment\u2026",
                           lambda: actions.download_attachment(self.library, entry, self))
            menu.addAction("Show in Folder", lambda: actions.show_attachment_in_folder(self.library, entry, self))
        if self._mode == MODE_FACILITATOR:
            if entry.attachment:
                menu.addSeparator()
            menu.addAction("Edit\u2026", lambda: self.edit_classwork_requested.emit(entry.id))
            menu.addAction("Delete\u2026", lambda: actions.delete_classwork(self.library, entry, self))
        if menu.actions():
            menu.exec(self.view.viewport().mapToGlobal(pos))

    def _show_filter_menu(self) -> None:
        menu = actions.make_menu(self)
        act = menu.addAction(actions.menu_icon("check" if self._module_id is None else None), "All Modules")
        act.triggered.connect(lambda: self._set_filter(None))
        menu.addSeparator()
        for m in self.library.modules():
            icon = actions.menu_icon("check") if self._module_id == m.id else actions.dot_icon(system_color(m.color))
            act = menu.addAction(icon, m.name)
            act.triggered.connect(lambda _=False, mid=m.id: self._set_filter(mid))
        actions.popup_below(menu, self._filter_btn)

    def _set_filter(self, module_id: str | None) -> None:
        self._module_id = module_id
        self._topic_id = None
        self.refresh()

    def _on_library_changed(self, part: str) -> None:
        if part in ("classwork", "syllabus", "all"):
            self.refresh()

    def _on_theme(self) -> None:
        self._filter_btn.setColor(palette().accent if (self._module_id and not self._scoped) else None)
        self.view.viewport().update()

    def showEvent(self, e):
        super().showEvent(e)
        if self._dirty:
            self.refresh()

    def paintEvent(self, _):
        QPainter(self).fillRect(self.rect(), palette().window)
