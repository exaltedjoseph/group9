"""Add / edit a resource: file drop zone, Gemini suggestions and the metadata form."""
# TODO(branch5): implement the app shell, Home dashboard and actions.
from __future__ import annotations
from pathlib import Path
from typing import Callable
from PySide6.QtCore import QEvent, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QSizePolicy, QWidget
from .. import icons
from ..constants import API_KEY_URL, KIND_NAMES
from ..core.library import LibraryError
from ..core.models import Resource, Suggestion
from ..theme import font, palette, rgba, system_color
from .controls import ActivityIndicator, make_button, on_theme_change
from .forms import DropZone, KindCombo, ModuleCombo, SparkleBadge, StatusLabel, TokenField, TopicCombo, add_label_accessory, fit_row, keep_thread, merge_keywords, prettify_stem, tint_badges
from .sheet import GroupBox, Sheet
EXCERPT_CHARS = 24000
_SUBTITLE = 'Interns will find it under the module and topic you choose.'

def _extract_excerpt(path: Path) -> str:
    ...

class _TextJob(QThread):
    """Builds the text excerpt for the AI request off the GUI thread."""
    done = Signal(str)

    def __init__(self, fn: Callable[[], str], run_id: int, source: Path) -> None:
        ...

    def run(self) -> None:
        ...

class ResourceSheet(Sheet):
    """'Add Resource' / 'Edit Resource' sheet with AI-assisted tagging."""
    saved = Signal(str)
    settings_requested = Signal()

    def __init__(self, host: QWidget, library, settings, parent: QWidget | None=None) -> None:
        ...

    def open_add(self, module_id: str | None=None, files: list[Path] | None=None) -> None:
        ...

    def open_edit(self, resource_id: str) -> None:
        ...

    def _build(self) -> None:
        ...

    def _prepare(self, edit: Resource | None, module_id: str | None) -> None:
        ...

    def on_open(self) -> None:
        ...

    def _update_queue_note(self) -> None:
        ...

    def _validate(self) -> None:
        ...

    def _relayout(self) -> None:
        ...

    def _user_edit(self, field: str) -> None:
        ...

    def _on_file_changed(self, path) -> None:
        ...

    def _on_module_changed(self, _index: int) -> None:
        ...

    def _on_keywords_changed(self) -> None:
        ...

    def eventFilter(self, obj, event):
        ...

    def _ai_source(self) -> Path | None:
        ...

    def _set_busy(self, on: bool, text: str='') -> None:
        ...

    def _save_key(self) -> None:
        ...

    def _suggest(self) -> None:
        ...

    def _on_text_ready(self, text: str) -> None:
        ...

    def _on_suggested(self, suggestion) -> None:
        ...

    def _on_failed(self, message: str) -> None:
        ...

    def _show_ai_error(self, message: str) -> None:
        ...

    def _apply_suggestion(self, s: Suggestion) -> None:
        ...

    def _submit(self) -> None:
        ...

    def _show_error(self, message: str) -> None:
        ...

    def _on_closed(self) -> None:
        ...
