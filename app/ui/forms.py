"""Shared macOS-style form widgets for the sheets: tokens, drop zones, dates, colors and lists."""
from __future__ import annotations

import atexit
import math
import re
from pathlib import Path
from typing import Callable, Iterable

import shiboken6
from PySide6.QtCore import (QCoreApplication, QDate, QEvent, QLocale, QObject, QPoint, QPointF, QRect, QRectF, QSize,
                            Qt, QThread, Signal, Slot)
from PySide6.QtGui import QColor, QFontMetrics, QFontMetricsF, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QFileDialog, QHBoxLayout,
                               QLabel, QLayout, QLineEdit, QListWidget, QSizePolicy, QStyle, QStyledItemDelegate,
                               QToolTip, QVBoxLayout, QWidget, QWidgetItem)

from .. import icons
from ..constants import MODULE_COLORS, RESOURCE_KINDS
from ..theme import font, palette, rgba, system_color, with_alpha
from .controls import IconButton, Separator, make_button, on_theme_change

ColorSource = QColor | Callable[[], QColor] | None

# --------------------------------------------------------------------------- helpers

_KINDS = {
    "pdf": "PDF document", "doc": "Word document", "docx": "Word document", "rtf": "Rich text document",
    "odt": "OpenDocument text", "pages": "Pages document", "ppt": "PowerPoint presentation",
    "pptx": "PowerPoint presentation", "key": "Keynote presentation", "odp": "OpenDocument presentation",
    "xls": "Excel spreadsheet", "xlsx": "Excel spreadsheet", "csv": "CSV document", "numbers": "Numbers spreadsheet",
    "ods": "OpenDocument spreadsheet", "txt": "Plain text", "md": "Markdown document", "html": "HTML document",
    "htm": "HTML document", "json": "JSON document", "py": "Python script", "ipynb": "Jupyter notebook",
    "js": "JavaScript file", "ts": "TypeScript file", "java": "Java source", "c": "C source", "cpp": "C++ source",
    "sql": "SQL file", "css": "CSS stylesheet", "png": "PNG image", "jpg": "JPEG image", "jpeg": "JPEG image",
    "gif": "GIF image", "webp": "WebP image", "svg": "SVG image", "heic": "HEIC image", "bmp": "BMP image",
    "mp4": "MPEG-4 movie", "mov": "QuickTime movie", "mkv": "Matroska video", "webm": "WebM video",
    "mp3": "MP3 audio", "wav": "WAV audio", "m4a": "MPEG-4 audio", "zip": "ZIP archive", "rar": "RAR archive",
    "7z": "7-Zip archive", "gz": "Gzip archive", "tar": "Tar archive",
}


def file_kind(ext: str) -> str:
    """Finder-style kind description for a file extension ("PDF document")."""
    ext = (ext or "").lower().lstrip(".")
    return _KINDS.get(ext, f"{ext.upper()} file" if ext else "Document")


def human_size(n: int) -> str:
    try:
        from ..core.extract import human_size as _human_size
        return _human_size(int(n))
    except Exception:
        pass
    value = float(max(0, int(n or 0)))
    if value < 1000:
        return f"{int(value)} bytes"
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1000.0
        if value < 1000 or unit == "TB":
            return f"{value:.1f} {unit}" if value < 10 and unit != "KB" else f"{value:.0f} {unit}"
    return f"{value:.0f} TB"


def prettify_stem(stem: str) -> str:
    """'intro_to-python' -> 'Intro To Python' (keeps the casing of mixed-case names)."""
    text = re.sub(r"[_\-]+", " ", stem or "")
    text = re.sub(r"\s+", " ", text).strip()
    if text and text == text.lower():
        text = " ".join(w[:1].upper() + w[1:] for w in text.split(" "))
    return text


def merge_keywords(current: Iterable[str], extra: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for kw in [*current, *extra]:
        kw = re.sub(r"\s+", " ", str(kw)).strip().strip(",;#").strip()
        if kw and kw.lower() not in seen:
            seen.add(kw.lower())
            out.append(kw)
    return out


_last_dir: list[str] = []


def choose_file(parent: QWidget | None, title: str = "Choose a File") -> Path | None:
    """Native open-file dialog; remembers the last folder."""
    start = _last_dir[0] if _last_dir else str(Path.home() / "Documents" if (Path.home() / "Documents").is_dir()
                                               else Path.home())
    path, _ = QFileDialog.getOpenFileName(parent, title, start)
    if not path:
        return None
    p = Path(path)
    _last_dir[:] = [str(p.parent)]
    return p


def local_files(mime) -> list[Path]:
    if mime is None or not mime.hasUrls():
        return []
    out = []
    for url in mime.urls():
        if url.isLocalFile():
            p = Path(url.toLocalFile())
            if p.is_file():
                out.append(p)
    return out


def _resolve(color: ColorSource, default: Callable[[], QColor]) -> QColor:
    if callable(color):
        return color()
    return QColor(color) if color is not None else default()


def fit_row(row: QWidget, height: int = 40) -> None:
    """Trim a GroupBox row's vertical padding so rows with fields stay `height` px tall."""
    lay = row.layout()
    if lay is None:
        return
    content = 0
    for i in range(lay.count()):
        item = lay.itemAt(i)
        if item is not None:
            content = max(content, item.sizeHint().height())
    pad = max(4, (height - content) // 2)
    m = lay.contentsMargins()
    lay.setContentsMargins(m.left(), pad, m.right(), pad)


def add_label_accessory(row: QWidget, widget: QWidget) -> None:
    """Place `widget` right after a GroupBox row's label (e.g. a sparkle badge)."""
    label = row.findChild(QLabel, "rowLabel")
    lay = _layout_containing(row.layout(), label) if label is not None else None
    if lay is None:
        return
    idx = lay.indexOf(label)
    lay.insertWidget(idx + 1, widget, 0, Qt.AlignmentFlag.AlignVCenter)
    if isinstance(lay, QHBoxLayout) and not any(lay.itemAt(i).spacerItem() for i in range(lay.count())):
        lay.addStretch(1)


def _layout_containing(layout: QLayout | None, widget: QWidget) -> QLayout | None:
    if layout is None:
        return None
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() is widget:
            return layout
        if item.layout() is not None:
            found = _layout_containing(item.layout(), widget)
            if found is not None:
                return found
    return None


class _Reaper(QObject):
    """Holds Python references to running threads until they finish, then deletes them."""

    def __init__(self) -> None:
        super().__init__()
        self.alive: set[QThread] = set()
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)
        atexit.register(self.shutdown)

    def keep(self, thread: QThread) -> None:
        self.alive.add(thread)
        thread.finished.connect(self._release)

    def shutdown(self) -> None:
        """Give running threads a moment; never let Python destroy one that is still running."""
        for thread in list(self.alive):
            try:
                if not shiboken6.isValid(thread):
                    continue
                if thread.isRunning():
                    thread.requestInterruption()
                    thread.wait(1500)
                if thread.isRunning():
                    shiboken6.invalidate(thread)
            except Exception:
                pass

    @Slot()
    def _release(self) -> None:
        thread = self.sender()
        if thread in self.alive:
            self.alive.discard(thread)
            thread.deleteLater()


_reaper: _Reaper | None = None


def keep_thread(thread: QThread) -> QThread:
    """Start-and-forget safety: the thread object survives (even if its owner is closed) until finished."""
    global _reaper
    if _reaper is None:
        _reaper = _Reaper()
    _reaper.keep(thread)
    return thread


def tint_badges(row: QWidget, color_name: str) -> None:
    """Keep a row's SymbolBadge in the system color for the current appearance."""
    from .sheet import SymbolBadge

    def apply():
        for badge in row.findChildren(SymbolBadge):
            badge.set_color(system_color(color_name))

    on_theme_change(row, apply)


# --------------------------------------------------------------------------- small pieces

class Glyph(QWidget):
    """A single SF-style glyph. `color` may be a QColor or a callable (resolved at paint time)."""

    def __init__(self, icon: str, color: ColorSource = None, size: int = 16, parent: QWidget | None = None,
                 weight: float = 1.0) -> None:
        super().__init__(parent)
        self._icon, self._color, self._weight = icon, color, weight
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        on_theme_change(self, self.update, call_now=False)

    def set_icon(self, icon: str, color: ColorSource = None) -> None:
        self._icon = icon
        if color is not None:
            self._color = color
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        icons.draw_icon(p, self._icon, QRectF(self.rect()), _resolve(self._color, lambda: palette().secondary_label),
                        self._weight)


class SparkleBadge(Glyph):
    """Tiny purple sparkles shown next to a field Gemini filled in."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("sparkles", lambda: system_color("purple"), 13, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setToolTip("Suggested by Gemini")
        self.hide()


class ElidedLabel(QLabel):
    """Single-line label that elides its text to the available width."""

    def __init__(self, text: str = "", mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._refresh()

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text or ""
        self._refresh()
        self.updateGeometry()

    def text(self) -> str:
        return self._full

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self._full) + 2, fm.height())

    def minimumSizeHint(self) -> QSize:
        return QSize(min(40, self.sizeHint().width()), QFontMetrics(self.font()).height())

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.Type.FontChange:
            self._refresh()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._refresh()

    def _refresh(self) -> None:
        fm = QFontMetrics(self.font())
        super().setText(fm.elidedText(self._full, self._mode, max(0, self.width())))


class StatusLabel(QWidget):
    """Footnote with an optional leading glyph. kind: info | ok | error | ai."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = "info"
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(5)
        self._glyph = Glyph("info_circle", self._glyph_color, 13)
        glyph_box = QVBoxLayout()
        glyph_box.setContentsMargins(0, 1, 0, 0)
        glyph_box.addWidget(self._glyph)
        glyph_box.addStretch(1)
        lay.addLayout(glyph_box)
        self._label = QLabel()
        self._label.setFont(font("subheadline"))
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._label, 1)
        self.hide()
        on_theme_change(self, self._apply_theme)

    def _glyph_color(self) -> QColor:
        pal = palette()
        return {"ok": pal.green, "error": pal.red, "ai": system_color("purple")}.get(self._kind, pal.secondary_label)

    def set_status(self, text: str, kind: str = "info") -> None:
        self._kind = kind
        self._label.setText(text or "")
        name = {"ok": "checkmark_circle_fill", "error": "exclamation_circle", "ai": "sparkles"}.get(kind)
        self._glyph.setVisible(name is not None)
        if name:
            self._glyph.set_icon(name)
        self._apply_theme()
        self.setVisible(bool(text))

    def clear(self) -> None:
        self.set_status("")

    def text(self) -> str:
        return self._label.text()

    def kind(self) -> str:
        return self._kind

    def _apply_theme(self) -> None:
        pal = palette()
        color = pal.red if self._kind == "error" else pal.secondary_label
        self._label.setStyleSheet(f"color: {rgba(color)};")
        self._glyph.update()


class _FileIcon(QWidget):
    def __init__(self, size: int = 40, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ext = ""
        self.setFixedSize(size, size)
        on_theme_change(self, self.update, call_now=False)

    def set_ext(self, ext: str) -> None:
        self._ext = ext
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        icons.draw_file_icon(p, QRectF(self.rect()), self._ext, palette().dark)


# --------------------------------------------------------------------------- flow layout

class FlowLayout(QLayout):
    """Left-to-right wrapping layout; an optional last "stretch" widget fills the rest of its line."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 4, line_spacing: int = 4) -> None:
        super().__init__(parent)
        self._items: list = []
        self._h, self._v = spacing, line_spacing
        self._stretch: QWidget | None = None
        self._stretch_min = 80

    def set_stretch_widget(self, widget: QWidget, min_width: int = 80) -> None:
        self._stretch, self._stretch_min = widget, min_width

    def insert_widget(self, index: int, widget: QWidget) -> None:
        self.addChildWidget(widget)
        self._items.insert(max(0, min(index, len(self._items))), QWidgetItem(widget))
        self.invalidate()

    def addItem(self, item) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int):  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int):  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize(self._stretch_min, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect: QRect, test: bool) -> int:
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = eff.x(), eff.y(), 0
        right = eff.x() + eff.width()
        for item in self._items:
            w = item.widget()
            if w is not None and w.isHidden() and w is not self._stretch:
                continue
            hint = item.sizeHint()
            width = hint.width()
            if w is not None and w is self._stretch:
                avail = right - x
                if avail < self._stretch_min and x > eff.x():
                    x, y, line_h = eff.x(), y + line_h + self._v, 0
                    avail = eff.width()
                width = max(10, avail)
            elif x + width > right and x > eff.x():
                x, y, line_h = eff.x(), y + line_h + self._v, 0
            if not test:
                item.setGeometry(QRect(QPoint(x, y), QSize(min(width, max(10, eff.width())), hint.height())))
            x += width + self._h
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + m.bottom()


# --------------------------------------------------------------------------- token field

class _Token(QWidget):
    remove_requested = Signal(object)
    pressed = Signal(object)

    H = 20

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.text = text
        self.selected = False
        self._hover = False
        self.setFont(font("callout"))
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setToolTip(text)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        advance = math.ceil(QFontMetricsF(self.font()).horizontalAdvance(self.text))
        return QSize(min(220, max(40, advance + 26)), self.H)

    def _close_rect(self) -> QRectF:
        return QRectF(self.width() - 16, (self.height() - 12) / 2, 12, 12)

    def set_selected(self, on: bool) -> None:
        self.selected = on
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if (self._hover or self.selected) and self._close_rect().adjusted(-3, -3, 3, 3).contains(e.position()):
                self.remove_requested.emit(self)
            else:
                self.pressed.emit(self)
        e.accept()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.selected:
            bg = pal.accent
            fg = pal.on_accent
        else:
            bg = pal.fill_hover if self._hover else pal.fill
            fg = pal.label
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setFont(self.font())
        p.setPen(fg)
        fm = QFontMetricsF(self.font())
        active = self._hover or self.selected
        if active:
            text_rect, align = QRectF(8, 0, self.width() - 26, self.height()), Qt.AlignmentFlag.AlignLeft
        else:
            text_rect, align = QRectF(8, 0, self.width() - 16, self.height()), Qt.AlignmentFlag.AlignHCenter
        p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | align,
                   fm.elidedText(self.text, Qt.TextElideMode.ElideRight, text_rect.width() + 1))
        if active:
            color = with_alpha(pal.on_accent, 220) if self.selected else pal.secondary_label
            icons.draw_icon(p, "xmark_circle_fill", self._close_rect(), color)


class _TokenInput(QLineEdit):
    def __init__(self, owner: "TokenField") -> None:
        super().__init__(owner)
        self._owner = owner
        self.setFont(font("body"))
        self.setFrame(False)
        self.setFixedHeight(_Token.H)
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        self.setStyleSheet("QLineEdit { background: transparent; border: none; padding: 0px; margin: 0px; }")

    def sizeHint(self) -> QSize:
        return QSize(80, _Token.H)

    def minimumSizeHint(self) -> QSize:
        return QSize(10, _Token.H)

    def event(self, e):
        if e.type() == QEvent.Type.KeyPress and e.key() == Qt.Key.Key_Tab and self.text().strip():
            if not self._owner._pick_suggestion():
                self._owner._commit_input()
            return True
        return super().event(e)

    def keyPressEvent(self, e: QKeyEvent):
        owner = self._owner
        key = e.key()
        popup = owner._popup
        if popup.isVisible():
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                popup.move_selection(1 if key == Qt.Key.Key_Down else -1)
                return
            if key == Qt.Key.Key_Escape:
                popup.hide()
                return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if owner._pick_suggestion():
                return
            if self.text().strip():
                owner._commit_input()
                e.accept()
                return
            e.ignore()
            return
        if e.text() in (",", ";"):
            owner._commit_input()
            return
        if key == Qt.Key.Key_Backspace and not self.text():
            owner._backspace()
            return
        if key == Qt.Key.Key_Left and not self.text() and owner._tokens:
            owner._backspace(select_only=True)
            return
        owner._select(None)
        super().keyPressEvent(e)


class _SuggestionPopup(QWidget):
    """Non-activating rounded menu of keyword completions shown under a TokenField."""

    picked = Signal(str)

    M = 10
    ROW = 24
    MAX_ROWS = 8

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setFont(font("body"))
        self._items: list[str] = []
        self._current = -1
        self._query = ""
        self.hide()

    def show_items(self, items: list[str], query: str, anchor: QWidget) -> None:
        self._items = items[: self.MAX_ROWS]
        self._query = query
        self._current = -1
        if not self._items:
            self.hide()
            return
        width = max(200, min(anchor.width(), 300))
        self.setFixedSize(width + 2 * self.M, len(self._items) * self.ROW + 10 + 2 * self.M)
        g = anchor.mapToGlobal(QPoint(0, anchor.height() + 3))
        x, y = g.x() - self.M, g.y() - self.M + 2
        screen = anchor.screen().availableGeometry() if anchor.screen() else None
        if screen is not None and y + self.height() > screen.bottom():
            y = anchor.mapToGlobal(QPoint(0, 0)).y() - self.height() + self.M - 3
        self.move(x, y)
        self.show()
        self.raise_()
        self.update()

    def current(self) -> str | None:
        return self._items[self._current] if 0 <= self._current < len(self._items) else None

    def move_selection(self, delta: int) -> None:
        if not self._items:
            return
        if self._current < 0:
            self._current = 0 if delta > 0 else len(self._items) - 1
        else:
            self._current = (self._current + delta) % len(self._items)
        self.update()

    def _row_at(self, y: float) -> int:
        i = int((y - self.M - 5) // self.ROW)
        return i if 0 <= i < len(self._items) else -1

    def mouseMoveEvent(self, e):
        i = self._row_at(e.position().y())
        if i != self._current:
            self._current = i
            self.update()

    def mousePressEvent(self, e):
        i = self._row_at(e.position().y())
        if i >= 0 and e.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self._items[i])

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        card = QRectF(self.rect()).adjusted(self.M, self.M, -self.M, -self.M)
        for i in range(self.M, 0, -2):
            a = int((9 if not pal.dark else 20) * (1 - i / self.M))
            p.fillPath(icons.squircle_path(card.adjusted(-i, -i + 3, i, i + 3), 8 + i), QColor(0, 0, 0, a))
        bg = QColor(pal.menu)
        bg.setAlpha(255)
        p.fillPath(icons.squircle_path(card, 8), bg)
        p.setPen(QPen(pal.menu_border, 1))
        p.drawPath(icons.squircle_path(card.adjusted(0.5, 0.5, -0.5, -0.5), 8))
        fm = QFontMetricsF(self.font())
        for i, text in enumerate(self._items):
            row = QRectF(card.left() + 5, card.top() + 5 + i * self.ROW, card.width() - 10, self.ROW)
            selected = i == self._current
            if selected:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(pal.accent)
                p.drawRoundedRect(row, 5, 5)
            p.setPen(pal.on_accent if selected else pal.label)
            p.setFont(self.font())
            p.drawText(row.adjusted(9, 0, -9, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       fm.elidedText(text, Qt.TextElideMode.ElideRight, row.width() - 18))


class TokenField(QWidget):
    """Keyword chips editor (macOS tag field) with wrapping tokens and autocompletion."""

    changed = Signal()

    def __init__(self, completions: Iterable[str] = (), placeholder: str = "Add keywords",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens: list[_Token] = []
        self._selected: _Token | None = None
        self._placeholder = placeholder
        self._completions: list[str] = []
        self._last_h = 0
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._flow = FlowLayout(self, 4, 4)
        self._flow.setContentsMargins(5, 4, 5, 4)
        self._input = _TokenInput(self)
        self._flow.addWidget(self._input)
        self._flow.set_stretch_widget(self._input, 90)
        self._input.installEventFilter(self)
        self._input.textEdited.connect(self._on_text_edited)

        self._popup = _SuggestionPopup(self)
        self._popup.picked.connect(self._on_completion)
        self.set_completions(completions)
        self._update_placeholder()
        on_theme_change(self, self._apply_theme)

    # ------------------------------------------------------------------ public API
    def tokens(self) -> list[str]:
        return [t.text for t in self._tokens]

    def set_tokens(self, tokens: Iterable[str]) -> None:
        for t in self._tokens:
            self._flow.removeWidget(t)
            t.deleteLater()
        self._tokens.clear()
        self._selected = None
        for text in merge_keywords([], tokens):
            self._insert(text)
        self._after_change(emit=True)

    def add_token(self, text: str) -> bool:
        text = re.sub(r"\s+", " ", str(text)).strip().strip(",;#").strip()
        if not text or text.lower() in {t.lower() for t in self.tokens()}:
            return False
        self._insert(text)
        self._after_change(emit=True)
        return True

    def commit_pending(self) -> None:
        """Turn any typed-but-uncommitted text into a token."""
        if self._input.text().strip():
            self._commit_input()

    def set_completions(self, words: Iterable[str]) -> None:
        self._completions = [w for w in words if w]

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self._update_placeholder()

    def input(self) -> QLineEdit:
        return self._input

    def setFocus(self, *args) -> None:  # noqa: N802
        self._input.setFocus(*args)

    # ------------------------------------------------------------------ internals
    def _insert(self, text: str) -> None:
        tok = _Token(text, self)
        tok.remove_requested.connect(self._remove)
        tok.pressed.connect(self._on_token_pressed)
        self._flow.insert_widget(len(self._tokens), tok)
        self._tokens.append(tok)
        tok.show()

    def _remove(self, tok: _Token) -> None:
        if tok not in self._tokens:
            return
        self._tokens.remove(tok)
        if self._selected is tok:
            self._selected = None
        self._flow.removeWidget(tok)
        tok.deleteLater()
        self._after_change(emit=True)
        self._input.setFocus()

    def _on_token_pressed(self, tok: _Token) -> None:
        self._select(None if self._selected is tok else tok)
        self._input.setFocus()

    def _select(self, tok: _Token | None) -> None:
        if self._selected is tok:
            return
        if self._selected is not None:
            self._selected.set_selected(False)
        self._selected = tok
        if tok is not None:
            tok.set_selected(True)

    def _backspace(self, select_only: bool = False) -> None:
        if not self._tokens:
            return
        if self._selected is not None and not select_only:
            self._remove(self._selected)
        else:
            self._select(self._tokens[-1])

    def _commit_input(self) -> None:
        parts = re.split(r"[,;]", self._input.text())
        self._input.clear()
        self._popup.hide()
        added = False
        for part in parts:
            text = re.sub(r"\s+", " ", part).strip().strip("#").strip()
            if text and text.lower() not in {t.lower() for t in self.tokens()}:
                self._insert(text)
                added = True
        if added:
            self._after_change(emit=True)

    def _on_completion(self, text: str) -> None:
        self._popup.hide()
        self._input.clear()
        self.add_token(text)
        self._input.setFocus()

    def _pick_suggestion(self) -> bool:
        """Accept the highlighted completion, if any."""
        choice = self._popup.current() if self._popup.isVisible() else None
        if choice is None:
            return False
        self._on_completion(choice)
        return True

    def _matches(self, query: str) -> list[str]:
        q = query.lower()
        used = {t.lower() for t in self.tokens()}
        starts, contains = [], []
        for w in self._completions:
            lw = w.lower()
            if lw in used or lw == q:
                continue
            if lw.startswith(q):
                starts.append(w)
            elif q in lw:
                contains.append(w)
        return starts + contains

    def _on_text_edited(self, text: str) -> None:
        self._select(None)
        if "," in text or ";" in text:
            self._commit_input()
            return
        query = text.strip()
        if not query or not self._completions:
            self._popup.hide()
            return
        self._popup.show_items(self._matches(query), query, self)

    def hideEvent(self, e):
        self._popup.hide()
        super().hideEvent(e)

    def _after_change(self, emit: bool) -> None:
        self._update_placeholder()
        self._flow.invalidate()
        self.updateGeometry()
        self._sync_height()
        if emit:
            self.changed.emit()

    def _update_placeholder(self) -> None:
        self._input.setPlaceholderText("" if self._tokens else self._placeholder)

    def _sync_height(self) -> None:
        h = self._flow.heightForWidth(max(self.width(), 100))
        if h != self._last_h:
            self._last_h = h
            self.setFixedHeight(h)

    def sizeHint(self) -> QSize:
        return QSize(260, self._flow.heightForWidth(max(self.width(), 260)))

    def minimumSizeHint(self) -> QSize:
        return QSize(120, _Token.H + 8)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._sync_height()

    def mousePressEvent(self, e):
        self._select(None)
        self._input.setFocus()
        self._input.setCursorPosition(len(self._input.text()))
        e.accept()

    def eventFilter(self, obj, event):
        if obj is self._input and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            if event.type() == QEvent.Type.FocusOut:
                self._popup.hide()
                reason = event.reason()
                if reason not in (Qt.FocusReason.PopupFocusReason, Qt.FocusReason.ActiveWindowFocusReason):
                    self._select(None)
                    self.commit_pending()
            self.update()
        return super().eventFilter(obj, event)

    def _apply_theme(self) -> None:
        pal = palette()
        self._popup.update()
        self._input.setStyleSheet(
            "QLineEdit { background: transparent; border: none; padding: 0px; margin: 0px;"
            f" color: {rgba(pal.label)}; selection-background-color: {rgba(with_alpha(pal.accent, 90))}; }}"
        )
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = icons.squircle_path(r, 6)
        p.fillPath(path, pal.field)
        p.setPen(QPen(pal.accent if self._input.hasFocus() else pal.field_border, 1))
        p.drawPath(path)


# --------------------------------------------------------------------------- drop zone

class DropZone(QWidget):
    """Dashed drop target with "Choose File…", turning into a file card once a file is chosen."""

    file_changed = Signal(object)  # Path | None

    EMPTY_H = 112
    CARD_H = 64

    def __init__(self, parent: QWidget | None = None, prompt: str = "Drop a file here") -> None:
        super().__init__(parent)
        self._path: Path | None = None
        self._existing: tuple[str, int, str] | None = None
        self._drag = False
        self._clearable = True
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._empty = QWidget()
        ev = QVBoxLayout(self._empty)
        ev.setContentsMargins(16, 18, 16, 12)
        ev.setSpacing(2)
        self._glyph = Glyph("upload", lambda: palette().accent if self._drag else palette().secondary_label, 26,
                            weight=1.05)
        ev.addWidget(self._glyph, 0, Qt.AlignmentFlag.AlignHCenter)
        ev.addSpacing(6)
        self._prompt = QLabel(prompt)
        self._prompt.setFont(font("body"))
        ev.addWidget(self._prompt, 0, Qt.AlignmentFlag.AlignHCenter)
        self._choose = make_button("Choose File\u2026", "plain")
        self._choose.clicked.connect(self._pick)
        ev.addWidget(self._choose, 0, Qt.AlignmentFlag.AlignHCenter)
        ev.addStretch(1)
        lay.addWidget(self._empty)

        self._card = QWidget()
        cl = QHBoxLayout(self._card)
        cl.setContentsMargins(12, 10, 10, 10)
        cl.setSpacing(12)
        self._icon = _FileIcon(40)
        cl.addWidget(self._icon)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        texts.addStretch(1)
        self._name = ElidedLabel(mode=Qt.TextElideMode.ElideMiddle)
        self._name.setFont(font("headline"))
        texts.addWidget(self._name)
        self._detail = QLabel()
        self._detail.setFont(font("subheadline"))
        texts.addWidget(self._detail)
        texts.addStretch(1)
        cl.addLayout(texts, 1)
        self._replace = make_button("Replace\u2026", "plain")
        self._replace.clicked.connect(self._pick)
        cl.addWidget(self._replace)
        self._clear = IconButton("xmark", "Remove", 22, 11)
        self._clear.clicked.connect(self._on_clear)
        cl.addWidget(self._clear)
        lay.addWidget(self._card)

        on_theme_change(self, self._apply_theme)
        self._refresh()

    # ------------------------------------------------------------------ API
    def path(self) -> Path | None:
        return self._path

    def set_path(self, path: Path | str | None) -> None:
        new = Path(path) if path else None
        if new == self._path:
            self._refresh()
            return
        self._path = new
        self._refresh()
        self.file_changed.emit(new)

    def set_existing(self, name: str | None, size: int = 0, ext: str = "") -> None:
        """Show a file that is already in the library (edit mode); `path()` stays None."""
        self._existing = (name, int(size or 0), ext or Path(name).suffix.lstrip(".")) if name else None
        self._path = None
        self._refresh()

    def has_file(self) -> bool:
        return self._path is not None or self._existing is not None

    def set_clearable(self, on: bool) -> None:
        self._clearable = on
        self._refresh()

    def set_prompt(self, text: str) -> None:
        self._prompt.setText(text)

    # ------------------------------------------------------------------ internals
    def _pick(self) -> None:
        p = choose_file(self, "Choose a File")
        if p is not None:
            self.set_path(p)

    def _on_clear(self) -> None:
        self.set_path(None)

    def _refresh(self) -> None:
        has = self.has_file()
        self._empty.setVisible(not has)
        self._card.setVisible(has)
        self.setFixedHeight(self.CARD_H if has else self.EMPTY_H)
        if self._path is not None:
            try:
                size = self._path.stat().st_size
            except OSError:
                size = 0
            name, ext = self._path.name, self._path.suffix.lstrip(".")
        elif self._existing is not None:
            name, size, ext = self._existing
        else:
            name, size, ext = "", 0, ""
        self._name.setText(name)
        self._name.setToolTip(str(self._path) if self._path else name)
        self._detail.setText(f"{human_size(size)} \u00b7 {file_kind(ext)}" if has else "")
        self._icon.set_ext(ext)
        self._clear.setVisible(self._clearable or (self._path is not None and self._existing is not None))
        self._clear.setToolTip("Keep the current file" if self._existing is not None else "Remove")
        self.update()

    def _apply_theme(self) -> None:
        pal = palette()
        self._prompt.setStyleSheet(f"color: {rgba(pal.secondary_label)};")
        self._name.setStyleSheet(f"color: {rgba(pal.label)};")
        self._detail.setStyleSheet(f"color: {rgba(pal.secondary_label)};")
        self.update()

    def dragEnterEvent(self, e):
        if local_files(e.mimeData()):
            e.acceptProposedAction()
            self._drag = True
            self.update()
            self._glyph.update()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._drag = False
        self.update()
        self._glyph.update()

    def dropEvent(self, e):
        files = local_files(e.mimeData())
        self._drag = False
        self._glyph.update()
        if files:
            e.acceptProposedAction()
            self.set_path(files[0])
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = icons.squircle_path(r, 10)
        if self.has_file():
            p.fillPath(path, with_alpha(pal.accent, 22) if self._drag else pal.group)
            p.setPen(QPen(pal.accent if self._drag else pal.group_border, 1.5 if self._drag else 1))
            p.drawPath(icons.squircle_path(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10))
            return
        if self._drag:
            p.fillPath(path, with_alpha(pal.accent, 22))
        pen = QPen(pal.accent if self._drag else pal.tertiary_label, 1.5)
        pen.setDashPattern([4, 3])
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawPath(path)


# --------------------------------------------------------------------------- attachment field

class AttachmentField(QWidget):
    """Compact optional attachment: "Attach File…" button, or a file chip with a remove button."""

    file_changed = Signal(object)  # Path | None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path: Path | None = None
        self._existing: tuple[str, int, str] | None = None
        self._removed = False
        self._drag = False
        self.setAcceptDrops(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addStretch(1)
        self._attach = make_button("Attach File\u2026")
        self._attach.clicked.connect(self._pick)
        lay.addWidget(self._attach)

        self._chip = QWidget()
        self._chip.setObjectName("attachChip")
        cl = QHBoxLayout(self._chip)
        cl.setContentsMargins(6, 2, 2, 2)
        cl.setSpacing(6)
        self._icon = _FileIcon(20)
        cl.addWidget(self._icon)
        self._name = ElidedLabel(mode=Qt.TextElideMode.ElideMiddle)
        self._name.setFont(font("callout"))
        self._name.setMaximumWidth(190)
        cl.addWidget(self._name)
        self._size = QLabel()
        self._size.setFont(font("subheadline"))
        cl.addWidget(self._size)
        self._remove = IconButton("xmark_circle_fill", "Remove Attachment", 20, 13)
        self._remove.clicked.connect(self.clear)
        cl.addWidget(self._remove)
        lay.addWidget(self._chip)
        self._replace = make_button("Replace\u2026", "plain")
        self._replace.clicked.connect(self._pick)
        lay.addWidget(self._replace)
        on_theme_change(self, self._apply_theme)
        self._refresh()

    def path(self) -> Path | None:
        return self._path

    def set_path(self, path: Path | str | None) -> None:
        self._path = Path(path) if path else None
        if self._path is not None:
            self._removed = self._existing is not None
        self._refresh()
        self.file_changed.emit(self._path)

    def set_existing(self, name: str | None, size: int = 0, ext: str = "") -> None:
        self._existing = (name, int(size or 0), ext or Path(name).suffix.lstrip(".")) if name else None
        self._path = None
        self._removed = False
        self._refresh()

    def removed_existing(self) -> bool:
        """True when an existing attachment was removed or replaced."""
        return self._removed

    def clear(self) -> None:
        if self._existing is not None:
            self._removed = True
        self._path = None
        self._refresh()
        self.file_changed.emit(None)

    def _shown(self) -> tuple[str, int, str] | None:
        if self._path is not None:
            try:
                size = self._path.stat().st_size
            except OSError:
                size = 0
            return self._path.name, size, self._path.suffix.lstrip(".")
        if self._existing is not None and not self._removed:
            return self._existing
        return None

    def _pick(self) -> None:
        p = choose_file(self, "Attach a File")
        if p is not None:
            self.set_path(p)

    def _refresh(self) -> None:
        shown = self._shown()
        self._attach.setVisible(shown is None)
        self._chip.setVisible(shown is not None)
        self._replace.setVisible(shown is not None)
        if shown:
            name, size, ext = shown
            self._name.setText(name)
            self._name.setToolTip(name)
            self._size.setText(human_size(size) if size else "")
            self._icon.set_ext(ext)
        self.update()

    def _apply_theme(self) -> None:
        pal = palette()
        self._attach.setIcon(icons.make_icon("paperclip", pal.secondary_label, 14))
        self._chip.setStyleSheet(f"#attachChip {{ background: {rgba(pal.fill)}; border-radius: 6px; }}")
        self._name.setStyleSheet(f"color: {rgba(pal.label)};")
        self._size.setStyleSheet(f"color: {rgba(pal.secondary_label)};")
        self._remove.setColor(pal.tertiary_label)

    def dragEnterEvent(self, e):
        if local_files(e.mimeData()):
            e.acceptProposedAction()
            self._drag = True
            self.update()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._drag = False
        self.update()

    def dropEvent(self, e):
        files = local_files(e.mimeData())
        self._drag = False
        if files:
            e.acceptProposedAction()
            self.set_path(files[0])
        self.update()

    def paintEvent(self, _):
        if not self._drag:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(pal.accent, 1.5))
        p.setBrush(with_alpha(pal.accent, 22))
        p.drawRoundedRect(r, 6, 6)


# --------------------------------------------------------------------------- date field

def _medium_date_format() -> str:
    short = QLocale.system().dateFormat(QLocale.FormatType.ShortFormat).strip().lower()
    return "MMM d, yyyy" if short.startswith("m") else "d MMM yyyy"


class _TodayButton(IconButton):
    """The small dot between the month arrows that jumps to today."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("sparkle", "Today", 22, 12, parent)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        if self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pal.fill_pressed if self.isDown() else pal.fill_hover)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.label if self.underMouse() else pal.secondary_label)
        p.drawEllipse(QRectF(self.rect()).center(), 3.2, 3.2)


class _CalendarPopup(QWidget):
    """Compact macOS-style month calendar shown below a DateField."""

    picked = Signal(QDate)

    M = 12          # shadow margin
    CELL_W, CELL_H = 30, 26

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._selected = QDate.currentDate()
        self._focus = QDate.currentDate()
        self._month = QDate(self._focus.year(), self._focus.month(), 1)
        self._hover: QDate | None = None
        self._first_dow = QLocale.system().firstDayOfWeek().value
        self.closed_at = 0

        self._prev = IconButton("chevron_left", "Previous Month", 22, 12, self)
        self._today = _TodayButton(self)
        self._next = IconButton("chevron_right", "Next Month", 22, 12, self)
        self._prev.clicked.connect(lambda: self._shift_month(-1))
        self._next.clicked.connect(lambda: self._shift_month(1))
        self._today.clicked.connect(self._go_today)
        w = self.M * 2 + 12 + self.CELL_W * 7
        h = self.M * 2 + 10 + 26 + 22 + self.CELL_H * 6 + 8
        self.setFixedSize(w, h)
        y = self.M + 10
        right = w - self.M - 8
        self._next.move(right - 22, y)
        self._today.move(right - 44, y)
        self._prev.move(right - 66, y)

    def show_for(self, field: QWidget, date: QDate) -> None:
        self._selected = QDate(date)
        self._focus = QDate(date)
        self._month = QDate(date.year(), date.month(), 1)
        g = field.mapToGlobal(QPoint(0, field.height() + 4))
        x = g.x() + field.width() - self.width() + self.M
        y = g.y() - self.M + 2
        screen = field.screen().availableGeometry() if field.screen() else None
        if screen is not None:
            x = max(screen.left(), min(x, screen.right() - self.width()))
            if y + self.height() > screen.bottom():
                y = field.mapToGlobal(QPoint(0, 0)).y() - self.height() + self.M - 4
        self.move(x, y)
        self.show()
        self.setFocus()

    def hideEvent(self, e):
        from time import monotonic
        self.closed_at = monotonic()
        super().hideEvent(e)

    # geometry
    def _grid_origin(self) -> QPointF:
        return QPointF(self.M + 6, self.M + 10 + 26 + 22)

    def _grid_start(self) -> QDate:
        offset = (self._month.dayOfWeek() - self._first_dow) % 7
        return self._month.addDays(-offset)

    def _date_at(self, pos: QPointF) -> QDate | None:
        o = self._grid_origin()
        col = int((pos.x() - o.x()) // self.CELL_W)
        row = int((pos.y() - o.y()) // self.CELL_H)
        if 0 <= col < 7 and 0 <= row < 6 and pos.x() >= o.x() and pos.y() >= o.y():
            return self._grid_start().addDays(row * 7 + col)
        return None

    def _shift_month(self, n: int) -> None:
        self._month = self._month.addMonths(n)
        self._focus = self._focus.addMonths(n)
        self.update()

    def _go_today(self) -> None:
        today = QDate.currentDate()
        self._month = QDate(today.year(), today.month(), 1)
        self._focus = today
        self.update()

    def _set_focus_date(self, d: QDate) -> None:
        self._focus = d
        if d.year() != self._month.year() or d.month() != self._month.month():
            self._month = QDate(d.year(), d.month(), 1)
        self.update()

    # events
    def mouseMoveEvent(self, e):
        d = self._date_at(e.position())
        if d != self._hover:
            self._hover = d
            self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, e):
        d = self._date_at(e.position())
        if d is not None and e.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(d)
            self.hide()

    def wheelEvent(self, e):
        self._shift_month(-1 if e.angleDelta().y() > 0 else 1)

    def keyPressEvent(self, e):
        k = e.key()
        moves = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_Up: -7, Qt.Key.Key_Down: 7}
        if k in moves:
            self._set_focus_date(self._focus.addDays(moves[k]))
        elif k == Qt.Key.Key_PageUp:
            self._set_focus_date(self._focus.addMonths(-1))
        elif k == Qt.Key.Key_PageDown:
            self._set_focus_date(self._focus.addMonths(1))
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.picked.emit(self._focus)
            self.hide()
        elif k == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        card = QRectF(self.rect()).adjusted(self.M, self.M, -self.M, -self.M)
        for i in range(self.M, 0, -2):
            a = int((10 if not pal.dark else 22) * (1 - i / self.M))
            p.fillPath(icons.squircle_path(card.adjusted(-i, -i + 4, i, i + 4), 10 + i), QColor(0, 0, 0, a))
        bg = QColor(pal.menu)
        bg.setAlpha(255)
        p.fillPath(icons.squircle_path(card, 10), bg)
        p.setPen(QPen(pal.menu_border, 1))
        p.drawPath(icons.squircle_path(card.adjusted(0.5, 0.5, -0.5, -0.5), 10))

        loc = QLocale.system()
        p.setFont(font("headline"))
        p.setPen(pal.label)
        title = f"{loc.standaloneMonthName(self._month.month(), QLocale.FormatType.LongFormat)} {self._month.year()}"
        p.drawText(QRectF(card.left() + 12, card.top() + 10, 140, 22),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title)

        o = self._grid_origin()
        p.setFont(font("subheadline", weight=font("headline").weight()))
        p.setPen(pal.secondary_label)
        for col in range(7):
            dow = (self._first_dow - 1 + col) % 7 + 1
            name = loc.standaloneDayName(dow, QLocale.FormatType.NarrowFormat)
            p.drawText(QRectF(o.x() + col * self.CELL_W, o.y() - 22, self.CELL_W, 20), Qt.AlignmentFlag.AlignCenter,
                       name)

        today = QDate.currentDate()
        start = self._grid_start()
        body = font("callout")
        bold = font("callout", weight=font("headline").weight())
        for i in range(42):
            d = start.addDays(i)
            cell = QRectF(o.x() + (i % 7) * self.CELL_W, o.y() + (i // 7) * self.CELL_H, self.CELL_W, self.CELL_H)
            dot = QRectF(cell.center().x() - 11, cell.center().y() - 11, 22, 22)
            in_month = d.month() == self._month.month()
            selected = d == self._selected
            p.setPen(Qt.PenStyle.NoPen)
            if selected:
                p.setBrush(pal.accent)
                p.drawEllipse(dot)
            elif d == self._hover or (d == self._focus and self.hasFocus() and d != self._selected
                                      and self._focus != self._selected):
                p.setBrush(pal.fill_hover)
                p.drawEllipse(dot)
            if selected:
                color = pal.on_accent
            elif d == today:
                color = pal.red
            elif not in_month:
                color = pal.tertiary_label
            else:
                color = pal.label
            p.setFont(bold if d == today or selected else body)
            p.setPen(color)
            p.drawText(cell, Qt.AlignmentFlag.AlignCenter, str(d.day()))


class DateField(QDateEdit):
    """Date field ("6 Oct 2026") with keyboard editing and a macOS-style calendar popup."""

    date_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDisplayFormat(_medium_date_format())
        self.setCalendarPopup(False)
        self.setButtonSymbols(QDateEdit.ButtonSymbols.NoButtons)
        self.setFont(font("body"))
        self.setDate(QDate.currentDate())
        self.setMinimumWidth(150)
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        self._btn = IconButton("calendar", "Show Calendar", 22, 14, self)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self._toggle_popup)
        self._popup = _CalendarPopup(self)
        self._popup.picked.connect(self._on_picked)
        self.dateChanged.connect(lambda d: self.date_changed.emit(d.toString("yyyy-MM-dd")))
        on_theme_change(self, self._apply_theme)

    def date_iso(self) -> str:
        return self.date().toString("yyyy-MM-dd")

    def set_date_iso(self, value: str | None) -> None:
        d = QDate.fromString(value or "", "yyyy-MM-dd")
        self.setDate(d if d.isValid() else QDate.currentDate())

    def _toggle_popup(self) -> None:
        from time import monotonic
        if self._popup.isVisible() or monotonic() - self._popup.closed_at < 0.25:
            self._popup.hide()
            return
        self._popup.show_for(self, self.date())

    def _on_picked(self, d: QDate) -> None:
        self.setDate(d)
        self.setFocus()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space or (e.key() == Qt.Key.Key_Down and e.modifiers() & Qt.KeyboardModifier.AltModifier):
            self._toggle_popup()
            return
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            e.ignore()
            return
        super().keyPressEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._btn.move(self.width() - self._btn.width() - 3, (self.height() - self._btn.height()) // 2)

    def _apply_theme(self) -> None:
        pal = palette()
        self.setStyleSheet(
            f"QDateEdit {{ background: {rgba(pal.field)}; color: {rgba(pal.label)};"
            f" border: 1px solid {rgba(pal.field_border)}; border-radius: 6px; padding: 4px 28px 4px 8px;"
            f" selection-background-color: {rgba(with_alpha(pal.accent, 90))}; selection-color: {rgba(pal.label)}; }}"
            f"QDateEdit:focus {{ border: 1px solid {rgba(pal.accent)}; }}"
            "QDateEdit::up-button, QDateEdit::down-button { width: 0px; border: none; }"
        )
        self._btn.setColor(pal.secondary_label)


# --------------------------------------------------------------------------- color picker

class ColorPicker(QWidget):
    """Row of circular system-color swatches (like the macOS accent color picker)."""

    color_changed = Signal(str)

    def __init__(self, colors: Iterable[str] = MODULE_COLORS, size: int = 18, spacing: int = 6,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._colors = list(colors)
        self._size, self._spacing = size, spacing
        self._current = self._colors[0] if self._colors else "blue"
        self._hover = -1
        self._pad = 4
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        n = len(self._colors)
        self.setFixedSize(n * size + (n - 1) * spacing + 2 * self._pad, size + 2 * self._pad)
        on_theme_change(self, self.update, call_now=False)

    def color(self) -> str:
        return self._current

    def set_color(self, name: str) -> None:
        """Select without emitting `color_changed`."""
        if name in self._colors:
            self._current = name
            self.update()

    def _rect(self, i: int) -> QRectF:
        return QRectF(self._pad + i * (self._size + self._spacing), self._pad, self._size, self._size)

    def _index_at(self, pos: QPointF) -> int:
        for i in range(len(self._colors)):
            if self._rect(i).adjusted(-3, -3, 3, 3).contains(pos):
                return i
        return -1

    def _choose(self, i: int) -> None:
        if 0 <= i < len(self._colors) and self._colors[i] != self._current:
            self._current = self._colors[i]
            self.update()
            self.color_changed.emit(self._current)

    def event(self, e):
        if e.type() == QEvent.Type.ToolTip:
            i = self._index_at(QPointF(e.pos()))
            if i >= 0:
                QToolTip.showText(e.globalPos(), self._colors[i].capitalize(), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def mouseMoveEvent(self, e):
        i = self._index_at(e.position())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._choose(self._index_at(e.position()))

    def keyPressEvent(self, e):
        i = self._colors.index(self._current) if self._current in self._colors else 0
        if e.key() == Qt.Key.Key_Left:
            self._choose(max(0, i - 1))
        elif e.key() == Qt.Key.Key_Right:
            self._choose(min(len(self._colors) - 1, i + 1))
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        for i, name in enumerate(self._colors):
            r = self._rect(i)
            c = system_color(name)
            selected = name == self._current
            inner = r.adjusted(3, 3, -3, -3) if selected else r
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c.lighter(108) if i == self._hover and not selected else c)
            p.drawEllipse(inner)
            p.setPen(QPen(QColor(0, 0, 0, 30 if not pal.dark else 0), 0.8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(inner.adjusted(0.4, 0.4, -0.4, -0.4))
            if selected:
                p.setPen(QPen(c, 2))
                p.drawEllipse(r.adjusted(0.5, 0.5, -0.5, -0.5))
        if self.hasFocus() and self._current in self._colors:
            r = self._rect(self._colors.index(self._current)).adjusted(-3, -3, 3, 3)
            p.setPen(QPen(pal.focus_ring, 2))
            p.drawEllipse(r)


# --------------------------------------------------------------------------- pop-up buttons

def _fit_combo(combo: QComboBox, min_width: int) -> None:
    combo.setFont(font("body"))
    combo.setMinimumWidth(min_width)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setIconSize(QSize(14, 14))
    combo.setMaxVisibleItems(14)


class ModuleCombo(QComboBox):
    """Pop-up button listing modules with colored folder glyphs."""

    def __init__(self, min_width: int = 260, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._modules: list = []
        _fit_combo(self, min_width)
        self.setPlaceholderText("Choose a Module")
        on_theme_change(self, self._repaint_icons, call_now=False)

    def set_modules(self, modules, current: str | None = None) -> None:
        self.blockSignals(True)
        self._modules = list(modules)
        self.clear()
        for m in self._modules:
            self.addItem(icons.make_icon("folder_fill", system_color(m.color), 14), m.name, m.id)
        self.setCurrentIndex(-1)
        self.blockSignals(False)
        self.set_module_id(current)

    def module_id(self) -> str | None:
        return self.currentData() if self.currentIndex() >= 0 else None

    def set_module_id(self, module_id: str | None) -> None:
        idx = self.findData(module_id) if module_id else -1
        self.setCurrentIndex(idx)

    def _repaint_icons(self) -> None:
        for i, m in enumerate(self._modules):
            if i < self.count():
                self.setItemIcon(i, icons.make_icon("folder_fill", system_color(m.color), 14))


class TopicCombo(QComboBox):
    """Pop-up button with "None" plus the topics of one module."""

    def __init__(self, min_width: int = 260, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        _fit_combo(self, min_width)
        self.set_module(None)

    def set_module(self, module, current: str | None = None) -> None:
        keep = current if current is not None else self.topic_id()
        self.blockSignals(True)
        self.clear()
        self.addItem("None", None)
        if module is not None:
            for t in module.topics:
                self.addItem(t.name, t.id)
        self.setEnabled(module is not None)
        idx = self.findData(keep) if keep else 0
        self.setCurrentIndex(max(0, idx))
        self.blockSignals(False)

    def topic_id(self) -> str | None:
        return self.currentData() if self.currentIndex() > 0 else None

    def set_topic_id(self, topic_id: str | None) -> None:
        idx = self.findData(topic_id) if topic_id else 0
        self.setCurrentIndex(max(0, idx))


class KindCombo(QComboBox):
    """Pop-up button for the resource type."""

    def __init__(self, min_width: int = 170, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        _fit_combo(self, min_width)
        for kid, name, _icon in RESOURCE_KINDS:
            self.addItem(name, kid)
        on_theme_change(self, self._repaint_icons)

    def kind(self) -> str:
        return self.currentData() or "notes"

    def set_kind(self, kind: str | None) -> None:
        idx = self.findData(kind)
        self.setCurrentIndex(max(0, idx))

    def _repaint_icons(self) -> None:
        color = palette().secondary_label
        for i, (_kid, _name, icon) in enumerate(RESOURCE_KINDS):
            self.setItemIcon(i, icons.make_icon(icon, color, 14))


# --------------------------------------------------------------------------- lists with +/- bar

class RowDelegate(QStyledItemDelegate):
    """Rounded selection plates for lists (accent when focused), optional glyph per row."""

    ROW_H = 28

    def __init__(self, view: QAbstractItemView, glyph: Callable | None = None) -> None:
        super().__init__(view)
        self._view = view
        self._glyph = glyph  # index -> (icon name, QColor) | None

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), self.ROW_H)

    def paint(self, p: QPainter, option, index) -> None:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(option.rect).adjusted(5, 1, -5, -1)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        active = self._view.hasFocus() or self._view.state() == QAbstractItemView.State.EditingState
        if selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pal.selection if active else pal.selection_inactive)
            p.drawRoundedRect(r, 6, 6)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pal.hover)
            p.drawRoundedRect(r, 6, 6)
        on_accent = selected and active
        x = r.left() + 8
        glyph = self._glyph(index) if self._glyph else None
        if glyph:
            name, color = glyph
            icons.draw_icon(p, name, QRectF(x, r.center().y() - 8, 16, 16), pal.on_accent if on_accent else color)
            x += 24
        p.setFont(font("body"))
        p.setPen(pal.selection_text if on_accent else pal.label)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        tr = QRectF(x, r.top(), r.right() - x - 6, r.height())
        p.drawText(tr, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(tr.width())))
        p.restore()

    def createEditor(self, parent, option, index):  # noqa: N802
        editor = QLineEdit(parent)
        editor.setFont(font("body"))
        pal = palette()
        editor.setStyleSheet(
            f"QLineEdit {{ background: {rgba(pal.field if not pal.dark else QColor(30, 30, 32))};"
            f" color: {rgba(pal.label)}; border: 1px solid {rgba(pal.accent)}; border-radius: 5px;"
            f" padding: 0px 6px; selection-background-color: {rgba(with_alpha(pal.accent, 90))}; }}")
        return editor

    def updateEditorGeometry(self, editor, option, index):  # noqa: N802
        r = option.rect.adjusted(5, 2, -5, -2)
        if self._glyph and self._glyph(index):
            r.setLeft(r.left() + 26)
        editor.setGeometry(r)


class _BarButton(QWidget):
    clicked = Signal()

    def __init__(self, icon: str, tooltip: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon = icon
        self._down = False
        self._hover = False
        self.setFixedSize(26, 22)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        on_theme_change(self, self.update, call_now=False)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._down = True
            self.update()

    def mouseReleaseEvent(self, e):
        if self._down:
            self._down = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                self.clicked.emit()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.Type.EnabledChange:
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        pal = palette()
        if self.isEnabled() and (self._down or self._hover):
            p.fillRect(self.rect(), pal.fill_pressed if self._down else pal.fill)
        color = pal.secondary_label if self.isEnabled() else pal.quaternary_label
        if self.isEnabled() and self._hover:
            color = pal.label
        icons.draw_icon(p, self._icon, QRectF((self.width() - 11) / 2, (self.height() - 11) / 2, 11, 11), color, 1.2)


class ListPane(QWidget):
    """Rounded bordered list with the classic macOS +/- button bar along its bottom edge."""

    add_clicked = Signal()
    remove_clicked = Signal()

    def __init__(self, view: QListWidget, empty_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.view = view
        view.setFrameShape(QListWidget.Shape.NoFrame)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setMouseTracking(True)
        view.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        view.setUniformItemSizes(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 4, 1, 1)
        lay.setSpacing(0)
        lay.addWidget(view, 1)
        lay.addSpacing(3)
        lay.addWidget(Separator())
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(0)
        self.add_button = _BarButton("plus", "Add")
        self.remove_button = _BarButton("minus", "Remove")
        self.add_button.clicked.connect(self.add_clicked)
        self.remove_button.clicked.connect(self.remove_clicked)
        bar.addWidget(self.add_button)
        bar.addWidget(Separator(vertical=True))
        bar.addWidget(self.remove_button)
        bar.addWidget(Separator(vertical=True))
        bar.addStretch(1)
        lay.addLayout(bar)

        self._hint = QLabel(empty_text, view.viewport())
        self._hint.setFont(font("callout"))
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setWordWrap(True)
        self._hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        view.viewport().installEventFilter(self)
        on_theme_change(self, self._apply_theme)
        self.update_hint()

    def sizeHint(self) -> QSize:
        return QSize(240, max(self.minimumHeight(), 160))

    def update_hint(self) -> None:
        self._hint.setVisible(bool(self._hint.text()) and self.view.count() == 0)
        self._hint.setGeometry(self.view.viewport().rect().adjusted(12, 0, -12, 0))

    def set_empty_text(self, text: str) -> None:
        self._hint.setText(text)
        self.update_hint()

    def eventFilter(self, obj, event):
        if obj is self.view.viewport() and event.type() == QEvent.Type.Resize:
            self._hint.setGeometry(obj.rect().adjusted(12, 0, -12, 0))
        return super().eventFilter(obj, event)

    def _apply_theme(self) -> None:
        self._hint.setStyleSheet(f"color: {rgba(palette().tertiary_label)};")
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = icons.squircle_path(r, 8)
        p.fillPath(path, pal.group)
        p.setPen(QPen(pal.group_border, 1))
        p.drawPath(path)
