"""Shared resource/classwork actions (open, download, reveal, delete) and small UI helpers
used by the library list, the inspector and the classwork timeline."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import shiboken6
from PySide6.QtCore import (QAbstractAnimation, QDate, QEasingCurve, QEvent, QLocale, QObject, QPoint, QRectF,
                            QTime, Qt, QTimer, QUrl, QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QDesktopServices, QFontMetrics, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractScrollArea, QFileDialog, QLabel, QMenu, QPushButton, QVBoxLayout,
                               QWidget)

from .. import icons
from ..core.library import Library, LibraryError, safe_filename
from ..core.models import ClassworkEntry, Resource
from ..theme import font, palette, rgba, with_alpha
from .alert import AlertDialog, confirm
from .controls import make_button, on_theme_change

# --------------------------------------------------------------------------- formatting

_size_impl: Callable[[int], str] | None = None


def _fallback_human_size(n: int) -> str:
    if n < 1000:
        return "1 byte" if n == 1 else f"{n} bytes"
    value = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1000.0
        if value < 999.5 or unit == "TB":
            if unit == "KB" or value >= 100:
                return f"{value:.0f} {unit}"
            return f"{value:.1f} {unit}".replace(".0 ", " ")
    return f"{n} bytes"


def human_size(n: int) -> str:
    """macOS-style file size ("1.2 MB"); uses `core.extract.human_size` when available."""
    global _size_impl
    if _size_impl is None:
        try:
            from ..core.extract import human_size as impl
        except Exception:
            impl = _fallback_human_size
        _size_impl = impl
    try:
        return _size_impl(int(n or 0))
    except Exception:
        return _fallback_human_size(int(n or 0))


_TYPE_NAMES = {
    "pdf": "PDF Document", "doc": "Word Document", "docx": "Word Document", "rtf": "Rich Text Document",
    "odt": "OpenDocument Text", "pages": "Pages Document", "ppt": "PowerPoint Presentation",
    "pptx": "PowerPoint Presentation", "key": "Keynote Presentation", "odp": "OpenDocument Presentation",
    "xls": "Excel Spreadsheet", "xlsx": "Excel Spreadsheet", "ods": "OpenDocument Spreadsheet",
    "numbers": "Numbers Spreadsheet", "csv": "CSV Document", "txt": "Plain Text Document",
    "md": "Markdown Document", "json": "JSON Document", "html": "HTML Document", "htm": "HTML Document",
    "css": "CSS Style Sheet", "py": "Python Script", "ipynb": "Jupyter Notebook", "js": "JavaScript File",
    "ts": "TypeScript File", "java": "Java Source File", "c": "C Source File", "cpp": "C++ Source File",
    "sql": "SQL File", "png": "PNG Image", "jpg": "JPEG Image", "jpeg": "JPEG Image", "gif": "GIF Image",
    "webp": "WebP Image", "svg": "SVG Image", "heic": "HEIC Image", "bmp": "BMP Image",
    "mp4": "MPEG-4 Movie", "mov": "QuickTime Movie", "mkv": "Matroska Video", "webm": "WebM Video",
    "mp3": "MP3 Audio", "wav": "WAVE Audio", "m4a": "MPEG-4 Audio", "zip": "ZIP Archive",
    "rar": "RAR Archive", "7z": "7-Zip Archive", "gz": "Gzip Archive", "tar": "Tar Archive",
}


def file_type_name(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    if not ext:
        return "Document"
    return _TYPE_NAMES.get(ext, f"{ext.upper()} File")


def _qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def short_time(dt: datetime) -> str:
    return QLocale().toString(QTime(dt.hour, dt.minute), QLocale.FormatType.ShortFormat)


def medium_date(d: date, with_year: bool = True) -> str:
    """"6 Oct 2026" or "Oct 6, 2026" depending on the locale's date order."""
    loc = QLocale()
    short = loc.dateFormat(QLocale.FormatType.ShortFormat).lower()
    if short.find("m") < short.find("d"):
        fmt = "MMM d, yyyy" if with_year else "MMM d"
    else:
        fmt = "d MMM yyyy" if with_year else "d MMM"
    return loc.toString(_qdate(d), fmt)


def relative_date(ts: float) -> str:
    """Finder/Mail style: "Today 14:05", "Yesterday", weekday within a week, else a short date."""
    if not ts:
        return ""
    dt = datetime.fromtimestamp(ts)
    delta = (date.today() - dt.date()).days
    loc = QLocale()
    if delta == 0:
        return f"Today {short_time(dt)}"
    if delta == 1:
        return "Yesterday"
    if 1 < delta < 7:
        return loc.dayName(dt.isoweekday(), QLocale.FormatType.LongFormat)
    return loc.toString(_qdate(dt.date()), QLocale.FormatType.ShortFormat)


def long_date(ts: float) -> str:
    """"6 Oct 2026 at 14:05"."""
    if not ts:
        return ""
    dt = datetime.fromtimestamp(ts)
    return f"{medium_date(dt.date())} at {short_time(dt)}"


def parse_iso(iso: str) -> date | None:
    try:
        return date.fromisoformat(iso)
    except (TypeError, ValueError):
        return None


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


# --------------------------------------------------------------------------- menus

def make_menu(parent: QWidget | None) -> QMenu:
    """Rounded QMenu (frameless, translucent) styled by the global QSS."""
    menu = QMenu(parent)
    menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint
                        | Qt.WindowType.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    menu.setFont(font("body"))
    return menu


def menu_icon(name: str | None, color: QColor | None = None, size: int = 14) -> QIcon:
    """Menu glyph that turns white on the highlighted (accent) row; `None` gives a blank spacer."""
    pal = palette()
    icon = QIcon()
    for dpr in (1.0, 2.0):
        if name is None:
            pm = QPixmap(int(size * dpr), int(size * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            icon.addPixmap(pm, QIcon.Mode.Normal)
            icon.addPixmap(pm, QIcon.Mode.Active)
            continue
        icon.addPixmap(icons.icon_pixmap(name, color or pal.label, size, dpr), QIcon.Mode.Normal)
        icon.addPixmap(icons.icon_pixmap(name, pal.on_accent, size, dpr), QIcon.Mode.Active)
        icon.addPixmap(icons.icon_pixmap(name, pal.tertiary_label, size, dpr), QIcon.Mode.Disabled)
    return icon


def dot_icon(color: QColor, size: int = 14) -> QIcon:
    """Small colored dot used for module entries in menus."""
    icon = QIcon()
    for dpr in (1.0, 2.0):
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        d = size * 0.58
        p.drawEllipse(QRectF((size - d) / 2, (size - d) / 2, d, d))
        p.end()
        icon.addPixmap(pm, QIcon.Mode.Normal)
        icon.addPixmap(pm, QIcon.Mode.Active)
    return icon


def popup_below(menu: QMenu, button: QWidget) -> None:
    """Show `menu` under `button`, right-aligned with it (toolbar buttons sit at the right edge)."""
    x = button.width() - menu.sizeHint().width()
    menu.exec(button.mapToGlobal(QPoint(min(0, x), button.height() + 4)))


def menu_header(menu: QMenu, text: str) -> None:
    """Grey, non-interactive section title inside a menu."""
    act = menu.addAction(text)
    act.setEnabled(False)
    act.setFont(font("subheadline", weight=font("headline").weight()))


# --------------------------------------------------------------------------- smooth scrolling

class _SmoothScroller(QObject):
    def __init__(self, area: QAbstractScrollArea) -> None:
        super().__init__(area)
        self._area = area
        self._target = 0.0
        self._anim = QVariantAnimation(self, duration=220, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: area.verticalScrollBar().setValue(round(float(v))))
        area.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and not event.modifiers():
            if event.pixelDelta().isNull() and event.angleDelta().y():
                bar = self._area.verticalScrollBar()
                if bar.maximum() <= 0:
                    return False
                running = self._anim.state() == QAbstractAnimation.State.Running
                base = self._target if running else bar.value()
                self._target = max(bar.minimum(), min(bar.maximum(), base - event.angleDelta().y() / 120 * 96))
                self._anim.stop()
                self._anim.setStartValue(float(bar.value()))
                self._anim.setEndValue(float(self._target))
                self._anim.start()
                event.accept()
                return True
        return False


def smooth_scroll(area: QAbstractScrollArea) -> None:
    """Animate mouse-wheel scrolling (trackpad pixel scrolling stays direct)."""
    _SmoothScroller(area)


# --------------------------------------------------------------------------- toast

class Toast(QWidget):
    """HUD-style rounded notification that fades in, lingers and fades out over the window."""

    _MARGIN = 14

    def __init__(self, host: QWidget, text: str, icon: str = "checkmark_circle_fill", duration: int = 1600) -> None:
        super().__init__(host)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._text = text
        self._icon = icon
        self._opacity = 0.0
        self._font = font("headline")
        fm = QFontMetrics(self._font)
        w = 16 + 18 + 8 + fm.horizontalAdvance(text) + 18
        self.resize(w + 2 * self._MARGIN, 40 + 2 * self._MARGIN)
        self._anim = QVariantAnimation(self, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_opacity)
        self._hold = QTimer(self, singleShot=True, interval=duration)
        self._hold.timeout.connect(self._fade_out)
        host.installEventFilter(self)
        self._place()

    def _set_opacity(self, v) -> None:
        self._opacity = float(v)
        self.update()

    def _place(self) -> None:
        host = self.parentWidget()
        if host is None:
            return
        self.move((host.width() - self.width()) // 2, host.height() - self.height() - 36)

    def popup(self) -> None:
        self.show()
        self.raise_()
        self._anim.setDuration(180)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._hold.start()

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setDuration(260)
        self._anim.setStartValue(self._opacity)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.deleteLater)
        self._anim.start()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Resize:
            self._place()
        return False

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._opacity)
        pal = palette()
        m = self._MARGIN
        card = QRectF(self.rect()).adjusted(m, m, -m, -m)
        for i in range(m, 0, -2):
            a = int((10 if not pal.dark else 22) * (1 - i / m))
            p.fillPath(icons.squircle_path(card.adjusted(-i, -i + 4, i, i + 4), 12 + i), QColor(0, 0, 0, a))
        bg = QColor(250, 250, 250, 238) if not pal.dark else QColor(54, 54, 56, 240)
        p.fillPath(icons.squircle_path(card, 12), bg)
        p.setPen(QPen(pal.group_border if not pal.dark else with_alpha(pal.label, 34), 1))
        p.drawPath(icons.squircle_path(card.adjusted(0.5, 0.5, -0.5, -0.5), 12))
        icons.draw_icon(p, self._icon, QRectF(card.left() + 16, card.center().y() - 9, 18, 18), pal.green)
        p.setFont(self._font)
        p.setPen(pal.label)
        p.drawText(card.adjusted(16 + 18 + 8, 0, -12, 0),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)


def show_toast(parent: QWidget | None, text: str, icon: str = "checkmark_circle_fill") -> None:
    """Brief "Saved to Downloads" style confirmation over the parent's window."""
    if parent is None or not shiboken6.isValid(parent):
        return
    host = parent.window()
    for old in host.findChildren(Toast):
        old.deleteLater()
    Toast(host, text, icon).popup()


# --------------------------------------------------------------------------- alerts

def show_error(parent: QWidget | None, title: str, message: str = "") -> None:
    """Single-button macOS alert."""
    dlg = AlertDialog(parent, title, message, "OK", "Cancel", destructive=False)
    for btn in dlg.findChildren(QPushButton):
        if btn.text() == "Cancel":
            btn.hide()
    dlg.exec()


def _error_text(exc: Exception) -> str:
    if isinstance(exc, OSError):
        return exc.strerror or str(exc)
    return str(exc)


# --------------------------------------------------------------------------- file helpers

def _open_path(path: Path, parent: QWidget | None) -> bool:
    if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
        return True
    show_error(parent, f"Can\u2019t Open \u201c{path.name}\u201d",
               "There\u2019s no app set up to open this kind of file.")
    return False


def _reveal(path: Path) -> None:
    try:
        if sys.platform == "win32":
            if path.exists():
                subprocess.Popen(f'explorer /select,"{path}"')
            else:
                os.startfile(str(path.parent if path.parent.exists() else path.parent.parent))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)] if path.exists() else ["open", str(path.parent)])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
    except OSError:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


def _save_copy(src: Path, filename: str, parent: QWidget | None) -> Path | None:
    downloads = Path.home() / "Downloads"
    start = downloads if downloads.is_dir() else Path.home()
    name = safe_filename(filename or src.name)
    ext = Path(name).suffix.lstrip(".")
    filters = (f"{file_type_name(ext)} (*.{ext});;" if ext else "") + "All Files (*)"
    chosen, _ = QFileDialog.getSaveFileName(parent, "Download", str(start / name), filters)
    if not chosen:
        return None
    dest = Path(chosen)
    try:
        if dest.resolve() != src.resolve():
            shutil.copy2(src, dest)
    except OSError as exc:
        show_error(parent, "Couldn\u2019t Save the File", _error_text(exc))
        return None
    show_toast(parent, f"Saved to {dest.parent.name or str(dest.parent)}")
    return dest


def _missing(parent: QWidget | None, name: str) -> None:
    show_error(parent, f"\u201c{name}\u201d Is Missing",
               "The file is no longer in the library folder. It may have been moved or deleted "
               "outside Study Library.")


# --------------------------------------------------------------------------- resources

def resource_file(library: Library, r: Resource) -> Path | None:
    """Absolute path of the resource file, or None if it is missing."""
    try:
        path = library.file_path(r)
    except LibraryError:
        return None
    return path if path.exists() else None


def open_resource(library: Library, r: Resource, parent: QWidget | None = None) -> bool:
    path = resource_file(library, r)
    if path is None:
        _missing(parent, r.filename)
        return False
    return _open_path(path, parent)


def download_resource(library: Library, r: Resource, parent: QWidget | None = None) -> Path | None:
    """Ask where to save a copy (defaults to ~/Downloads) and confirm with a toast."""
    path = resource_file(library, r)
    if path is None:
        _missing(parent, r.filename)
        return None
    return _save_copy(path, r.filename, parent)


def show_in_folder(library: Library, r: Resource, parent: QWidget | None = None) -> None:
    try:
        _reveal(library.file_path(r))
    except LibraryError as exc:
        show_error(parent, "Can\u2019t Show the File", str(exc))


def delete_resource(library: Library, r: Resource, parent: QWidget | None = None) -> bool:
    if not confirm(parent, f"Delete \u201c{r.title}\u201d?",
                   "The file will be removed from the library. This change is recorded in Git history.",
                   "Delete"):
        return False
    try:
        library.delete_resource(r.id)
    except (LibraryError, OSError) as exc:
        show_error(parent, "Couldn\u2019t Delete the Resource", _error_text(exc))
        return False
    return True


# --------------------------------------------------------------------------- classwork

def attachment_file(library: Library, entry: ClassworkEntry) -> Path | None:
    try:
        path = library.attachment_path(entry)
    except LibraryError:
        return None
    return path if path is not None and path.exists() else None


def open_attachment(library: Library, entry: ClassworkEntry, parent: QWidget | None = None) -> bool:
    if not entry.attachment:
        return False
    path = attachment_file(library, entry)
    if path is None:
        _missing(parent, entry.attachment_name or "Attachment")
        return False
    return _open_path(path, parent)


def download_attachment(library: Library, entry: ClassworkEntry, parent: QWidget | None = None) -> Path | None:
    if not entry.attachment:
        return None
    path = attachment_file(library, entry)
    if path is None:
        _missing(parent, entry.attachment_name or "Attachment")
        return None
    return _save_copy(path, entry.attachment_name or path.name, parent)


def show_attachment_in_folder(library: Library, entry: ClassworkEntry, parent: QWidget | None = None) -> None:
    if not entry.attachment:
        return
    try:
        path = library.attachment_path(entry)
    except LibraryError as exc:
        show_error(parent, "Can\u2019t Show the File", str(exc))
        return
    if path is not None:
        _reveal(path)


def delete_classwork(library: Library, entry: ClassworkEntry, parent: QWidget | None = None) -> bool:
    extra = " and its attachment" if entry.attachment else ""
    if not confirm(parent, f"Delete \u201c{entry.title}\u201d?",
                   f"This classwork entry{extra} will be removed. This change is recorded in Git history.",
                   "Delete"):
        return False
    try:
        library.delete_classwork(entry.id)
    except (LibraryError, OSError) as exc:
        show_error(parent, "Couldn\u2019t Delete the Entry", _error_text(exc))
        return False
    return True


# --------------------------------------------------------------------------- empty state

class _Glyph(QWidget):
    def __init__(self, name: str, size: int = 48, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.name = name
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        icons.draw_icon(p, self.name, QRectF(self.rect()), palette().tertiary_label, 0.9)


class EmptyState(QWidget):
    """Centered macOS empty state: large tertiary glyph, title and a short hint."""

    action_clicked = Signal()

    def __init__(self, icon: str = "doc", title: str = "", message: str = "", action_text: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 48)
        lay.setSpacing(0)
        lay.addStretch(1)
        self._glyph = _Glyph(icon)
        lay.addWidget(self._glyph, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(14)
        self._title = QLabel()
        self._title.setFont(font("title2"))
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._title)
        lay.addSpacing(4)
        self._message = QLabel()
        self._message.setFont(font("callout"))
        self._message.setWordWrap(True)
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setFixedWidth(320)
        lay.addWidget(self._message, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(18)
        self._button = make_button("", "primary")
        self._button.clicked.connect(self.action_clicked)
        lay.addWidget(self._button, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)
        self.set_content(icon, title, message, action_text)
        on_theme_change(self, self._apply_theme)

    def set_content(self, icon: str, title: str, message: str = "", action_text: str = "") -> None:
        self._glyph.name = icon
        self._glyph.setVisible(bool(title))
        self._glyph.update()
        self._title.setText(title)
        self._message.setText(message)
        self._message.setVisible(bool(message))
        self._button.setText(action_text)
        self._button.setVisible(bool(action_text))

    def _apply_theme(self) -> None:
        pal = palette()
        self._title.setStyleSheet(f"color: {rgba(pal.secondary_label)};")
        self._message.setStyleSheet(f"color: {rgba(pal.tertiary_label)};")
        self._glyph.update()
