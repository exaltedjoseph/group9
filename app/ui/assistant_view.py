"""Assistant: a Gemini-powered tutor chat that explains the materials in the local library."""
from __future__ import annotations

import html
import math
import re
import textwrap

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QAbstractTextDocumentLayout, QColor, QDesktopServices, QFont, QFontMetrics,
                           QGuiApplication, QLinearGradient, QPainter, QPalette, QPen, QPixmap, QTextBlockFormat,
                           QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QTextOption)
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
                               QStackedWidget, QTextBrowser, QTextEdit, QVBoxLayout, QWidget)

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
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+#.\-]*)")

_SUGGESTIONS = [
    ("text_bubble", "blue", "Explain a topic simply", "Clear explanations with examples",
     "Explain a topic from my syllabus simply, with an everyday example. If it isn\u2019t clear which topic "
     "I mean, suggest three topics to choose from."),
    ("checklist", "orange", "Quiz me", "Test yourself with quick questions",
     "Quiz me on my library. Ask me 5 short questions one at a time, wait for my answer, then give feedback."),
    ("calendar", "green", "Make a study plan for this week", "A day-by-day plan from your syllabus",
     "Make a study plan for this week based on my syllabus, resources and recent classwork. "
     "Keep it to a short day-by-day list and point to the resources to use."),
    ("doc", "purple", "Summarize a resource", "Key points from your latest material", ""),
]


# ====================================================================== helpers
def _over(top: QColor, bottom: QColor) -> QColor:
    """`top` composited over an opaque `bottom`."""
    opaque = QColor(top)
    opaque.setAlpha(255)
    return mix(bottom, opaque, top.alphaF())


def _code_colors() -> tuple[QColor, QColor]:
    """(code block background, inline code background) as opaque colors over the window."""
    pal = palette()
    block = _over(pal.code_bg, pal.window) if pal.dark else _over(with_alpha(pal.fill, 9), pal.window)
    inline = _over(pal.fill, pal.window)
    return block, inline


def _open_link(url: QUrl) -> None:
    if url.scheme() in ("http", "https", "mailto"):
        QDesktopServices.openUrl(url)


def split_segments(text: str) -> list[tuple[str, str, str]]:
    """Split Markdown into ("md", text, "") and ("code", code, language) segments (unclosed fences allowed)."""
    out: list[tuple[str, str, str]] = []
    buf: list[str] = []
    fence: str | None = None
    lang = ""
    code: list[str] = []

    def flush_md() -> None:
        md = "\n".join(buf).strip("\n")
        if md.strip():
            out.append(("md", md, ""))
        buf.clear()

    for line in (text or "").split("\n"):
        if fence is None:
            m = _FENCE.match(line)
            if m:
                flush_md()
                fence, lang, code = m.group(1), m.group(2), []
            else:
                buf.append(line)
        else:
            stripped = line.strip()
            if stripped.startswith(fence) and set(stripped) <= {fence[0]}:
                out.append(("code", textwrap.dedent("\n".join(code)).strip("\n"), lang))
                fence = None
            else:
                code.append(line)
    if fence is not None:
        if code and code[-1].strip() and set(code[-1].strip()) <= {fence[0]}:
            code.pop()
        out.append(("code", textwrap.dedent("\n".join(code)).strip("\n"), lang))
    else:
        flush_md()
    return out


def style_markdown(doc: QTextDocument) -> None:
    """Apple-like typography for a document filled with `setMarkdown`."""
    _, inline_bg = _code_colors()
    proportional = QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
    cursor = QTextCursor(doc)
    code_ranges: list[tuple[int, int]] = []
    block = doc.begin()
    while block.isValid():
        bf = block.blockFormat()
        level = bf.headingLevel()
        fmt = QTextBlockFormat()
        fmt.setLineHeight(118 if level else 132, proportional)
        nxt = block.next()
        in_list = block.textList() is not None
        next_in_list = nxt.isValid() and nxt.textList() is not None
        if level:
            fmt.setTopMargin(12 if block != doc.begin() else 0)
            fmt.setBottomMargin(4)
        else:
            fmt.setTopMargin(0)
            fmt.setBottomMargin(4 if in_list and next_in_list else 10)
        if not nxt.isValid():
            fmt.setBottomMargin(0)
        cursor.setPosition(block.position())
        cursor.setPosition(block.position() + max(0, block.length() - 1), QTextCursor.MoveMode.KeepAnchor)
        cursor.mergeBlockFormat(fmt)
        if level:
            cf = QTextCharFormat()
            cf.setProperty(QTextFormat.Property.FontSizeAdjustment, 0)
            cf.setProperty(QTextFormat.Property.FontPixelSize, {1: 19, 2: 17, 3: 15}.get(level, 14))
            cf.setFontWeight(QFont.Weight.Bold if level == 1 else QFont.Weight.DemiBold)
            cursor.mergeCharFormat(cf)
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().fontFixedPitch():
                code_ranges.append((frag.position(), frag.length()))
            it += 1
        block = nxt
    for pos, length in code_ranges:
        cursor.setPosition(pos)
        cursor.setPosition(pos + length, QTextCursor.MoveMode.KeepAnchor)
        cf = QTextCharFormat()
        cf.setFontFamilies([mono_family()])
        cf.setFontFixedPitch(True)
        cf.setProperty(QTextFormat.Property.FontPixelSize, 13)
        cf.setBackground(inline_bg)
        cursor.mergeCharFormat(cf)


def _gradient_glyph(p: QPainter, name: str, rect: QRectF) -> None:
    """Draw a glyph filled with the assistant's purple-to-blue gradient."""
    dpr = max(1.0, p.device().devicePixelRatioF())
    pm = QPixmap(int(rect.width() * dpr), int(rect.height() * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    q = QPainter(pm)
    icons.draw_icon(q, name, QRectF(0, 0, rect.width(), rect.height()), QColor("#000000"))
    q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    q.fillRect(QRectF(0, 0, rect.width(), rect.height()), _gradient(QRectF(0, 0, rect.width(), rect.height())))
    q.end()
    p.drawPixmap(rect.topLeft(), pm)


def _gradient(rect: QRectF) -> QLinearGradient:
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0.0, system_color("pink"))
    g.setColorAt(0.45, system_color("purple"))
    g.setColorAt(1.0, system_color("blue"))
    return g


class _Label(QLabel):
    """QLabel whose text color follows a palette role across theme changes."""

    def __init__(self, text: str = "", style: str = "body", role: str = "label", wrap: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._role = role
        self.setFont(font(style))
        self.setWordWrap(wrap)
        on_theme_change(self, self._restyle)

    def set_role(self, role: str) -> None:
        self._role = role
        self._restyle()

    def _restyle(self) -> None:
        self.setStyleSheet(f"color: {rgba(getattr(palette(), self._role))};")


# ====================================================================== text widgets
class _AutoText(QTextBrowser):
    """Read-only, selectable rich text that grows to fit its content (no inner scrolling)."""

    kind = "md"

    def __init__(self, mono: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source: str | None = None
        self._mono = mono
        self.setObjectName("assistantText")
        self.setStyleSheet("#assistantText, #assistantText:focus { background: transparent; border: none; "
                           "padding: 0; margin: 0; }")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setOpenLinks(False)
        self.anchorClicked.connect(_open_link)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.viewport().setAutoFillBackground(False)
        self.document().setDocumentMargin(0)
        self.document().setIndentWidth(22)
        self.setFont(mono_font(12) if mono else font("message"))
        if mono:
            opt = QTextOption()
            opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            self.document().setDefaultTextOption(opt)
        self.setFixedHeight(20)

    def set_content(self, text: str, force: bool = False) -> None:
        if text == self._source and not force:
            return
        self._source = text
        if self._mono:
            self.setPlainText(text)
        else:
            self.setMarkdown(text)
            style_markdown(self.document())
        self.fit()

    def restyle(self) -> None:
        if self._source is not None:
            self.set_content(self._source, force=True)

    def fit(self) -> None:
        width = self.viewport().width()
        if width <= 0:
            return
        self.document().setTextWidth(width)
        height = max(1, math.ceil(self.document().size().height()))
        if height != self.height():
            self.setFixedHeight(height)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(60, self.height())

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(400, self.height())

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if e.oldSize().width() != e.size().width():
            self.fit()

    def wheelEvent(self, e):  # noqa: N802
        e.ignore()


class _CodeBlock(QWidget):
    """Fenced code: rounded card with a language label and a copy button."""

    kind = "code"
    HEADER = 30

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._code = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        header = QWidget()
        header.setFixedHeight(self.HEADER)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 0, 5, 0)
        self._lang = _Label("", "subheadline", "secondary_label")
        self._copy = IconButton("copy", "Copy Code", 24, 14)
        self._copy.clicked.connect(self._on_copy)
        hl.addWidget(self._lang)
        hl.addStretch(1)
        hl.addWidget(self._copy)
        lay.addWidget(header)
        self._text = _AutoText(mono=True)
        body = QVBoxLayout()
        body.setContentsMargins(14, 10, 14, 12)
        body.addWidget(self._text)
        lay.addLayout(body)
        self._reset = QTimer(self, singleShot=True, interval=1400)
        self._reset.timeout.connect(lambda: self._copy.setIconName("copy"))

    def set_content(self, code: str, lang: str = "") -> None:
        self._lang.setText(lang.lower())
        self._code = code
        self._text.set_content(code)

    def restyle(self) -> None:
        self._text.restyle()
        self.update()

    def _on_copy(self) -> None:
        QGuiApplication.clipboard().setText(self._code)
        self._copy.setIconName("check")
        self._reset.start()

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        bg, _inline = _code_colors()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = icons.squircle_path(r, 10)
        p.setPen(QPen(pal.code_border, 1))
        p.setBrush(bg)
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.fillRect(QRectF(1, self.HEADER - 0.5, self.width() - 2, 1), pal.code_border)


class _Avatar(QWidget):
    def __init__(self, size: int = 26, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_gradient(r))
        p.drawEllipse(r)
        s = r.width() * 0.56
        icons.draw_icon(p, "sparkle", QRectF((r.width() - s) / 2, (r.height() - s) / 2, s, s), QColor("#FFFFFF"))


class _TypingDots(QWidget):
    """Three pulsing dots in a small bubble while waiting for the first words."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(58, 32)
        self._t = 0.0
        self._timer = QTimer(self, interval=33)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self._t += 0.033
        self.update()

    def showEvent(self, e):  # noqa: N802
        self._timer.start()
        super().showEvent(e)

    def hideEvent(self, e):  # noqa: N802
        self._timer.stop()
        super().hideEvent(e)

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.bubble_assistant)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        base = pal.secondary_label
        for i in range(3):
            phase = (math.sin((self._t * 2 * math.pi / 1.2) - i * 0.9) + 1) / 2
            c = with_alpha(base, int(base.alpha() * (0.35 + 0.65 * phase)))
            d = 7.0 + 1.2 * phase
            cx = r.center().x() + (i - 1) * 12
            p.setBrush(c)
            p.drawEllipse(QPointF(cx, r.center().y()), d / 2, d / 2)


class _Bubble(QWidget):
    """The user's message: a blue iMessage-style bubble sized to its text."""

    PAD_X, PAD_Y, RADIUS = 14, 8, 18

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._doc = QTextDocument(self)
        self._doc.setDocumentMargin(0)
        self._doc.setDefaultFont(font("message"))
        opt = QTextOption()
        opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self._doc.setDefaultTextOption(opt)
        self._doc.setPlainText(text)
        self._text = text
        self._max = 520
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self._relayout()

    def text(self) -> str:
        return self._text

    def set_max_width(self, width: int) -> None:
        width = max(120, width)
        if width != self._max:
            self._max = width
            self._relayout()

    def _relayout(self) -> None:
        self._doc.setTextWidth(-1)
        inner = min(math.ceil(self._doc.idealWidth()) + 1, self._max - 2 * self.PAD_X)
        self._doc.setTextWidth(inner)
        h = math.ceil(self._doc.size().height())
        self.setFixedSize(inner + 2 * self.PAD_X, max(h + 2 * self.PAD_Y, 2 * self.RADIUS - 2))

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.bubble_user)
        p.drawPath(icons.squircle_path(r, min(self.RADIUS, r.height() / 2)))
        text_h = self._doc.size().height()
        p.translate(self.PAD_X, (r.height() - text_h) / 2)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette.setColor(QPalette.ColorRole.Text, pal.bubble_user_text)
        self._doc.documentLayout().draw(p, ctx)


class _Capsule(QAbstractButton):
    """Small rounded chip: optional file icon or glyph, an elided title, optional hover."""

    def __init__(self, text: str, ext: str | None = None, glyph: str | None = None, max_text: int = 240,
                 clickable: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text, self._ext, self._glyph = text, ext, glyph
        self._clickable = clickable
        self._font = font("callout")
        fm = QFontMetrics(self._font)
        self._shown = fm.elidedText(text, Qt.TextElideMode.ElideRight, max_text)
        lead = 8 + 14 + 6 if (ext is not None or glyph) else 10
        self.setFixedSize(lead + fm.horizontalAdvance(self._shown) + 11, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        if self._shown != text or clickable:
            self.setToolTip(f"Open \u201c{text}\u201d" if clickable else text)

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect())
        hover = self._clickable and self.underMouse()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.fill_pressed if self.isDown() else pal.fill_hover if hover else pal.fill)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        x = 10.0
        if self._ext is not None:
            icons.draw_file_icon(p, QRectF(8, 5, 14, 14), self._ext, pal.dark)
            x = 28.0
        elif self._glyph:
            icons.draw_icon(p, self._glyph, QRectF(8, 5, 14, 14), pal.secondary_label)
            x = 28.0
        p.setFont(self._font)
        p.setPen(pal.label)
        p.drawText(QRectF(x, 0, r.width() - x - 8, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._shown)


# ====================================================================== messages
class _UserMessage(QWidget):
    def __init__(self, text: str, attachment: str = "", ext: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        if attachment:
            chip = _Capsule(attachment, ext=ext, glyph=None if ext is not None else "paperclip", clickable=False)
            lay.addWidget(chip, 0, Qt.AlignmentFlag.AlignRight)
        self.bubble = _Bubble(text)
        lay.addWidget(self.bubble, 0, Qt.AlignmentFlag.AlignRight)

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self.bubble.set_max_width(int(self.width() * 0.78))

    def restyle(self) -> None:
        self.update()


class _AssistantMessage(QWidget):
    """A tutor reply: avatar, streamed Markdown, copy button, sources and inline errors."""

    retry_requested = Signal()
    source_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = ""
        self._blocks: list[QWidget] = []
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.addWidget(_Avatar(), 0, Qt.AlignmentFlag.AlignTop)
        body = QVBoxLayout()
        body.setContentsMargins(0, 1, 0, 0)
        body.setSpacing(8)
        self._dots = _TypingDots()
        body.addWidget(self._dots, 0, Qt.AlignmentFlag.AlignLeft)
        self._content = QVBoxLayout()
        self._content.setSpacing(12)
        body.addLayout(self._content)

        self._error = QWidget()
        el = QHBoxLayout(self._error)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(6)
        self._error_icon = QLabel()
        self._error_icon.setFixedSize(14, 16)
        self._error_icon.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
        self._error_text = _Label("", "callout", "red", wrap=True)
        self._error_text.setTextFormat(Qt.TextFormat.RichText)
        self._error_text.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self._error_text.linkActivated.connect(lambda _: self.retry_requested.emit())
        self._error_message = ""
        self._can_retry = True
        el.addWidget(self._error_icon, 0, Qt.AlignmentFlag.AlignTop)
        el.addWidget(self._error_text, 1)
        self._error.hide()
        body.addWidget(self._error)

        self._sources = QWidget()
        sl = QVBoxLayout(self._sources)
        sl.setContentsMargins(0, 2, 0, 0)
        sl.setSpacing(6)
        sl.addWidget(_Label("Sources", "subheadline", "secondary_label"))
        self._chips = QWidget()
        self._flow = FlowLayout(self._chips, spacing=6)
        sl.addWidget(self._chips)
        self._sources.hide()
        body.addWidget(self._sources)

        self._footer = QWidget()
        fl = QHBoxLayout(self._footer)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)
        self._copy = IconButton("copy", "Copy", 24, 14)
        self._copy.clicked.connect(self._on_copy)
        self._note = _Label("", "subheadline", "tertiary_label")
        fl.addWidget(self._copy)
        fl.addWidget(self._note)
        fl.addStretch(1)
        self._footer.hide()
        body.addWidget(self._footer)
        row.addLayout(body, 1)

        self._render_timer = QTimer(self, singleShot=True, interval=40)
        self._render_timer.timeout.connect(self._render)
        self._copied = QTimer(self, singleShot=True, interval=1400)
        self._copied.timeout.connect(lambda: self._copy.setIconName("copy"))
        on_theme_change(self, self._paint_error_icon)

    # -- streaming
    def text(self) -> str:
        return self._text

    def append(self, piece: str) -> None:
        self._text += piece
        if self._text.strip():
            self._dots.hide()
        if not self._render_timer.isActive():
            self._render_timer.start()

    def set_text(self, text: str) -> None:
        self._text = text
        self._dots.setVisible(not text.strip())
        self._render()

    def finish(self, text: str | None = None, stopped: bool = False) -> None:
        if text is not None:
            self._text = text
        self._render_timer.stop()
        self._render()
        self._dots.hide()
        self._note.setText("Stopped" if stopped else "")
        self._footer.setVisible(bool(self._text.strip()) or stopped)
        self._copy.setVisible(bool(self._text.strip()))

    def fail(self, message: str) -> None:
        self._render_timer.stop()
        self._render()
        self._dots.hide()
        self._error_message = message
        self._show_error()
        self._error.show()
        self._footer.setVisible(bool(self._text.strip()))

    def set_retry_enabled(self, enabled: bool) -> None:
        self._can_retry = enabled
        self._show_error()

    def _show_error(self) -> None:
        text = html.escape(self._error_message)
        if self._can_retry:
            text += (f"&nbsp;&nbsp;<a href=\"retry\" style=\"color: {palette().accent.name()}; "
                     f"text-decoration: none; font-weight: 600;\">Try Again</a>")
        self._error_text.setText(text)

    def failed(self) -> bool:
        return not self._error.isHidden()

    def set_sources(self, resources: list) -> None:
        while self._flow.count():
            item = self._flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for r in resources:
            chip = _Capsule(r.title, ext=r.ext)
            chip.clicked.connect(lambda _=False, rid=r.id: self.source_clicked.emit(rid))
            self._flow.addWidget(chip)
        self._sources.setVisible(bool(resources))
        self._chips.updateGeometry()

    def _render(self) -> None:
        segments = split_segments(self._text)
        for i, (kind, text, lang) in enumerate(segments):
            if i < len(self._blocks) and self._blocks[i].kind != kind:
                for w in self._blocks[i:]:
                    w.deleteLater()
                del self._blocks[i:]
            if i >= len(self._blocks):
                w = _AutoText() if kind == "md" else _CodeBlock()
                self._content.addWidget(w)
                self._blocks.append(w)
            block = self._blocks[i]
            if kind == "md":
                block.set_content(text)
            else:
                block.set_content(text, lang)
        for w in self._blocks[len(segments):]:
            w.deleteLater()
        del self._blocks[len(segments):]

    def restyle(self) -> None:
        for b in self._blocks:
            b.restyle()
        if self._error_message:
            self._show_error()

    def _paint_error_icon(self) -> None:
        self._error_icon.setPixmap(icons.icon_pixmap("exclamation_circle", palette().red, 14,
                                                     max(1.0, self.devicePixelRatioF())))

    def _on_copy(self) -> None:
        QGuiApplication.clipboard().setText(self._text)
        self._copy.setIconName("check")
        self._copied.start()


# ====================================================================== empty state, banner, composer
class _SuggestionCard(QAbstractButton):
    def __init__(self, glyph: str, color: str, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._glyph, self._color, self._title, self._subtitle = glyph, color, title, subtitle
        self.setFixedSize(272, 62)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = icons.squircle_path(r, 10)
        p.setPen(QPen(pal.group_border, 1))
        p.setBrush(pal.group if not pal.dark else _over(pal.group, pal.window))
        p.drawPath(path)
        if self.isEnabled() and (self.underMouse() or self.isDown()):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(pal.fill if self.isDown() else pal.hover)
            p.drawPath(path)
        enabled = self.isEnabled()
        tint = system_color(self._color)
        badge = QRectF(14, (r.height() - 30) / 2, 30, 30)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(tint, (36 if not pal.dark else 56) if enabled else 18))
        p.drawPath(icons.squircle_path(badge, 8))
        icons.draw_icon(p, self._glyph, badge.adjusted(7, 7, -7, -7), tint if enabled else pal.tertiary_label)
        x = badge.right() + 12
        p.setFont(font("headline"))
        p.setPen(pal.label if enabled else pal.tertiary_label)
        fm = p.fontMetrics()
        w = int(r.width() - x - 12)
        p.drawText(QRectF(x, 12, w, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(self._title, Qt.TextElideMode.ElideRight, w))
        p.setFont(font("callout"))
        p.setPen(pal.secondary_label if enabled else pal.tertiary_label)
        p.drawText(QRectF(x, 31, w, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(self._subtitle, Qt.TextElideMode.ElideRight, w))


class _Hero(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(56, 56)

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        _gradient_glyph(p, "sparkles", QRectF(self.rect()))


class _EmptyState(QWidget):
    suggestion_clicked = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(0)
        lay.addStretch(3)
        lay.addWidget(_Hero(), 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(14)
        title = _Label("Ask about anything in your library", "title2", "secondary_label")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(4)
        sub = _Label("Get explanations, quizzes and study plans based on your training materials.",
                     "callout", "tertiary_label", wrap=True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)
        lay.addSpacing(26)
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.cards: list[_SuggestionCard] = []
        for i, (glyph, color, text, subtitle, _prompt) in enumerate(_SUGGESTIONS):
            card = _SuggestionCard(glyph, color, text, subtitle)
            card.clicked.connect(lambda _=False, n=i: self.suggestion_clicked.emit(n))
            grid.addWidget(card, i // 2, i % 2)
            self.cards.append(card)
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addLayout(grid)
        wrap.addStretch(1)
        lay.addLayout(wrap)
        lay.addStretch(4)

    def set_enabled(self, enabled: bool) -> None:
        for c in self.cards:
            c.setEnabled(enabled)
            c.update()


class _KeyBanner(QWidget):
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 10, 8)
        lay.setSpacing(10)
        self._icon = QLabel()
        self._icon.setFixedSize(16, 16)
        text = _Label("Add a Gemini API key in Settings to use the Assistant.", "body", "label", wrap=True)
        btn = make_button("Open Settings\u2026")
        btn.clicked.connect(self.settings_requested)
        lay.addWidget(self._icon)
        lay.addWidget(text, 1)
        lay.addWidget(btn)
        on_theme_change(self, self._restyle)

    def _restyle(self) -> None:
        self._icon.setPixmap(icons.icon_pixmap("key", system_color("orange"), 16, max(1.0, self.devicePixelRatioF())))
        self.update()

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        orange = system_color("orange")
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(with_alpha(orange, 90 if not pal.dark else 110), 1))
        p.setBrush(with_alpha(orange, 26 if not pal.dark else 38))
        p.drawPath(icons.squircle_path(r, 10))


class _SendButton(QAbstractButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stop = False
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("Send")

    def set_stop(self, stop: bool) -> None:
        self._stop = stop
        self.setToolTip("Stop" if stop else "Send")
        self.update()

    def is_stop(self) -> bool:
        return self._stop

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        active = self.isEnabled() or self._stop
        if active:
            color = pal.accent_pressed if self.isDown() else pal.accent
        else:
            color = pal.fill_pressed
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(r)
        glyph = QColor("#FFFFFF") if active else (pal.window if not pal.dark else pal.tertiary_label)
        if self._stop:
            s = 10.0
            p.setBrush(glyph)
            p.drawRoundedRect(QRectF(r.center().x() - s / 2, r.center().y() - s / 2, s, s), 2.2, 2.2)
        else:
            icons.draw_icon(p, "arrow_up", r.adjusted(6, 6, -6, -6), glyph, 1.35)


class _Input(QTextEdit):
    """Multi-line message field: Return sends, Shift+Return adds a line; grows to six lines."""

    submit = Signal()
    MAX_LINES = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("assistantInput")
        self.setStyleSheet("#assistantInput, #assistantInput:focus { background: transparent; border: none; "
                           "padding: 0; margin: 0; }")
        self.setAcceptRichText(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFont(font("message"))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self.document().setDocumentMargin(0)
        self.viewport().setAutoFillBackground(False)
        self.setPlaceholderText("Ask about your library\u2026")
        self.document().contentsChanged.connect(self._fit)
        self._fit()

    def keyPressEvent(self, e):  # noqa: N802
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            e.accept()
            self.submit.emit()
            return
        super().keyPressEvent(e)

    def _fit(self) -> None:
        line = QFontMetrics(self.font()).lineSpacing()
        self.document().setTextWidth(max(1, self.viewport().width()))
        content = math.ceil(self.document().size().height())
        height = max(line, min(content, line * self.MAX_LINES))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if content > line * self.MAX_LINES
                                        else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if height != self.height():
            self.setFixedHeight(height)

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if e.oldSize().width() != e.size().width():
            self._fit()

    def focusInEvent(self, e):  # noqa: N802
        super().focusInEvent(e)
        if self.parentWidget():
            self.parentWidget().update()

    def focusOutEvent(self, e):  # noqa: N802
        super().focusOutEvent(e)
        if self.parentWidget():
            self.parentWidget().update()


class _Composer(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 7, 7, 7)
        lay.setSpacing(8)
        self.input = _Input()
        self.send = _SendButton()
        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 5, 0, 5)
        text_box.addWidget(self.input)
        lay.addLayout(text_box, 1)
        lay.addWidget(self.send, 0, Qt.AlignmentFlag.AlignBottom)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.send.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):  # noqa: N802
        self.input.setFocus()
        super().mousePressEvent(e)

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect()).adjusted(1, 1, -1, -2)
        radius = min(22.0, r.height() / 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 10 if not pal.dark else 40))
        p.drawPath(icons.squircle_path(r.translated(0, 1), radius))
        focused = self.input.hasFocus()
        border = pal.focus_ring if focused else (pal.field_border if pal.dark else pal.control_border)
        p.setPen(QPen(border, 1.5 if focused else 1))
        p.setBrush(_over(pal.field, pal.window) if pal.dark else pal.field)
        p.drawPath(icons.squircle_path(r, radius))


class _AttachmentBar(QWidget):
    """Chip above the composer showing the resource attached as context."""

    removed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(4, 0, 0, 0)
        self._lay.setSpacing(6)
        self._lead = _Label("Attached:", "callout", "secondary_label")
        self._lay.addWidget(self._lead)
        self._chip: QWidget | None = None
        self._remove = IconButton("xmark_circle_fill", "Remove", 20, 14)
        self._remove.clicked.connect(self.removed)
        self._lay.addWidget(self._remove)
        self._lay.addStretch(1)
        on_theme_change(self, lambda: self._remove.setColor(palette().tertiary_label))

    def set_resource(self, title: str, ext: str) -> None:
        if self._chip is not None:
            self._chip.deleteLater()
        self._chip = _Capsule(title, ext=ext, max_text=320, clickable=False)
        self._lay.insertWidget(1, self._chip)


# ====================================================================== the view
class AssistantView(QWidget):
    """Chat with a Gemini tutor that explains the materials in the library."""

    settings_requested = Signal()
    open_resource_requested = Signal(str)

    def __init__(self, library: Library, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library
        self.settings = settings
        self._mode = settings.mode() or MODE_INTERN
        self._history: list[tuple[str, str]] = []
        self._items: list[QWidget] = []
        self._worker = None
        self._run = 0
        self._reply: _AssistantMessage | None = None
        self._request: dict | None = None
        self._attachment: dict | None = None
        self._stick = True

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.toolbar = Toolbar("Assistant", "Powered by Gemini \u00b7 answers come from your library")
        self._new = IconButton("compose", "New Chat")
        self._new.clicked.connect(self.new_chat)
        self.toolbar.add_action(self._new)
        root.addWidget(self.toolbar)

        self._banner = _KeyBanner()
        self._banner.settings_requested.connect(self.settings_requested)
        root.addLayout(self._centered(self._banner, (24, 14, 24, 0)))

        self._stack = QStackedWidget()
        self._empty = _EmptyState()
        self._empty.suggestion_clicked.connect(self._on_suggestion)
        self._stack.addWidget(self._empty)

        self._thread = QWidget()
        self._thread.setObjectName("assistantThread")
        self._thread.setStyleSheet("#assistantThread { background: transparent; }")
        tl = QVBoxLayout(self._thread)
        tl.setContentsMargins(24, 22, 24, 22)
        tl.setSpacing(0)
        self._column = QWidget()
        self._messages = QVBoxLayout(self._column)
        self._messages.setContentsMargins(0, 0, 0, 0)
        self._messages.setSpacing(26)
        tl.addLayout(self._centered(self._column))
        tl.addStretch(1)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._thread)
        self._scroll.viewport().setAutoFillBackground(False)
        actions.smooth_scroll(self._scroll)
        bar = self._scroll.verticalScrollBar()
        bar.rangeChanged.connect(self._on_range)
        bar.valueChanged.connect(self._on_scrolled)
        self._stack.addWidget(self._scroll)
        root.addWidget(self._stack, 1)

        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        self._attach_bar = _AttachmentBar()
        self._attach_bar.removed.connect(self.clear_attachment)
        self._attach_bar.hide()
        bl.addWidget(self._attach_bar)
        self._composer = _Composer()
        self._composer.input.submit.connect(self._submit)
        self._composer.input.textChanged.connect(self._update_send)
        self._composer.send.clicked.connect(self._on_send_clicked)
        bl.addWidget(self._composer)
        note = _Label("The Assistant uses Gemini and can make mistakes. Check important details in your materials.",
                      "footnote", "tertiary_label")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(note)
        root.addLayout(self._centered(bottom, (24, 6, 24, 10)))

        settings.changed.connect(self._on_setting)
        library.changed.connect(lambda *_: self._validate_attachment())
        on_theme_change(self, self._apply_theme, call_now=False)
        self._check_key()

    # ------------------------------------------------------------------ public API
    def set_mode(self, mode: str) -> None:
        self._mode = mode or MODE_INTERN

    def ask(self, prompt: str) -> None:
        """Send `prompt` as a new message (no-op when empty)."""
        prompt = (prompt or "").strip()
        if prompt:
            self._send(prompt)

    def explain_resource(self, resource_id: str) -> None:
        """Start an "Explain …" turn with the resource attached as context."""
        r = self._attach(resource_id)
        if r is None:
            return
        self._send(f"Explain \u201c{r.title}\u201d",
                   f"Explain the attached resource \u201c{r.title}\u201d: what it covers, the key ideas in simple "
                   "terms, and a short example.")

    def new_chat(self) -> None:
        self._stop(record=False)
        for w in self._items:
            w.deleteLater()
        self._items.clear()
        self._history.clear()
        self._reply = self._request = None
        self.clear_attachment()
        self._stack.setCurrentWidget(self._empty)
        self._composer.input.setFocus()

    def refresh(self) -> None:
        self._check_key()
        self._validate_attachment()

    def clear_attachment(self) -> None:
        self._attachment = None
        self._attach_bar.hide()

    def is_busy(self) -> bool:
        return self._worker is not None

    # ------------------------------------------------------------------ layout helpers
    @staticmethod
    def _centered(widget: QWidget, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(*margins)
        row.addStretch(1)
        widget.setMaximumWidth(COLUMN_WIDTH)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, widget.sizePolicy().verticalPolicy())
        row.addWidget(widget, 100)
        row.addStretch(1)
        return row

    def _add(self, widget: QWidget) -> None:
        self._stack.setCurrentWidget(self._scroll)
        self._messages.addWidget(widget)
        self._items.append(widget)

    def _on_range(self, _min: int, maximum: int) -> None:
        if self._stick:
            self._scroll.verticalScrollBar().setValue(maximum)

    def _on_scrolled(self, value: int) -> None:
        self._stick = value >= self._scroll.verticalScrollBar().maximum() - 32

    # ------------------------------------------------------------------ key, settings, theme
    def _has_key(self) -> bool:
        try:
            return bool(self.settings.api_key())
        except Exception:
            return False

    def _check_key(self) -> None:
        has = self._has_key()
        self._banner.setVisible(not has)
        self._empty.set_enabled(has)
        self._composer.input.setEnabled(has)
        self._composer.input.setPlaceholderText("Ask about your library\u2026" if has
                                                else "Add an API key in Settings to start chatting")
        self._update_send()

    def _on_setting(self, key: str) -> None:
        if key in (KEY_API_KEY, KEY_MODEL):
            self._check_key()

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self._check_key()

    def _apply_theme(self) -> None:
        for w in self._items:
            w.restyle()
        self.update()

    def paintEvent(self, _):  # noqa: N802
        QPainter(self).fillRect(self.rect(), palette().window)

    # ------------------------------------------------------------------ attachment
    def _attach(self, resource_id: str):
        try:
            r = self.library.resource(resource_id)
        except Exception:
            r = None
        if r is None:
            return None
        label, text = core.resource_context(self.library, resource_id)
        self._attachment = {"id": r.id, "label": label, "text": text, "ext": r.ext}
        self._attach_bar.set_resource(r.title, r.ext)
        self._attach_bar.show()
        return r

    def _validate_attachment(self) -> None:
        if self._attachment and self.library.resource(self._attachment["id"]) is None:
            self.clear_attachment()

    # ------------------------------------------------------------------ sending
    def _update_send(self) -> None:
        send = self._composer.send
        busy = self._worker is not None
        send.set_stop(busy)
        send.setEnabled(busy or (self._has_key() and bool(self._composer.input.toPlainText().strip())))

    def _submit(self) -> None:
        if self._worker is not None:
            return
        text = self._composer.input.toPlainText().strip()
        if text and self._has_key():
            self._composer.input.clear()
            self._send(text)

    def _on_send_clicked(self) -> None:
        if self._worker is not None:
            self._stop()
        else:
            self._submit()

    def _on_suggestion(self, index: int) -> None:
        _glyph, _color, title, _sub, prompt = _SUGGESTIONS[index]
        if prompt:
            self._send(title, prompt)
            return
        recent = self.library.recent(1)
        if not recent:
            self._composer.input.setPlainText("Summarize ")
            self._composer.input.moveCursor(QTextCursor.MoveOperation.End)
            self._composer.input.setFocus()
            return
        r = self._attach(recent[0].id)
        if r is not None:
            self._send(f"Summarize \u201c{r.title}\u201d",
                       f"Summarize the attached resource \u201c{r.title}\u201d in a few key points, then give me "
                       "three questions to check my understanding.")

    def _send(self, display: str, message: str | None = None) -> None:
        display = display.strip()
        if not display:
            return
        if not self._has_key():
            self._check_key()
            self._composer.input.setPlainText(display)
            return
        if self._worker is not None:
            self._stop()
        message = message or display
        att = self._attachment or {}
        exclude = [att["id"]] if att else []
        try:
            found, ids = core.retrieval_context(self.library, display, exclude=exclude)
        except Exception:
            found, ids = "", []
        context = "\n\n".join(t for t in (att.get("text", ""), found) if t)
        self._stick = True
        self._add(_UserMessage(display, att.get("label", ""), att.get("ext")))
        self._start({"message": message, "context": context, "sources": exclude + ids})

    def _start(self, request: dict) -> None:
        if self._reply is not None and self._reply.failed():
            self._reply.set_retry_enabled(False)
        reply = _AssistantMessage()
        reply.retry_requested.connect(lambda r=reply: self._retry(r))
        reply.source_clicked.connect(self.open_resource_requested)
        self._add(reply)
        self._reply, self._request = reply, request
        try:
            system = core.build_system_prompt(self.library, self._mode)
            worker = core.ChatWorker(self.settings.api_key(), self.settings.model(), system, list(self._history),
                                     request["message"], request["context"])
        except Exception as exc:
            reply.fail(f"Couldn\u2019t start the Assistant ({exc}).")
            return
        self._run += 1
        worker.run_id = self._run
        worker.chunk.connect(self._on_chunk)
        worker.finished_ok.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        keep_thread(worker)
        self._worker = worker
        self._update_send()
        worker.start()

    def _retry(self, reply: _AssistantMessage) -> None:
        if self._worker is not None or reply is not self._reply or self._request is None:
            return
        self._items.remove(reply)
        reply.deleteLater()
        self._reply = None
        self._stick = True
        self._start(self._request)

    def _stop(self, record: bool = True) -> None:
        worker, reply = self._worker, self._reply
        if worker is None:
            return
        worker.cancel()
        self._worker = None
        self._run += 1
        if reply is not None:
            reply.finish(stopped=True)
            if record and reply.text().strip() and self._request:
                self._history += [("user", self._request["message"]), ("model", reply.text())]
        self._update_send()

    def _current(self) -> bool:
        return getattr(self.sender(), "run_id", -1) == self._run and self._reply is not None

    def _on_chunk(self, piece: str) -> None:
        if self._current():
            self._reply.append(piece)

    def _on_done(self, text: str) -> None:
        if not self._current():
            return
        reply, request = self._reply, self._request or {}
        self._worker = None
        reply.finish(text)
        sources = [r for r in (self.library.resource(i) for i in request.get("sources", [])) if r is not None]
        reply.set_sources(sources)
        self._history += [("user", request.get("message", "")), ("model", text)]
        self._update_send()

    def _on_failed(self, message: str) -> None:
        if not self._current():
            return
        self._worker = None
        self._reply.fail(message)
        self._update_send()
