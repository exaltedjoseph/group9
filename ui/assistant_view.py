"""Assistant: a Gemini-powered tutor chat that explains the materials in the local library."""
# TODO(branch4): implement the Gemini AI integration and Assistant.
from __future__ import annotations
import html
import math
import re
import textwrap
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAbstractTextDocumentLayout, QColor, QDesktopServices, QFont, QFontMetrics, QGuiApplication, QLinearGradient, QPainter, QPalette, QPen, QPixmap, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QTextOption
from PySide6.QtWidgets import QAbstractButton, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QStackedWidget, QTextBrowser, QTextEdit, QVBoxLayout, QWidget
from .. import icons
from ..constants import MODE_INTERN
from ..core import assistant as core
from ..core.library import Library
from ..core.settings import KEY_API_KEY, KEY_MODEL, Settings
from ..theme import font, mono_family, mono_font, palette, rgba, system_color, with_alpha
from . import actions
from .controls import IconButton, make_button, mix, on_theme_change
from .forms import keep_thread
from .inspector import FlowLayout
from .toolbar import Toolbar
COLUMN_WIDTH = 760
_FENCE = re.compile('^\\s*(`{3,}|~{3,})\\s*([\\w+#.\\-]*)')
_SUGGESTIONS = [('text_bubble', 'blue', 'Explain a topic simply', 'Clear explanations with examples', 'Explain a topic from my syllabus simply, with an everyday example. If it isn’t clear which topic I mean, suggest three topics to choose from.'), ('checklist', 'orange', 'Quiz me', 'Test yourself with quick questions', 'Quiz me on my library. Ask me 5 short questions one at a time, wait for my answer, then give feedback.'), ('calendar', 'green', 'Make a study plan for this week', 'A day-by-day plan from your syllabus', 'Make a study plan for this week based on my syllabus, resources and recent classwork. Keep it to a short day-by-day list and point to the resources to use.'), ('doc', 'purple', 'Summarize a resource', 'Key points from your latest material', '')]

def _over(top: QColor, bottom: QColor) -> QColor:
    """`top` composited over an opaque `bottom`."""
    ...

def _code_colors() -> tuple[QColor, QColor]:
    """(code block background, inline code background) as opaque colors over the window."""
    ...

def _open_link(url: QUrl) -> None:
    ...

def split_segments(text: str) -> list[tuple[str, str, str]]:
    """Split Markdown into ("md", text, "") and ("code", code, language) segments (unclosed fences allowed)."""
    ...

def style_markdown(doc: QTextDocument) -> None:
    """Apple-like typography for a document filled with `setMarkdown`."""
    ...

def _gradient_glyph(p: QPainter, name: str, rect: QRectF) -> None:
    """Draw a glyph filled with the assistant's purple-to-blue gradient."""
    ...

def _gradient(rect: QRectF) -> QLinearGradient:
    ...

class _Label(QLabel):
    """QLabel whose text color follows a palette role across theme changes."""

    def __init__(self, text: str='', style: str='body', role: str='label', wrap: bool=False, parent: QWidget | None=None) -> None:
        ...

    def set_role(self, role: str) -> None:
        ...

    def _restyle(self) -> None:
        ...

class _AutoText(QTextBrowser):
    """Read-only, selectable rich text that grows to fit its content (no inner scrolling)."""
    kind = 'md'

    def __init__(self, mono: bool=False, parent: QWidget | None=None) -> None:
        ...

    def set_content(self, text: str, force: bool=False) -> None:
        ...

    def restyle(self) -> None:
        ...

    def fit(self) -> None:
        ...

    def minimumSizeHint(self) -> QSize:
        ...

    def sizeHint(self) -> QSize:
        ...

    def resizeEvent(self, e):
        ...

    def wheelEvent(self, e):
        ...

class _CodeBlock(QWidget):
    """Fenced code: rounded card with a language label and a copy button."""
    kind = 'code'
    HEADER = 30

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def set_content(self, code: str, lang: str='') -> None:
        ...

    def restyle(self) -> None:
        ...

    def _on_copy(self) -> None:
        ...

    def paintEvent(self, _):
        ...

class _Avatar(QWidget):

    def __init__(self, size: int=26, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class _TypingDots(QWidget):
    """Three pulsing dots in a small bubble while waiting for the first words."""

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def _tick(self) -> None:
        ...

    def showEvent(self, e):
        ...

    def hideEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

class _Bubble(QWidget):
    """The user's message: a blue iMessage-style bubble sized to its text."""
    PAD_X, PAD_Y, RADIUS = (14, 8, 18)

    def __init__(self, text: str, parent: QWidget | None=None) -> None:
        ...

    def text(self) -> str:
        ...

    def set_max_width(self, width: int) -> None:
        ...

    def _relayout(self) -> None:
        ...

    def paintEvent(self, _):
        ...

class _Capsule(QAbstractButton):
    """Small rounded chip: optional file icon or glyph, an elided title, optional hover."""

    def __init__(self, text: str, ext: str | None=None, glyph: str | None=None, max_text: int=240, clickable: bool=True, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class _UserMessage(QWidget):

    def __init__(self, text: str, attachment: str='', ext: str | None=None, parent: QWidget | None=None) -> None:
        ...

    def resizeEvent(self, e):
        ...

    def restyle(self) -> None:
        ...

class _AssistantMessage(QWidget):
    """A tutor reply: avatar, streamed Markdown, copy button, sources and inline errors."""
    retry_requested = Signal()
    source_clicked = Signal(str)

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def text(self) -> str:
        ...

    def append(self, piece: str) -> None:
        ...

    def set_text(self, text: str) -> None:
        ...

    def finish(self, text: str | None=None, stopped: bool=False) -> None:
        ...

    def fail(self, message: str) -> None:
        ...

    def set_retry_enabled(self, enabled: bool) -> None:
        ...

    def _show_error(self) -> None:
        ...

    def failed(self) -> bool:
        ...

    def set_sources(self, resources: list) -> None:
        ...

    def _render(self) -> None:
        ...

    def restyle(self) -> None:
        ...

    def _paint_error_icon(self) -> None:
        ...

    def _on_copy(self) -> None:
        ...

class _SuggestionCard(QAbstractButton):

    def __init__(self, glyph: str, color: str, title: str, subtitle: str, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class _Hero(QWidget):

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def paintEvent(self, _):
        ...

class _EmptyState(QWidget):
    suggestion_clicked = Signal(int)

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def set_enabled(self, enabled: bool) -> None:
        ...

class _KeyBanner(QWidget):
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def _restyle(self) -> None:
        ...

    def paintEvent(self, _):
        ...

class _SendButton(QAbstractButton):

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def set_stop(self, stop: bool) -> None:
        ...

    def is_stop(self) -> bool:
        ...

    def paintEvent(self, _):
        ...

class _Input(QTextEdit):
    """Multi-line message field: Return sends, Shift+Return adds a line; grows to six lines."""
    submit = Signal()
    MAX_LINES = 6

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def keyPressEvent(self, e):
        ...

    def _fit(self) -> None:
        ...

    def resizeEvent(self, e):
        ...

    def focusInEvent(self, e):
        ...

    def focusOutEvent(self, e):
        ...

class _Composer(QWidget):

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def mousePressEvent(self, e):
        ...

    def paintEvent(self, _):
        ...

class _AttachmentBar(QWidget):
    """Chip above the composer showing the resource attached as context."""
    removed = Signal()

    def __init__(self, parent: QWidget | None=None) -> None:
        ...

    def set_resource(self, title: str, ext: str) -> None:
        ...

class AssistantView(QWidget):
    """Chat with a Gemini tutor that explains the materials in the library."""
    settings_requested = Signal()
    open_resource_requested = Signal(str)

    def __init__(self, library: Library, settings: Settings, parent: QWidget | None=None) -> None:
        ...

    def set_mode(self, mode: str) -> None:
        ...

    def ask(self, prompt: str) -> None:
        """Send `prompt` as a new message (no-op when empty)."""
        ...

    def explain_resource(self, resource_id: str) -> None:
        """Start an "Explain …" turn with the resource attached as context."""
        ...

    def new_chat(self) -> None:
        ...

    def refresh(self) -> None:
        ...

    def clear_attachment(self) -> None:
        ...

    def is_busy(self) -> bool:
        ...

    @staticmethod
    def _centered(widget: QWidget, margins: tuple[int, int, int, int]=(0, 0, 0, 0)) -> QHBoxLayout:
        ...

    def _add(self, widget: QWidget) -> None:
        ...

    def _on_range(self, _min: int, maximum: int) -> None:
        ...

    def _on_scrolled(self, value: int) -> None:
        ...

    def _has_key(self) -> bool:
        ...

    def _check_key(self) -> None:
        ...

    def _on_setting(self, key: str) -> None:
        ...

    def showEvent(self, e):
        ...

    def _apply_theme(self) -> None:
        ...

    def paintEvent(self, _):
        ...

    def _attach(self, resource_id: str):
        ...

    def _validate_attachment(self) -> None:
        ...

    def _update_send(self) -> None:
        ...

    def _submit(self) -> None:
        ...

    def _on_send_clicked(self) -> None:
        ...

    def _on_suggestion(self, index: int) -> None:
        ...

    def _send(self, display: str, message: str | None=None) -> None:
        ...

    def _start(self, request: dict) -> None:
        ...

    def _retry(self, reply: _AssistantMessage) -> None:
        ...

    def _stop(self, record: bool=True) -> None:
        ...

    def _current(self) -> bool:
        ...

    def _on_chunk(self, piece: str) -> None:
        ...

    def _on_done(self, text: str) -> None:
        ...

    def _on_failed(self, message: str) -> None:
        ...
