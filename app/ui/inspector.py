"""Inspector pane: details of the selected resource or classwork entry (Finder "Get Info" feel)."""
from __future__ import annotations

from PySide6.QtCore import QLocale, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLayout, QScrollArea, QStackedWidget, QVBoxLayout,
                               QWidget)

from .. import icons
from ..constants import KIND_NAMES, MODE_FACILITATOR, MODE_INTERN
from ..core.library import Library
from ..core.models import ClassworkEntry, Resource
from ..core.settings import Settings
from ..theme import font, palette, rgba, system_color, with_alpha
from . import actions
from .classwork_view import draw_date_tile
from .controls import IconButton, make_button, on_theme_change
from .sheet import GroupBox, section_header

INSPECTOR_WIDTH = 300
_VALUE_WIDTH = 158


class FlowLayout(QLayout):
    """Left-to-right layout that wraps its items onto new lines."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):  # noqa: N802
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width):  # noqa: N802
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _arrange(self, rect: QRect, apply: bool) -> int:
        x, y, line_h = rect.x(), rect.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x > rect.x() and x + hint.width() > rect.right() + 1:
                x = rect.x()
                y += line_h + self._spacing
                line_h = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


class Tag(QWidget):
    """Keyword capsule."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self._font = font("subheadline")
        fm = QFontMetrics(self._font)
        self.setFixedSize(min(fm.horizontalAdvance(text) + 20, INSPECTOR_WIDTH - 40), 20)
        self.setToolTip(text)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.fill)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setFont(self._font)
        p.setPen(pal.label)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter,
                   p.fontMetrics().elidedText(self._text, Qt.TextElideMode.ElideRight, int(r.width() - 16)))


class _Picture(QWidget):
    """Large file icon (or calendar tile) at the top of the inspector."""

    def __init__(self, ext: str | None = None, day=None, size: int = 64, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ext, self._day = ext, day
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        if self._ext is not None:
            icons.draw_file_icon(p, r, self._ext, palette().dark)
        else:
            draw_date_tile(p, r.adjusted(5, 3, -5, -3), self._day)


class _Dot(QWidget):
    def __init__(self, color: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(8, 8)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(QRectF(self.rect()))


class _Badge(QWidget):
    """Capsule with a glyph and a short text (AI suggestion, missing-file warning)."""

    def __init__(self, icon: str, text: str, color: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon, self._text = icon, text
        self._color = QColor(color)
        self._font = font("subheadline", weight=font("headline").weight())
        fm = QFontMetrics(self._font)
        self.setFixedSize(fm.horizontalAdvance(text) + 12 + 14 + 6 + 12, 24)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(with_alpha(self._color, 34 if not pal.dark else 52))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        icons.draw_icon(p, self._icon, QRectF(12, (r.height() - 14) / 2, 14, 14), self._color)
        p.setFont(self._font)
        text_color = self._color.darker(135) if not pal.dark else self._color.lighter(125)
        p.setPen(text_color)
        p.drawText(r.adjusted(12 + 14 + 6, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._text)


def _label(text: str, style: str = "body", color: str = "label", wrap: bool = False,
           align: Qt.AlignmentFlag | None = None, selectable: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(font(style))
    lbl.setWordWrap(wrap)
    if align is not None:
        lbl.setAlignment(align)
    if selectable:
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setCursor(Qt.CursorShape.IBeamCursor)
    lbl.setStyleSheet(f"color: {rgba(getattr(palette(), color))};")
    return lbl


def _value(text: str, elide: bool = False) -> QLabel:
    lbl = _label(text, "body", "secondary_label", wrap=not elide,
                 align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    lbl.setMaximumWidth(_VALUE_WIDTH)
    natural = QFontMetrics(lbl.font()).horizontalAdvance(text) + 2
    lbl.setMinimumWidth(min(natural, _VALUE_WIDTH))
    if elide:
        fm = QFontMetrics(lbl.font())
        shown = fm.elidedText(text, Qt.TextElideMode.ElideMiddle, _VALUE_WIDTH)
        lbl.setText(shown)
        if shown != text:
            lbl.setToolTip(text)
    return lbl


def _module_value(name: str, color: str) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lay.addStretch(1)
    lay.addWidget(_Dot(system_color(color)), 0, Qt.AlignmentFlag.AlignVCenter)
    lbl = _value(name)
    lay.addWidget(lbl)
    return w


class Inspector(QWidget):
    """Right-hand detail pane shown next to the resource list."""

    edit_requested = Signal(str)
    edit_classwork_requested = Signal(str)
    explain_requested = Signal(str)

    def __init__(self, library: Library, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.library = library
        self.settings = settings
        self._mode = settings.mode() or MODE_INTERN
        self._resource: Resource | None = None
        self._entry: ClassworkEntry | None = None
        self.setFixedWidth(INSPECTOR_WIDTH)

        root = QVBoxLayout(self)
        root.setContentsMargins(1, 0, 0, 0)
        root.setSpacing(0)
        self._stack = QStackedWidget()
        self._none = QLabel("No Selection")
        self._none.setFont(font("title2", weight=font("body").weight()))
        self._none.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        actions.smooth_scroll(self._scroll)
        self._stack.addWidget(self._none)
        self._stack.addWidget(self._scroll)
        root.addWidget(self._stack)
        on_theme_change(self, self._on_theme)

    # ------------------------------------------------------------------ public API
    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._rebuild()

    def set_resource(self, r: Resource | None) -> None:
        keep = r is not None and self._resource is not None and r.id == self._resource.id
        self._resource, self._entry = r, None
        self._rebuild(keep_scroll=keep)

    def set_classwork(self, entry: ClassworkEntry | None) -> None:
        keep = entry is not None and self._entry is not None and entry.id == self._entry.id
        self._entry, self._resource = entry, None
        self._rebuild(keep_scroll=keep)

    def clear(self) -> None:
        self._resource = self._entry = None
        self._rebuild()

    def current_id(self) -> str | None:
        obj = self._resource or self._entry
        return obj.id if obj else None

    def refresh(self) -> None:
        """Reload the shown item from the library (it may have been edited or deleted)."""
        if self._resource is not None:
            self.set_resource(self.library.resource(self._resource.id))
        elif self._entry is not None:
            self.set_classwork(self.library.classwork_entry(self._entry.id))

    # ------------------------------------------------------------------ building
    def _on_theme(self) -> None:
        self._none.setStyleSheet(f"color: {rgba(palette().tertiary_label)};")
        self._rebuild(keep_scroll=True)
        self.update()

    def _rebuild(self, keep_scroll: bool = False) -> None:
        bar = self._scroll.verticalScrollBar()
        pos = bar.value() if keep_scroll else 0
        if self._resource is not None:
            content = self._build_resource(self._resource)
        elif self._entry is not None:
            content = self._build_classwork(self._entry)
        else:
            self._stack.setCurrentWidget(self._none)
            return
        content.setObjectName("inspectorContent")
        content.setStyleSheet("#inspectorContent { background: transparent; }")
        self._scroll.setWidget(content)
        self._scroll.viewport().setAutoFillBackground(False)
        self._stack.setCurrentWidget(self._scroll)
        if pos:
            content.adjustSize()
            bar.setValue(pos)

    def _base(self) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 22, 16, 20)
        lay.setSpacing(0)
        return w, lay

    def _header(self, lay: QVBoxLayout, picture: QWidget, title: str, meta: str) -> None:
        lay.addWidget(picture, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(10)
        t = _label(title, "title3", wrap=True, align=Qt.AlignmentFlag.AlignHCenter, selectable=True)
        lay.addWidget(t)
        lay.addSpacing(3)
        lay.addWidget(_label(meta, "subheadline", "secondary_label", wrap=True, align=Qt.AlignmentFlag.AlignHCenter))

    def _file_buttons(self, lay: QVBoxLayout, available: bool, on_open, on_download, on_reveal) -> None:
        lay.addSpacing(14)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        open_btn = make_button("Open", "primary")
        open_btn.setMinimumWidth(70)
        open_btn.clicked.connect(on_open)
        dl_btn = make_button("Download\u2026")
        dl_btn.clicked.connect(on_download)
        reveal = IconButton("folder", "Show in Folder")
        reveal.clicked.connect(on_reveal)
        for b in (open_btn, dl_btn):
            b.setEnabled(available)
            row.addWidget(b)
        reveal.setEnabled(available)
        row.addWidget(reveal)
        row.addStretch(1)
        lay.addLayout(row)
        if not available:
            lay.addSpacing(12)
            lay.addWidget(_Badge("warning", "File missing from the library", system_color("orange")), 0,
                          Qt.AlignmentFlag.AlignHCenter)

    def _footer(self, lay: QVBoxLayout, on_edit, on_delete) -> None:
        if self._mode != MODE_FACILITATOR:
            return
        lay.addSpacing(22)
        row = QHBoxLayout()
        row.setSpacing(8)
        edit = make_button("Edit\u2026")
        edit.clicked.connect(on_edit)
        delete = make_button("Delete\u2026", "plain")
        red = system_color("red")
        delete.setStyleSheet(f"QPushButton {{ color: {rgba(red)}; }} "
                             f"QPushButton:hover {{ color: {rgba(red.lighter(115))}; }} "
                             f"QPushButton:pressed {{ color: {rgba(red.darker(120))}; }}")
        delete.clicked.connect(on_delete)
        row.addWidget(edit)
        row.addStretch(1)
        row.addWidget(delete)
        lay.addLayout(row)

    @staticmethod
    def _section(lay: QVBoxLayout, title: str) -> None:
        lay.addSpacing(16)
        lay.addWidget(section_header(title))
        lay.addSpacing(6)

    @staticmethod
    def _info(group: GroupBox, label: str, control: QWidget) -> None:
        row = group.add_row(label, control)
        row.setMinimumHeight(34)
        row.layout().setContentsMargins(12, 7, 12, 7)

    def _build_resource(self, r: Resource) -> QWidget:
        w, lay = self._base()
        path = actions.resource_file(self.library, r)
        self._header(lay, _Picture(r.ext), r.title, f"{actions.file_type_name(r.ext)} \u00b7 {actions.human_size(r.size)}")
        self._file_buttons(lay, path is not None,
                           lambda: actions.open_resource(self.library, r, self),
                           lambda: actions.download_resource(self.library, r, self),
                           lambda: actions.show_in_folder(self.library, r, self))
        lay.addSpacing(10)
        explain = make_button("Ask Assistant to Explain")
        explain.setIcon(icons.make_icon("sparkles", system_color("purple"), 14))
        explain.clicked.connect(lambda: self.explain_requested.emit(r.id))
        lay.addWidget(explain)

        m = self.library.module(r.module_id)
        lay.addSpacing(20)
        info = GroupBox()
        self._info(info, "Module", _module_value(m.name if m else "Unsorted", m.color if m else "gray"))
        topic = m.topic(r.topic_id) if m else None
        self._info(info, "Topic", _value(topic.name if topic else "None"))
        self._info(info, "Type", _value(KIND_NAMES.get(r.kind, "Other")))
        self._info(info, "Added", _value(actions.long_date(r.created_at)))
        if r.uploader:
            self._info(info, "Added by", _value(r.uploader))
        if r.updated_at - r.created_at > 60:
            self._info(info, "Modified", _value(actions.long_date(r.updated_at)))
        self._info(info, "File name", _value(r.filename, elide=True))
        lay.addWidget(info)

        if r.keywords:
            self._section(lay, "Keywords")
            box = QWidget()
            flow = FlowLayout(box, spacing=6)
            for kw in r.keywords:
                flow.addWidget(Tag(kw))
            lay.addWidget(box)
        if r.ai_suggested:
            lay.addSpacing(12)
            lay.addWidget(_Badge("sparkles", "Tags suggested by Gemini", system_color("purple")), 0,
                          Qt.AlignmentFlag.AlignLeft)

        self._section(lay, "Description")
        if r.description:
            lay.addWidget(_label(r.description, "body", "label", wrap=True, selectable=True))
        else:
            lay.addWidget(_label("No description.", "body", "tertiary_label"))

        self._section(lay, "Classwork in this module")
        entries = self.library.classwork(module_id=r.module_id)[:3]
        if entries:
            group = GroupBox()
            for e in entries:
                group.add_row(None, self._mini_entry(e)).setMinimumHeight(32)
            lay.addWidget(group)
        else:
            lay.addWidget(_label("No classwork logged yet.", "callout", "tertiary_label"))

        lay.addStretch(1)
        self._footer(lay, lambda: self.edit_requested.emit(r.id),
                     lambda: actions.delete_resource(self.library, r, self))
        return w

    def _mini_entry(self, e: ClassworkEntry) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        d = actions.parse_iso(e.date)
        date_lbl = _label(actions.medium_date(d, with_year=False) if d else e.date, "callout", "secondary_label")
        date_lbl.setFixedWidth(46)
        row.addWidget(date_lbl)
        title = _label("", "body")
        fm = QFontMetrics(title.font())
        title.setText(fm.elidedText(e.title, Qt.TextElideMode.ElideRight, INSPECTOR_WIDTH - 32 - 24 - 56))
        title.setToolTip(e.title)
        row.addWidget(title, 1)
        return w

    def _build_classwork(self, e: ClassworkEntry) -> QWidget:
        w, lay = self._base()
        d = actions.parse_iso(e.date)
        when = f"{actions.medium_date(d)}" if d else e.date
        self._header(lay, _Picture(day=d), e.title, f"Classwork \u00b7 {when}")
        if e.attachment:
            path = actions.attachment_file(self.library, e)
            self._file_buttons(lay, path is not None,
                               lambda: actions.open_attachment(self.library, e, self),
                               lambda: actions.download_attachment(self.library, e, self),
                               lambda: actions.show_attachment_in_folder(self.library, e, self))
        m = self.library.module(e.module_id)
        lay.addSpacing(20)
        info = GroupBox()
        self._info(info, "Module", _module_value(m.name if m else "Unsorted", m.color if m else "gray"))
        topic = m.topic(e.topic_id) if m else None
        self._info(info, "Topic", _value(topic.name if topic else "None"))
        if d:
            weekday = QLocale().dayName(d.isoweekday(), QLocale.FormatType.LongFormat)
            self._info(info, "Date", _value(f"{weekday}, {actions.medium_date(d)}"))
        if e.facilitator:
            self._info(info, "Facilitator", _value(e.facilitator))
        if e.attachment:
            self._info(info, "Attachment", _value(e.attachment_name or "Attachment", elide=True))
        lay.addWidget(info)
        self._section(lay, "Description")
        if e.description:
            lay.addWidget(_label(e.description, "body", "label", wrap=True, selectable=True))
        else:
            lay.addWidget(_label("No description.", "body", "tertiary_label"))
        lay.addStretch(1)
        self._footer(lay, lambda: self.edit_classwork_requested.emit(e.id),
                     lambda: actions.delete_classwork(self.library, e, self))
        return w

    # ------------------------------------------------------------------ painting
    def paintEvent(self, _):
        p = QPainter(self)
        pal = palette()
        p.fillRect(self.rect(), pal.window)
        p.fillRect(self.rect(), with_alpha(pal.fill, int(pal.fill.alpha() * 0.5)))
        p.fillRect(0, 0, 1, self.height(), pal.separator)
