"""Shared resource/classwork actions (open, download, reveal, delete) and small UI helpers
used by the library list, the inspector and the classwork timeline."""
# TODO(branch5): implement the app shell, Home dashboard and actions.
from __future__ import annotations
import os
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Callable
import shiboken6
from PySide6.QtCore import QAbstractAnimation, QDate, QEasingCurve, QEvent, QLocale, QObject, QPoint, QRectF, QTime, Qt, QTimer, QUrl, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFontMetrics, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractScrollArea, QFileDialog, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget
from .. import icons
from ..core.library import Library, LibraryError, safe_filename
from ..core.models import ClassworkEntry, Resource
from ..theme import font, palette, rgba, with_alpha
from .alert import AlertDialog, confirm
from .controls import make_button, on_theme_change
_size_impl: Callable[[int], str] | None = None

def _fallback_human_size(n: int) -> str:
    ...

def human_size(n: int) -> str:
    """macOS-style file size ("1.2 MB"); uses `core.extract.human_size` when available."""
    ...
_TYPE_NAMES = {'pdf': 'PDF Document', 'doc': 'Word Document', 'docx': 'Word Document', 'rtf': 'Rich Text Document', 'odt': 'OpenDocument Text', 'pages': 'Pages Document', 'ppt': 'PowerPoint Presentation', 'pptx': 'PowerPoint Presentation', 'key': 'Keynote Presentation', 'odp': 'OpenDocument Presentation', 'xls': 'Excel Spreadsheet', 'xlsx': 'Excel Spreadsheet', 'ods': 'OpenDocument Spreadsheet', 'numbers': 'Numbers Spreadsheet', 'csv': 'CSV Document', 'txt': 'Plain Text Document', 'md': 'Markdown Document', 'json': 'JSON Document', 'html': 'HTML Document', 'htm': 'HTML Document', 'css': 'CSS Style Sheet', 'py': 'Python Script', 'ipynb': 'Jupyter Notebook', 'js': 'JavaScript File', 'ts': 'TypeScript File', 'java': 'Java Source File', 'c': 'C Source File', 'cpp': 'C++ Source File', 'sql': 'SQL File', 'png': 'PNG Image', 'jpg': 'JPEG Image', 'jpeg': 'JPEG Image', 'gif': 'GIF Image', 'webp': 'WebP Image', 'svg': 'SVG Image', 'heic': 'HEIC Image', 'bmp': 'BMP Image', 'mp4': 'MPEG-4 Movie', 'mov': 'QuickTime Movie', 'mkv': 'Matroska Video', 'webm': 'WebM Video', 'mp3': 'MP3 Audio', 'wav': 'WAVE Audio', 'm4a': 'MPEG-4 Audio', 'zip': 'ZIP Archive', 'rar': 'RAR Archive', '7z': '7-Zip Archive', 'gz': 'Gzip Archive', 'tar': 'Tar Archive'}

def file_type_name(ext: str) -> str:
    ...

def _qdate(d: date) -> QDate:
    ...

def short_time(dt: datetime) -> str:
    ...

def medium_date(d: date, with_year: bool=True) -> str:
    """"6 Oct 2026" or "Oct 6, 2026" depending on the locale's date order."""
    ...

def relative_date(ts: float) -> str:
    """Finder/Mail style: "Today 14:05", "Yesterday", weekday within a week, else a short date."""
    ...

def long_date(ts: float) -> str:
    """"6 Oct 2026 at 14:05"."""
    ...

def parse_iso(iso: str) -> date | None:
    ...

def plural(n: int, one: str, many: str | None=None) -> str:
    ...

def make_menu(parent: QWidget | None) -> QMenu:
    """Rounded QMenu (frameless, translucent) styled by the global QSS."""
    ...

def menu_icon(name: str | None, color: QColor | None=None, size: int=14) -> QIcon:
    """Menu glyph that turns white on the highlighted (accent) row; `None` gives a blank spacer."""
    ...

def dot_icon(color: QColor, size: int=14) -> QIcon:
    """Small colored dot used for module entries in menus."""
    ...

def popup_below(menu: QMenu, button: QWidget) -> None:
    """Show `menu` under `button`, right-aligned with it (toolbar buttons sit at the right edge)."""
    ...

def menu_header(menu: QMenu, text: str) -> None:
    """Grey, non-interactive section title inside a menu."""
    ...

class _SmoothScroller(QObject):

    def __init__(self, area: QAbstractScrollArea) -> None:
        ...

    def eventFilter(self, obj, event):
        ...

def smooth_scroll(area: QAbstractScrollArea) -> None:
    """Animate mouse-wheel scrolling (trackpad pixel scrolling stays direct)."""
    ...

class Toast(QWidget):
    """HUD-style rounded notification that fades in, lingers and fades out over the window."""
    _MARGIN = 14

    def __init__(self, host: QWidget, text: str, icon: str='checkmark_circle_fill', duration: int=1600) -> None:
        ...

    def _set_opacity(self, v) -> None:
        ...

    def _place(self) -> None:
        ...

    def popup(self) -> None:
        ...

    def _fade_out(self) -> None:
        ...

    def eventFilter(self, obj, event):
        ...

    def paintEvent(self, _):
        ...

def show_toast(parent: QWidget | None, text: str, icon: str='checkmark_circle_fill') -> None:
    """Brief "Saved to Downloads" style confirmation over the parent's window."""
    ...

def show_error(parent: QWidget | None, title: str, message: str='') -> None:
    """Single-button macOS alert."""
    ...

def _error_text(exc: Exception) -> str:
    ...

def _open_path(path: Path, parent: QWidget | None) -> bool:
    ...

def _reveal(path: Path) -> None:
    ...

def _save_copy(src: Path, filename: str, parent: QWidget | None) -> Path | None:
    ...

def _missing(parent: QWidget | None, name: str) -> None:
    ...

def resource_file(library: Library, r: Resource) -> Path | None:
    """Absolute path of the resource file, or None if it is missing."""
    ...

def open_resource(library: Library, r: Resource, parent: QWidget | None=None) -> bool:
    ...

def download_resource(library: Library, r: Resource, parent: QWidget | None=None) -> Path | None:
    """Ask where to save a copy (defaults to ~/Downloads) and confirm with a toast."""
    ...

def show_in_folder(library: Library, r: Resource, parent: QWidget | None=None) -> None:
    ...

def delete_resource(library: Library, r: Resource, parent: QWidget | None=None) -> bool:
    ...

def attachment_file(library: Library, entry: ClassworkEntry) -> Path | None:
    ...

def open_attachment(library: Library, entry: ClassworkEntry, parent: QWidget | None=None) -> bool:
    ...

def download_attachment(library: Library, entry: ClassworkEntry, parent: QWidget | None=None) -> Path | None:
    ...

def show_attachment_in_folder(library: Library, entry: ClassworkEntry, parent: QWidget | None=None) -> None:
    ...

def delete_classwork(library: Library, entry: ClassworkEntry, parent: QWidget | None=None) -> bool:
    ...

class _Glyph(QWidget):

    def __init__(self, name: str, size: int=48, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class EmptyState(QWidget):
    """Centered macOS empty state: large tertiary glyph, title and a short hint."""
    action_clicked = Signal()

    def __init__(self, icon: str='doc', title: str='', message: str='', action_text: str='', parent: QWidget | None=None) -> None:
        ...

    def set_content(self, icon: str, title: str, message: str='', action_text: str='') -> None:
        ...

    def _apply_theme(self) -> None:
        ...
