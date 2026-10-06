"""Resource browser: Finder-style list with topic pills, search results, drop target and an inspector."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, QEasingCurve, QEvent, QItemSelectionModel, QModelIndex, QPointF,
                            QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen, QPixmap, QStaticText,
                           QTransform)
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLabel, QListView, QSizePolicy,
                               QStackedWidget, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from .. import icons
from ..constants import KIND_NAMES, MODE_FACILITATOR, MODE_INTERN, RESOURCE_KINDS
from ..core.library import Library
from ..core.models import ClassworkEntry, Resource
from ..core.settings import Settings
from ..theme import font, palette, system_color, theme, with_alpha
from . import actions
from .classwork_view import ClassworkView, draw_date_tile
from .controls import IconButton, SegmentedControl
from .inspector import INSPECTOR_WIDTH, Inspector
from .toolbar import Toolbar

KEY_INSPECTOR_VISIBLE = "inspector_visible"
ROW_ROLE = Qt.ItemDataRole.UserRole + 1
ROW_HEADER, ROW_RESOURCE, ROW_CLASSWORK = range(3)

SORTS = [("recent", "Date Added"), ("title", "Title"), ("kind", "Type"), ("size", "Size")]


@dataclass
class _Row:
    kind: int
    id: str = ""
    title: str = ""
    subtitle: str = ""
    ext: str = ""
    date: str = ""
    size: str = ""
    tags: list[str] = field(default_factory=list)
    snippet: list[tuple[str, bool]] = field(default_factory=list)
    count: int = 0
    first: bool = False
    day: object = None
    attachment: bool = False
    payload: Resource | ClassworkEntry | None = None


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
            return row.title
        return None

    def flags(self, index):
        if not index.isValid() or self.rows[index.row()].kind == ROW_HEADER:
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def set_rows(self, rows: list[_Row]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def row_of(self, item_id: str) -> int:
        return next((i for i, r in enumerate(self.rows) if r.kind != ROW_HEADER and r.id == item_id), -1)


def _snippet_segments(text: str, tokens: list[str]) -> list[tuple[str, bool]]:
    text = re.sub(r"\s+", " ", text).strip()
    if not tokens:
        return [(text, False)]
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(t) for t in tokens) + r")\w*", re.IGNORECASE)
    out, pos = [], 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], False))
        out.append((m.group(0), True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return out


# --------------------------------------------------------------------------- delegate

class _Delegate(QStyledItemDelegate):
    ROW_H, SNIPPET_H, HEADER_H, FIRST_HEADER_H = 52, 68, 42, 32
    SIZE_W, DATE_W, GAP = 62, 112, 16

    def __init__(self, view: QListView) -> None:
        super().__init__(view)
        self.view = view
        self.f_title = font("body")
        self.f_sub = font("subheadline")
        self.f_sub_bold = font("subheadline", weight=QFont.Weight.Bold)
        self.f_meta = font("callout")
        self.f_tag = font("caption")
        self.f_head = font("headline")
        self._fm_tag = QFontMetricsF(self.f_tag)
        self._icons: dict[tuple, QPixmap] = {}
        self._capsules: dict[tuple, QPixmap] = {}
        self._texts: dict[tuple, tuple[QStaticText, float, float]] = {}

    def _icon(self, kind: int, key, dark: bool, dpr: float) -> QPixmap:
        """32px file icon / date tile rendered once per (key, appearance, scale)."""
        cache_key = (kind, key, dark, dpr)
        pm = self._icons.get(cache_key)
        if pm is None:
            pm = QPixmap(int(32 * dpr), int(32 * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pm)
            if kind == ROW_RESOURCE:
                icons.draw_file_icon(painter, QRectF(0, 0, 32, 32), key, dark)
            else:
                draw_date_tile(painter, QRectF(2, 1, 28, 30), key)
            painter.end()
            if len(self._icons) > 512:
                self._icons.clear()
            self._icons[cache_key] = pm
        return pm

    def _text(self, p: QPainter, rect: QRectF, text: str, f: QFont, right: bool = False) -> None:
        """Elided single-line text drawn from a cached QStaticText layout (pen = current color)."""
        key = (id(f), text, int(rect.width()))
        cached = self._texts.get(key)
        if cached is None:
            fm = QFontMetricsF(f)
            shown = fm.elidedText(text, Qt.TextElideMode.ElideRight, rect.width())
            st = QStaticText(shown)
            st.setTextFormat(Qt.TextFormat.PlainText)
            st.setPerformanceHint(QStaticText.PerformanceHint.AggressiveCaching)
            st.prepare(QTransform(), f)
            if len(self._texts) > 8000:
                self._texts.clear()
            cached = self._texts[key] = (st, fm.horizontalAdvance(shown), fm.height())
        st, w, h = cached
        x = rect.right() - w if right else rect.left()
        p.setFont(f)
        p.drawStaticText(QPointF(x, rect.top() + (rect.height() - h) / 2), st)

    def _capsule(self, text: str, w: int, focused: bool, dpr: float) -> QPixmap:
        pal = palette()
        key = (text, w, focused, pal.dark, dpr)
        pm = self._capsules.get(key)
        if pm is None:
            pm = QPixmap(int(w * dpr), int(18 * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 52) if focused else pal.fill)
            r = QRectF(0, 0, w, 18)
            painter.drawRoundedRect(r, 9, 9)
            painter.setFont(self.f_tag)
            painter.setPen(pal.selection_text if focused else pal.secondary_label)
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter,
                             painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(w - 12)))
            painter.end()
            if len(self._capsules) > 2000:
                self._capsules.clear()
            self._capsules[key] = pm
        return pm

    def clear_caches(self) -> None:
        self._icons.clear()
        self._capsules.clear()

    def sizeHint(self, option, index):  # noqa: N802
        row = index.data(ROW_ROLE)
        w = self.view.viewport().width()
        if row is None:
            return QSize(w, self.ROW_H)
        if row.kind == ROW_HEADER:
            return QSize(w, self.FIRST_HEADER_H if row.first else self.HEADER_H)
        return QSize(w, self.SNIPPET_H if row.snippet else self.ROW_H)

    def _tag_layout(self, tags: list[str], max_w: float) -> list[tuple[str, float]]:
        out, used = [], 0.0
        shown = tags[:3]
        for i, t in enumerate(shown):
            w = min(math.ceil(self._fm_tag.horizontalAdvance(t)) + 16, 110)
            rest = len(tags) - (i + 1)
            reserve = (math.ceil(self._fm_tag.horizontalAdvance(f"+{rest}")) + 16 + 4) if rest else 0
            if used + w + reserve > max_w:
                break
            out.append((t, w))
            used += w + 4
        hidden = len(tags) - len(out)
        if hidden:
            label = f"+{hidden}"
            w = math.ceil(self._fm_tag.horizontalAdvance(label)) + 16
            if used + w <= max_w:
                out.append((label, w))
        return out

    def paint(self, p: QPainter, option, index):
        row: _Row | None = index.data(ROW_ROLE)
        if row is None:
            return
        pal = palette()
        rect = QRectF(option.rect)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if row.kind == ROW_HEADER:
            self._paint_header(p, rect, row)
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

        top = plate.top() + (self.ROW_H - 2 - 34) / 2
        icon_rect = QRectF(plate.left() + 8, top + 1, 32, 32)
        dpr = self.view.devicePixelRatioF()
        pm = self._icon(row.kind, row.ext if row.kind == ROW_RESOURCE else row.day, pal.dark, dpr)
        p.drawPixmap(icon_rect.topLeft(), pm)

        right = plate.right() - 12
        avail = plate.width()
        show_size, show_tags, show_date = avail > 560, avail > 470, avail > 340
        p.setPen(secondary)
        if show_size:
            size_rect = QRectF(right - self.SIZE_W, top, self.SIZE_W, 34)
            if row.kind == ROW_RESOURCE:
                self._text(p, size_rect, row.size, self.f_meta, right=True)
            elif row.attachment:
                icons.draw_icon(p, "paperclip", QRectF(right - 14, size_rect.center().y() - 7, 14, 14), secondary)
            right -= self.SIZE_W + self.GAP
        if show_date:
            self._text(p, QRectF(right - self.DATE_W, top, self.DATE_W, 34), row.date, self.f_meta)
            right -= self.DATE_W + self.GAP

        x = icon_rect.right() + 12
        if show_tags and row.tags:
            max_w = min(230.0, (right - x) * 0.45)
            tags = self._tag_layout(row.tags, max_w)
            total = sum(w for _, w in tags) + 4 * max(0, len(tags) - 1)
            tx = right - total
            ty = top + (34 - 18) / 2
            for text, w in tags:
                p.drawPixmap(QPointF(tx, ty), self._capsule(text, int(w), focused, dpr))
                tx += w + 4
            if tags:
                right -= total + 14

        text_w = max(20.0, right - x)
        p.setPen(primary)
        self._text(p, QRectF(x, top, text_w, 18), row.title, self.f_title)
        p.setPen(secondary)
        self._text(p, QRectF(x, top + 18, text_w, 16), row.subtitle, self.f_sub)
        if row.snippet:
            self._paint_snippet(p, QRectF(x, top + 35, plate.right() - 12 - x, 16), row.snippet,
                                secondary, primary)
        p.restore()

    def _paint_header(self, p: QPainter, rect: QRectF, row: _Row) -> None:
        pal = palette()
        r = rect.adjusted(20, 0, -20, -6)
        p.setFont(self.f_head)
        p.setPen(pal.label)
        p.drawText(r, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, row.title)
        tw = p.fontMetrics().horizontalAdvance(row.title)
        p.setFont(self.f_sub)
        p.setPen(pal.secondary_label)
        p.drawText(r.adjusted(tw + 6, 0, 0, -1), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                   str(row.count))

    def _paint_snippet(self, p: QPainter, rect: QRectF, segments, color: QColor, strong: QColor) -> None:
        x = rect.left()
        for text, bold in segments:
            f = self.f_sub_bold if bold else self.f_sub
            p.setFont(f)
            fm = p.fontMetrics()
            w = fm.horizontalAdvance(text)
            remaining = rect.right() - x
            if remaining <= 8:
                break
            p.setPen(strong if bold else color)
            if w > remaining:
                p.drawText(QRectF(x, rect.top(), remaining, rect.height()),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           fm.elidedText(text, Qt.TextElideMode.ElideRight, int(remaining)))
                break
            p.drawText(QRectF(x, rect.top(), w + 1, rect.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            x += w


# --------------------------------------------------------------------------- list view

class _ListView(QListView):
    open_requested = Signal(QModelIndex)
    delete_requested = Signal(QModelIndex)
    space_pressed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(26)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setMouseTracking(True)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setViewportMargins(0, 6, 0, 6)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        actions.smooth_scroll(self)

    def keyPressEvent(self, e):
        idx = self.currentIndex()
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if idx.isValid():
                self.open_requested.emit(idx)
            return
        if e.key() == Qt.Key.Key_Space and not e.modifiers():
            self.space_pressed.emit()
            return
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if idx.isValid():
                self.delete_requested.emit(idx)
            return
        super().keyPressEvent(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.viewport().update()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.viewport().update()


# --------------------------------------------------------------------------- small widgets

class _PillBar(QWidget):
    """Row of capsule filters ("All" + topics) that scrolls horizontally when it overflows."""

    changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[tuple[str | None, str]] = []
        self._selected: str | None = None
        self._hover = -1
        self._offset = 0.0
        self._font = font("body")
        self._font_sel = font("headline")
        self.setFixedHeight(26)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        theme().changed.connect(self.update)

    def set_items(self, items: list[tuple[str, str]], selected: str | None = None) -> None:
        self._items = [(None, "All")] + list(items)
        self._selected = selected
        self._offset = 0.0
        self.update()

    def selected(self) -> str | None:
        return self._selected

    def items(self) -> list[tuple[str, str]]:
        return self._items[1:]

    def _rects(self) -> list[QRectF]:
        fm = QFontMetricsF(self._font_sel)
        out, x = [], 0.0
        for _, text in self._items:
            w = fm.horizontalAdvance(text) + 26
            out.append(QRectF(x - self._offset, 0, w, 26))
            x += w + 6
        return out

    def _content_width(self) -> float:
        rects = self._rects()
        return (rects[-1].right() + self._offset) if rects else 0.0

    def minimumSizeHint(self):  # noqa: N802
        return QSize(60, 26)

    def sizeHint(self):  # noqa: N802
        return QSize(int(self._content_width()), 26)

    def _index_at(self, x: float) -> int:
        return next((i for i, r in enumerate(self._rects()) if r.left() <= x <= r.right()), -1)

    def mouseMoveEvent(self, e):
        i = self._index_at(e.position().x())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        i = self._index_at(e.position().x())
        if e.button() == Qt.MouseButton.LeftButton and i >= 0:
            tid = self._items[i][0]
            if tid != self._selected:
                self._selected = tid
                self.update()
                self.changed.emit(tid)

    def wheelEvent(self, e):
        overflow = self._content_width() - self.width()
        if overflow <= 0:
            e.ignore()
            return
        delta = e.angleDelta().x() or e.angleDelta().y()
        self._offset = max(0.0, min(overflow, self._offset - delta / 2))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        for i, (r, (tid, text)) in enumerate(zip(self._rects(), self._items)):
            if r.right() < 0 or r.left() > self.width():
                continue
            selected = tid == self._selected
            if selected:
                fill = pal.accent
            else:
                fill = pal.fill_hover if i == self._hover else pal.fill
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(r, 13, 13)
            p.setFont(self._font_sel if selected else self._font)
            p.setPen(pal.on_accent if selected else pal.label)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
        overflow = self._content_width() - self.width()
        for at_right, visible in ((True, overflow - self._offset > 1), (False, self._offset > 1)):
            if not visible:
                continue
            w = 28
            x0 = self.width() - w if at_right else 0
            grad = QLinearGradient(x0, 0, x0 + w, 0)
            clear = with_alpha(pal.window, 0)
            grad.setColorAt(0, clear if at_right else pal.window)
            grad.setColorAt(1, pal.window if at_right else clear)
            p.fillRect(QRectF(x0, 0, w, self.height()), grad)


class _ModuleGlyph(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = "blue"
        self.setFixedSize(22, 22)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        icons.draw_icon(p, "folder_fill", QRectF(1, 1, 20, 20), system_color(self._color))


class _DropOverlay(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._text = ""
        self.hide()

    def set_text(self, text: str) -> None:
        self._text = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect()).adjusted(10, 8, -10, -10)
        path = icons.squircle_path(r, 12)
        p.fillPath(path, with_alpha(pal.window, 215))
        p.fillPath(path, with_alpha(pal.accent, 26 if not pal.dark else 40))
        p.setPen(QPen(pal.accent, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(icons.squircle_path(r.adjusted(1, 1, -1, -1), 11))
        c = r.center()
        icons.draw_icon(p, "tray_down", QRectF(c.x() - 24, c.y() - 44, 48, 48), pal.accent)
        p.setFont(font("title3"))
        p.setPen(pal.accent)
        p.drawText(QRectF(r.left(), c.y() + 12, r.width(), 24), Qt.AlignmentFlag.AlignCenter, self._text)


class _InspectorHost(QWidget):
    """Clips the inspector and animates its width when it is shown or hidden."""

    def __init__(self, inspector: Inspector, open_: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.inspector = inspector
        inspector.setParent(self)
        self._open = open_
        self.setFixedWidth(INSPECTOR_WIDTH if open_ else 0)
        self._anim = QVariantAnimation(self, duration=220, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: self.setFixedWidth(int(v)))

    def is_open(self) -> bool:
        return self._open

    def set_open(self, on: bool, animate: bool = True) -> None:
        self._open = on
        target = INSPECTOR_WIDTH if on else 0
        self._anim.stop()
        if animate and self.isVisible():
            self._anim.setStartValue(self.width())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.setFixedWidth(target)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.inspector.setGeometry(0, 0, INSPECTOR_WIDTH, self.height())


# --------------------------------------------------------------------------- the view

class LibraryView(QWidget):
    """All Resources / Recently Added / module / search results, with an inspector pane."""

    add_resource_requested = Signal(object, list)
    edit_resource_requested = Signal(str)
    log_classwork_requested = Signal(object)
    edit_classwork_requested = Signal(str)
    explain_resource_requested = Signal(str)

    def __init__(self, library: Library, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library
        self.settings = settings
        self._mode = settings.mode() or MODE_INTERN
        self._view = "all"
        self._module_id: str | None = None
        self._topic_id: str | None = None
        self._query = ""
        self._previous: tuple[str, str | None] = ("all", None)
        self._sort = "recent"
        self._kind: str | None = None
        self._segment = 0
        self._dirty = False
        self._inspector_pending = False
        self._inspector_throttle = QTimer(self, singleShot=True, interval=90)
        self._inspector_throttle.timeout.connect(self._on_throttle)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._build_toolbar()
        root.addWidget(self.toolbar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self._main = QWidget()
        main_lay = QVBoxLayout(self._main)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        self._filters = QWidget()
        f_lay = QHBoxLayout(self._filters)
        f_lay.setContentsMargins(20, 10, 16, 4)
        f_lay.setSpacing(12)
        self._pills = _PillBar()
        self._pills.changed.connect(self._on_topic)
        self._segments = SegmentedControl(["Resources", "Classwork"])
        self._segments.currentChanged.connect(self._on_segment)
        f_lay.addWidget(self._pills, 1)
        f_lay.addWidget(self._segments)
        main_lay.addWidget(self._filters)

        self._stack = QStackedWidget()
        self.list = _ListView()
        self.model = _Model()
        self.list.setModel(self.model)
        self.delegate = _Delegate(self.list)
        self.list.setItemDelegate(self.delegate)
        self.list.selectionModel().currentChanged.connect(self._on_current)
        self.list.selectionModel().selectionChanged.connect(self._on_current)
        self.list.doubleClicked.connect(self._activate)
        self.list.open_requested.connect(self._activate)
        self.list.delete_requested.connect(self._on_delete_key)
        self.list.space_pressed.connect(lambda: self._inspector_btn.click())
        self.list.customContextMenuRequested.connect(self._context_menu)
        self._empty = actions.EmptyState()
        self._empty.action_clicked.connect(self._request_add)
        self.classwork = ClassworkView(library, settings, embedded=True)
        self.classwork.log_classwork_requested.connect(self.log_classwork_requested)
        self.classwork.edit_classwork_requested.connect(self.edit_classwork_requested)
        for w in (self.list, self._empty, self.classwork):
            self._stack.addWidget(w)
        main_lay.addWidget(self._stack, 1)
        body.addWidget(self._main, 1)

        self.inspector = Inspector(library, settings)
        self.inspector.edit_requested.connect(self.edit_resource_requested)
        self.inspector.edit_classwork_requested.connect(self.edit_classwork_requested)
        self.inspector.explain_requested.connect(self.explain_resource_requested)
        visible = settings.get_bool(KEY_INSPECTOR_VISIBLE, True)
        self._inspector_host = _InspectorHost(self.inspector, visible)
        self._inspector_btn.setChecked(visible)
        body.addWidget(self._inspector_host)
        root.addLayout(body, 1)

        self._overlay = _DropOverlay(self._main)
        self._main.installEventFilter(self)

        library.changed.connect(self._on_library_changed)
        theme().changed.connect(self._on_theme)
        self._apply_mode()
        self.show_all()

    # ------------------------------------------------------------------ toolbar
    def _build_toolbar(self) -> None:
        self.toolbar = Toolbar("All Resources")
        for lbl in self.toolbar.findChildren(QLabel):
            lbl.setMinimumWidth(40)
        self._glyph = _ModuleGlyph()
        self._glyph.hide()
        self.toolbar.add_leading(self._glyph)
        self._sort_btn = IconButton("filter", "Sort and Filter")
        self._sort_btn.clicked.connect(self._show_sort_menu)
        self._log_btn = IconButton("calendar", "Log Classwork\u2026")
        self._log_btn.clicked.connect(lambda: self.log_classwork_requested.emit(self._module_id))
        self._add_btn = IconButton("plus", "Add Resource\u2026")
        self._add_btn.clicked.connect(self._request_add)
        self._inspector_btn = IconButton("sidebar_right", "Hide Inspector")
        self._inspector_btn.setCheckable(True)
        self._inspector_btn.toggled.connect(self._on_inspector_toggled)
        for w in (self._sort_btn, self._log_btn, self._add_btn):
            self.toolbar.add_action(w)
        self.toolbar.add_spacing(4)
        self.toolbar.add_action(self._inspector_btn)

    def _show_sort_menu(self) -> None:
        menu = actions.make_menu(self)
        actions.menu_header(menu, "Sort By")
        for sid, name in SORTS:
            act = menu.addAction(actions.menu_icon("check" if self._sort == sid else None), name)
            act.triggered.connect(lambda _=False, s=sid: self._set_sort(s))
        menu.addSeparator()
        actions.menu_header(menu, "Show")
        kinds = [(None, "All Types")] + [(k, name) for k, name, _ in RESOURCE_KINDS]
        for kid, name in kinds:
            act = menu.addAction(actions.menu_icon("check" if self._kind == kid else None), name)
            act.triggered.connect(lambda _=False, k=kid: self._set_kind(k))
        actions.popup_below(menu, self._sort_btn)

    def _set_sort(self, sort: str) -> None:
        self._sort = sort
        self.refresh()

    def _set_kind(self, kind: str | None) -> None:
        self._kind = kind
        self.refresh()

    # ------------------------------------------------------------------ public API
    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._apply_mode()
        self.inspector.set_mode(mode)
        self.classwork.set_mode(mode)
        self.refresh()

    def show_all(self) -> None:
        self._navigate("all")

    def show_recent(self) -> None:
        self._navigate("recent")

    def show_module(self, module_id: str) -> None:
        if self.library.module(module_id) is None:
            self.show_all()
            return
        self._navigate("module", module_id)

    def show_search(self, query: str) -> None:
        query = query.strip()
        if not query:
            kind, arg = self._previous
            self._navigate(kind, arg)
            return
        if self._view != "search":
            self._previous = (self._view, self._module_id)
        self._query = query
        self._view = "search"
        self._module_id = None
        self._topic_id = None
        self.refresh(reset_scroll=True)

    def select_resource(self, resource_id: str) -> None:
        if self._dirty:
            self.refresh()
        row = self.model.row_of(resource_id)
        if row < 0 and (self._kind or self._topic_id):
            self._kind = None
            self._topic_id = None
            self.refresh()
            row = self.model.row_of(resource_id)
        if row < 0:
            return
        if self._view == "module" and self._segment != 0:
            self._segments.setCurrentIndex(0)
        idx = self.model.index(row)
        self.list.setCurrentIndex(idx)
        self.list.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)
        self._inspector_throttle.stop()
        self._inspector_pending = False
        self._update_inspector()

    def refresh(self, reset_scroll: bool = False) -> None:
        if not self.isVisible() and not reset_scroll and self.model.rows:
            self._dirty = True
            return
        self._dirty = False
        selected_id = self._current_id()
        old_row = self.list.currentIndex().row()
        scroll = 0 if reset_scroll else self.list.verticalScrollBar().value()
        modules = {m.id: m for m in self.library.modules()}
        if self._view == "module" and self._module_id not in modules:
            self._view, self._module_id, self._topic_id = "all", None, None

        rows, total = self._build_rows(modules)
        self.model.set_rows(rows)
        self.list.setUniformItemSizes(self._view != "search")
        self._update_chrome(modules, total)

        row = self.model.row_of(selected_id) if selected_id else -1
        if row < 0 and selected_id and 0 <= old_row and self.model.rows:
            row = self._nearest_selectable(min(old_row, len(self.model.rows) - 1))
        self.list.doItemsLayout()
        if row >= 0:
            idx = self.model.index(row)
            self.list.selectionModel().setCurrentIndex(idx, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self._inspector_throttle.stop()
        self._inspector_pending = False
        self._update_inspector()
        self.list.verticalScrollBar().setValue(scroll)
        if row >= 0 and reset_scroll:
            self.list.scrollTo(self.model.index(row))

    # ------------------------------------------------------------------ rows
    def _navigate(self, view: str, module_id: str | None = None) -> None:
        changed = (view, module_id) != (self._view, self._module_id)
        self._view = view
        self._module_id = module_id if view == "module" else None
        self._query = ""
        if changed:
            self._topic_id = None
            self.list.clearSelection()
            self.list.setCurrentIndex(QModelIndex())
        if view == "module":
            self.classwork.show_module(module_id, None)
        self.refresh(reset_scroll=changed)

    def _resource_rows(self, resources: list[Resource], modules: dict, show_module: bool,
                       tokens: list[str] | None = None) -> list[_Row]:
        rows = []
        for r in resources:
            m = modules.get(r.module_id)
            topic = m.topic(r.topic_id) if m else None
            parts = []
            if show_module:
                parts.append(m.name if m else "Unsorted")
            if topic:
                parts.append(topic.name)
            parts.append(KIND_NAMES.get(r.kind, "Other"))
            snippet: list[tuple[str, bool]] = []
            if tokens:
                text = self.library.match_snippet(r.id, self._query)
                low = text.lower()
                if text and any(re.search(r"(?<!\w)" + re.escape(t), low) for t in tokens):
                    snippet = _snippet_segments(text, tokens)
            rows.append(_Row(ROW_RESOURCE, id=r.id, title=r.title, subtitle=" \u00b7 ".join(parts), ext=r.ext,
                             date=actions.relative_date(r.created_at), size=actions.human_size(r.size),
                             tags=list(r.keywords), snippet=snippet, payload=r))
        return rows

    def _classwork_rows(self, entries: list[ClassworkEntry], modules: dict) -> list[_Row]:
        rows = []
        for e in entries:
            m = modules.get(e.module_id)
            topic = m.topic(e.topic_id) if m else None
            parts = [m.name if m else "Unsorted"] + ([topic.name] if topic else []) + ["Classwork"]
            d = actions.parse_iso(e.date)
            rows.append(_Row(ROW_CLASSWORK, id=e.id, title=e.title, subtitle=" \u00b7 ".join(parts),
                             date=actions.medium_date(d) if d else e.date, day=d,
                             attachment=bool(e.attachment), payload=e))
        return rows

    def _build_rows(self, modules: dict) -> tuple[list[_Row], int]:
        if self._view == "search":
            tokens = [t.lower() for t in re.findall(r"\w+", self._query)]
            resources = self.library.search(self._query)
            if self._kind:
                resources = [r for r in resources if r.kind == self._kind]
            entries = self.library.search_classwork(self._query)
            rows: list[_Row] = []
            if resources:
                rows.append(_Row(ROW_HEADER, title="Resources", count=len(resources), first=True))
                rows += self._resource_rows(resources, modules, True, tokens)
            if entries:
                rows.append(_Row(ROW_HEADER, title="Classwork", count=len(entries), first=not rows))
                rows += self._classwork_rows(entries, modules)
            return rows, len(resources) + len(entries)
        if self._view == "recent":
            resources = self.library.recent(50)
            if self._kind:
                resources = [r for r in resources if r.kind == self._kind]
            keys = {"title": lambda r: r.title.lower(), "kind": lambda r: (r.kind, r.title.lower()),
                    "size": lambda r: -r.size}
            if self._sort in keys:
                resources.sort(key=keys[self._sort])
        elif self._view == "module":
            resources = self.library.resources(module_id=self._module_id, topic_id=self._topic_id,
                                               kind=self._kind, sort=self._sort)
        else:
            resources = self.library.resources(kind=self._kind, sort=self._sort)
        return self._resource_rows(resources, modules, self._view != "module"), len(resources)

    def _nearest_selectable(self, row: int) -> int:
        rows = self.model.rows
        for r in list(range(row, len(rows))) + list(range(row - 1, -1, -1)):
            if rows[r].kind != ROW_HEADER:
                return r
        return -1

    # ------------------------------------------------------------------ chrome
    def _update_chrome(self, modules: dict, total: int) -> None:
        in_module = self._view == "module"
        m = modules.get(self._module_id) if in_module else None
        self._glyph.setVisible(m is not None)
        if m is not None:
            self._glyph.set_color(m.color)
            self._pills.setVisible(bool(m.topics))
            items = [(t.id, t.name) for t in m.topics]
            if self._pills.items() != items or self._pills.selected() != self._topic_id:
                self._pills.set_items(items, self._topic_id)
        self._filters.setVisible(in_module)
        classwork_page = in_module and self._segment == 1
        if self._view == "search":
            title = "Search Results"
            subtitle = (f"{actions.plural(total, 'result')} for \u201c{self._query}\u201d" if total
                        else f"No results for \u201c{self._query}\u201d")
        elif in_module and m is not None:
            title = m.name
            if classwork_page:
                n = len(self.library.classwork(module_id=m.id, topic_id=self._topic_id))
                subtitle = actions.plural(n, "entry", "entries") if n else "No entries"
            else:
                subtitle = actions.plural(total, "resource") if total else "No resources"
            if m.description and len(m.description) <= 64:
                subtitle += f" \u00b7 {m.description}"
        else:
            title = "Recently Added" if self._view == "recent" else "All Resources"
            subtitle = actions.plural(total, "resource") if total else "No resources"
            if self._kind:
                subtitle += f" \u00b7 {KIND_NAMES.get(self._kind, '')}"
        self.toolbar.set_title(title, subtitle)
        self._sort_btn.setVisible(not classwork_page)
        self._sort_btn.setColor(palette().accent if self._kind else None)
        self._sort_btn.setToolTip("Sort and Filter" if self._view != "search" else "Filter")
        self._log_btn.setVisible(in_module and self._mode == MODE_FACILITATOR)
        self._inspector_btn.setVisible(not classwork_page)
        self._inspector_host.setVisible(not classwork_page)

        if classwork_page:
            self._stack.setCurrentWidget(self.classwork)
        elif self.model.rows:
            self._stack.setCurrentWidget(self.list)
        else:
            self._update_empty(m)
            self._stack.setCurrentWidget(self._empty)

    def _update_empty(self, m) -> None:
        facilitator = self._mode == MODE_FACILITATOR
        if self._view == "search":
            self._empty.set_content("search", "No Results", f"No resources match \u201c{self._query}\u201d.")
            return
        if self._kind or self._topic_id:
            self._empty.set_content("filter", "No Matching Resources",
                                    "Try a different topic or type.")
            return
        if m is not None:
            message = (f"Drag files here or click + to add the first resource to {m.name}." if facilitator
                       else f"Nothing has been added to {m.name} yet.")
            self._empty.set_content("folder", "No Resources Yet", message,
                                    "Add Resource\u2026" if facilitator else "")
            return
        message = ("Drag files here or click + to add your first resource." if facilitator
                   else "Your facilitators haven\u2019t added anything yet.")
        self._empty.set_content("tray_down", "No Resources Yet", message, "Add Resource\u2026" if facilitator else "")

    def _apply_mode(self) -> None:
        facilitator = self._mode == MODE_FACILITATOR
        self._add_btn.setVisible(facilitator)
        self._log_btn.setVisible(facilitator and self._view == "module")
        self.setAcceptDrops(facilitator)

    # ------------------------------------------------------------------ selection & actions
    def _row(self, idx: QModelIndex) -> _Row | None:
        row = idx.data(ROW_ROLE) if idx.isValid() else None
        return row if row is not None and row.kind != ROW_HEADER else None

    def _current_id(self) -> str | None:
        row = self._row(self.list.currentIndex())
        if row is not None and self.list.selectionModel().isSelected(self.list.currentIndex()):
            return row.id
        return None

    def _on_current(self, *_) -> None:
        if self._inspector_throttle.isActive():
            self._inspector_pending = True
            return
        self._update_inspector()
        self._inspector_throttle.start()

    def _on_throttle(self) -> None:
        if self._inspector_pending:
            self._inspector_pending = False
            self._update_inspector()
            self._inspector_throttle.start()

    def _update_inspector(self) -> None:
        row = self._row(self.list.currentIndex())
        if row is not None and not self.list.selectionModel().isSelected(self.list.currentIndex()):
            row = None
        if row is None:
            self.inspector.clear()
        elif row.kind == ROW_RESOURCE:
            self.inspector.set_resource(row.payload)
        else:
            self.inspector.set_classwork(row.payload)

    def _activate(self, idx: QModelIndex) -> None:
        row = self._row(idx)
        if row is None:
            return
        if row.kind == ROW_RESOURCE:
            actions.open_resource(self.library, row.payload, self)
        elif row.payload.attachment and self._mode != MODE_FACILITATOR:
            actions.open_attachment(self.library, row.payload, self)
        elif self._mode == MODE_FACILITATOR:
            self.edit_classwork_requested.emit(row.id)
        elif row.payload.attachment:
            actions.open_attachment(self.library, row.payload, self)

    def _on_delete_key(self, idx: QModelIndex) -> None:
        row = self._row(idx)
        if row is None or self._mode != MODE_FACILITATOR:
            return
        if row.kind == ROW_RESOURCE:
            actions.delete_resource(self.library, row.payload, self)
        else:
            actions.delete_classwork(self.library, row.payload, self)

    def _context_menu(self, pos) -> None:
        idx = self.list.indexAt(pos)
        row = self._row(idx)
        if row is None:
            return
        self.list.setCurrentIndex(idx)
        menu = actions.make_menu(self)
        facilitator = self._mode == MODE_FACILITATOR
        if row.kind == ROW_RESOURCE:
            r = row.payload
            menu.addAction("Open", lambda: actions.open_resource(self.library, r, self))
            menu.addAction("Download\u2026", lambda: actions.download_resource(self.library, r, self))
            menu.addAction("Show in Folder", lambda: actions.show_in_folder(self.library, r, self))
            if facilitator:
                menu.addSeparator()
                menu.addAction("Edit\u2026", lambda: self.edit_resource_requested.emit(r.id))
                menu.addAction("Delete\u2026", lambda: actions.delete_resource(self.library, r, self))
        else:
            e = row.payload
            if e.attachment:
                menu.addAction("Open Attachment", lambda: actions.open_attachment(self.library, e, self))
                menu.addAction("Download Attachment\u2026",
                               lambda: actions.download_attachment(self.library, e, self))
                menu.addAction("Show in Folder", lambda: actions.show_attachment_in_folder(self.library, e, self))
            if facilitator:
                if e.attachment:
                    menu.addSeparator()
                menu.addAction("Edit\u2026", lambda: self.edit_classwork_requested.emit(e.id))
                menu.addAction("Delete\u2026", lambda: actions.delete_classwork(self.library, e, self))
        if menu.actions():
            menu.exec(self.list.viewport().mapToGlobal(pos))

    def _request_add(self) -> None:
        self.add_resource_requested.emit(self._module_id if self._view == "module" else None, [])

    def _on_topic(self, topic_id: str | None) -> None:
        self._topic_id = topic_id
        self.classwork.set_topic(topic_id)
        self.refresh(reset_scroll=True)

    def _on_segment(self, index: int) -> None:
        self._segment = index
        if index == 1 and self._module_id:
            self.classwork.show_module(self._module_id, self._topic_id)
        self.refresh()

    def _on_inspector_toggled(self, on: bool) -> None:
        self._inspector_host.set_open(on)
        self._inspector_btn.setToolTip("Hide Inspector" if on else "Show Inspector")
        if self.settings.get_bool(KEY_INSPECTOR_VISIBLE, True) != on:
            self.settings.set_bool(KEY_INSPECTOR_VISIBLE, on)

    def _on_library_changed(self, _part: str) -> None:
        self.refresh()

    def _on_theme(self) -> None:
        self._sort_btn.setColor(palette().accent if self._kind else None)
        self.list.viewport().update()
        self.update()

    # ------------------------------------------------------------------ drag and drop
    @staticmethod
    def _dropped_files(event) -> list[Path]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile() and Path(u.toLocalFile()).is_file()]

    def dragEnterEvent(self, e):
        if self._mode != MODE_FACILITATOR or not self._dropped_files(e):
            e.ignore()
            return
        m = self.library.module(self._module_id) if self._view == "module" else None
        self._overlay.set_text(f"Drop to Add to {m.name}" if m else "Drop to Add to the Library")
        self._overlay.setGeometry(self._main.rect())
        self._overlay.show()
        self._overlay.raise_()
        e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._overlay.hide()

    def dropEvent(self, e):
        self._overlay.hide()
        files = self._dropped_files(e)
        if files and self._mode == MODE_FACILITATOR:
            e.acceptProposedAction()
            self.add_resource_requested.emit(self._module_id if self._view == "module" else None, files)

    # ------------------------------------------------------------------ Qt overrides
    def eventFilter(self, obj, event):
        if obj is self._main and event.type() == QEvent.Type.Resize and self._overlay.isVisible():
            self._overlay.setGeometry(self._main.rect())
        return super().eventFilter(obj, event)

    def showEvent(self, e):
        super().showEvent(e)
        if self._dirty:
            self.refresh()

    def paintEvent(self, _):
        QPainter(self).fillRect(self.rect(), palette().window)
