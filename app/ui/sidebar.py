"""macOS source-list sidebar: search, library sections, modules and the mode switcher."""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field

from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt, QTimer,
                            QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from .. import icons
from ..constants import APP_NAME, MODE_FACILITATOR, MODE_INTERN
from ..core.library import LibraryError
from ..core.settings import KEY_USER_NAME
from ..theme import font, palette, rgba, system_color, theme, with_alpha
from .controls import IconButton, SearchField, mix, on_theme_change

HEADER_HEIGHT = 52
FOOTER_HEIGHT = 48
ROW_HEIGHT = 28
SECTION_HEIGHT = 26
SECTION_GAP = 10
INSET = 8
SEARCH_DEBOUNCE_MS = 200

_COLLAPSED_KEY = "sidebar_collapsed"
_NAV_KINDS = ("home", "assistant", "all", "recent", "classwork", "history", "module")
_MODE_INFO = {
    MODE_FACILITATOR: ("Facilitator", "person", "blue"),
    MODE_INTERN: ("Intern", "graduationcap", "green"),
}


def popup_menu(parent: QWidget) -> QMenu:
    """QMenu with rounded translucent corners (styled by the global QSS)."""
    menu = QMenu(parent)
    menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint
                        | Qt.WindowType.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    menu.setFont(font("body"))
    return menu


def _check_icon(checked: bool) -> QIcon:
    """Menu checkmark that turns white on the highlighted item (blank when unchecked)."""
    icon = QIcon()
    pal = palette()
    for dpr in (1.0, 1.5, 2.0):
        if checked:
            icon.addPixmap(icons.icon_pixmap("check", pal.label, 12, dpr, 1.3), QIcon.Mode.Normal)
            icon.addPixmap(icons.icon_pixmap("check", pal.on_accent, 12, dpr, 1.3), QIcon.Mode.Active)
        else:
            blank = QPixmap(int(12 * dpr), int(12 * dpr))
            blank.setDevicePixelRatio(dpr)
            blank.fill(Qt.GlobalColor.transparent)
            icon.addPixmap(blank)
    return icon


# --------------------------------------------------------------------------- source list

@dataclass
class _Row:
    kind: str                 # a navigate kind, or "action" / "placeholder"
    arg: object = None
    title: str = ""
    icon: str = ""
    color: str | None = None  # module system color name
    count: int = 0

    @property
    def key(self) -> tuple[str, object]:
        return self.kind, self.arg

    @property
    def selectable(self) -> bool:
        return self.kind in _NAV_KINDS


@dataclass
class _Section:
    key: str
    title: str
    rows: list[_Row] = field(default_factory=list)


class _SourceList(QWidget):
    """Custom-painted list of collapsible sections with selectable rows."""

    activated = Signal(object)               # _Row
    menu_requested = Signal(object, QPoint)  # _Row | _Section, global position
    collapse_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sections: list[_Section] = []
        self._geo: list[tuple[_Section, float, float, float]] = []  # section, header top, body top, body height
        self._selected: tuple[str, object] | None = None
        self._hover: tuple[str, object] | None = None
        self._context: tuple[str, object] | None = None
        self._collapsed: set[str] = set()
        self._factor: dict[str, float] = {}
        self._anims: dict[str, QVariantAnimation] = {}
        self._row_font = font("body")
        self._count_font = font("callout")
        self._header_font = font("subheadline", weight=QFont.Weight.DemiBold)
        self.scroll: QScrollArea | None = None
        self.edit_section = "modules"
        self.edit_button = IconButton("ellipsis_circle", "Edit Modules\u2026", 20, 15, self)
        self.edit_button.hide()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        theme().changed.connect(self.update)

    # ------------------------------------------------------------------ state
    def set_sections(self, sections: list[_Section]) -> None:
        self._sections = sections
        self._relayout()

    def set_selected(self, key: tuple[str, object] | None) -> None:
        self._selected = key
        self.update()

    def selected(self) -> tuple[str, object] | None:
        return self._selected

    def set_context(self, key: tuple[str, object] | None) -> None:
        self._context = key
        self.update()

    def has(self, key: tuple[str, object]) -> bool:
        return any(r.key == key and r.selectable for s in self._sections for r in s.rows)

    def collapsed(self) -> set[str]:
        return set(self._collapsed)

    def set_collapsed(self, keys: set[str]) -> None:
        self._collapsed = set(keys)
        for key in list(self._factor) + list(keys):
            self._factor[key] = 0.0 if key in self._collapsed else 1.0
        self._relayout()

    def set_edit_visible(self, visible: bool) -> None:
        self.edit_button.setVisible(visible)
        self._relayout()

    def toggle_section(self, key: str) -> None:
        if key in self._collapsed:
            self._collapsed.discard(key)
        else:
            self._collapsed.add(key)
        anim = self._anims.get(key)
        if anim is None:
            anim = QVariantAnimation(self, duration=220, easingCurve=QEasingCurve.Type.OutCubic)
            anim.valueChanged.connect(lambda v, k=key: self._set_factor(k, float(v)))
            self._anims[key] = anim
        anim.stop()
        anim.setStartValue(self._factor.get(key, 1.0))
        anim.setEndValue(0.0 if key in self._collapsed else 1.0)
        anim.start()
        self.collapse_changed.emit()

    def _set_factor(self, key: str, value: float) -> None:
        self._factor[key] = value
        self._relayout()

    # ------------------------------------------------------------------ geometry
    def _relayout(self) -> None:
        y = 2.0
        geo = []
        for i, s in enumerate(self._sections):
            if i:
                y += SECTION_GAP
            top = y
            y += SECTION_HEIGHT
            body = len(s.rows) * ROW_HEIGHT
            geo.append((s, top, y, body))
            y += body * self._factor.get(s.key, 1.0)
        self._geo = geo
        self.setMinimumHeight(int(math.ceil(y + 10)))
        self._place_edit_button()
        self.update()

    def _place_edit_button(self) -> None:
        for s, top, _, _ in self._geo:
            if s.key == self.edit_section:
                b = self.edit_button
                b.move(self.width() - INSET - b.width() - 2, int(top + (SECTION_HEIGHT - b.height()) / 2 + 2))
                return

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_edit_button()

    def _hit(self, pos: QPointF) -> tuple[str, _Section, _Row | None] | None:
        y = pos.y()
        for s, top, body, height in self._geo:
            if top <= y < body:
                return "header", s, None
            f = self._factor.get(s.key, 1.0)
            if f > 0.05 and body <= y < body + height * f:
                idx = int((y - body) // ROW_HEIGHT)
                if 0 <= idx < len(s.rows):
                    return "row", s, s.rows[idx]
        return None

    def _row_rect(self, key: tuple[str, object]) -> QRectF | None:
        for s, _, body, _ in self._geo:
            for i, r in enumerate(s.rows):
                if r.key == key:
                    return QRectF(0, body + i * ROW_HEIGHT, self.width(), ROW_HEIGHT)
        return None

    def _navigable(self) -> list[_Row]:
        return [r for s in self._sections if s.key not in self._collapsed for r in s.rows if r.selectable]

    def ensure_visible(self, key: tuple[str, object]) -> None:
        rect = self._row_rect(key)
        if rect is not None and self.scroll is not None:
            self.scroll.ensureVisible(0, int(rect.center().y()), 0, ROW_HEIGHT)

    # ------------------------------------------------------------------ painting
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        active = self.isActiveWindow()
        w = self.width()
        for s, top, body, height in self._geo:
            self._paint_header(p, s, QRectF(0, top, w, SECTION_HEIGHT))
            f = self._factor.get(s.key, 1.0)
            if f <= 0.0:
                continue
            p.save()
            p.setClipRect(QRectF(0, body, w, height * f))
            if f < 1.0:
                p.setOpacity(f)
            for i, row in enumerate(s.rows):
                self._paint_row(p, row, QRectF(0, body + i * ROW_HEIGHT, w, ROW_HEIGHT), active)
            p.restore()

    def _paint_header(self, p: QPainter, s: _Section, rect: QRectF) -> None:
        pal = palette()
        right = rect.right() - INSET - 4
        if self.edit_button.isVisible() and s.key == self.edit_section:
            right -= self.edit_button.width() + 2
        if self._hover == ("header", s.key):
            f = self._factor.get(s.key, 1.0)
            c = QPointF(right - 6, rect.center().y() + 1.5)
            p.save()
            p.translate(c)
            p.rotate(90.0 * f)
            icons.draw_icon(p, "chevron_right", QRectF(-5.5, -5.5, 11, 11), pal.secondary_label, 1.3)
            p.restore()
            right -= 18
        p.setFont(self._header_font)
        p.setPen(pal.tertiary_label)
        text_rect = QRectF(INSET + 10, rect.top() + 4, right - INSET - 10, rect.height() - 4)
        text = p.fontMetrics().elidedText(s.title, Qt.TextElideMode.ElideRight, int(text_rect.width()))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)

    def _paint_row(self, p: QPainter, row: _Row, rect: QRectF, active: bool) -> None:
        pal = palette()
        plate = rect.adjusted(INSET, 1, -INSET, -1)
        selected = row.selectable and row.key == self._selected
        emphasized = selected and active
        if selected:
            p.fillPath(icons.squircle_path(plate, 6), pal.selection if active else pal.selection_inactive)
        elif self._hover == ("row", row.key) and row.kind != "placeholder":
            p.fillPath(icons.squircle_path(plate, 6), pal.hover)
        if self._context == row.key:
            p.setPen(QPen(pal.accent, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(icons.squircle_path(plate.adjusted(1, 1, -1, -1), 5))

        if emphasized:
            glyph, text_color = pal.selection_text, pal.selection_text
        elif row.kind == "module":
            glyph, text_color = system_color(row.color or "blue"), pal.label
        elif row.kind == "action":
            glyph, text_color = pal.secondary_label, pal.secondary_label
        elif row.kind == "placeholder":
            glyph, text_color = pal.tertiary_label, pal.tertiary_label
        else:
            glyph, text_color = pal.accent, pal.label

        x = plate.left() + 8
        if row.icon:
            icons.draw_icon(p, row.icon, QRectF(x, plate.center().y() - 8.5, 17, 17), glyph)
            x += 17 + 7
        right = plate.right() - 9

        if row.kind == "module" and row.count > 0:
            p.setFont(self._count_font)
            count = str(row.count)
            cw = p.fontMetrics().horizontalAdvance(count)
            p.setPen(with_alpha(pal.selection_text, 210) if emphasized else pal.secondary_label)
            p.drawText(QRectF(right - cw, plate.top(), cw, plate.height()),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, count)
            right -= cw + 8

        p.setFont(self._row_font)
        p.setPen(text_color)
        text = p.fontMetrics().elidedText(row.title, Qt.TextElideMode.ElideRight, int(max(0, right - x)))
        p.drawText(QRectF(x, plate.top(), right - x, plate.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)

    # ------------------------------------------------------------------ input
    def event(self, e):
        if e.type() in (QEvent.Type.WindowActivate, QEvent.Type.WindowDeactivate, QEvent.Type.ActivationChange):
            self.update()
        return super().event(e)

    def mousePressEvent(self, e):
        hit = self._hit(e.position())
        if e.button() != Qt.MouseButton.LeftButton or hit is None:
            super().mousePressEvent(e)
            return
        kind, section, row = hit
        if kind == "header":
            self.toggle_section(section.key)
        elif row.selectable:
            self.set_selected(row.key)
            self.activated.emit(row)
        elif row.kind == "action":
            self.activated.emit(row)
        e.accept()

    def mouseMoveEvent(self, e):
        hit = self._hit(e.position())
        hover = None
        if hit is not None:
            kind, section, row = hit
            if kind == "header":
                hover = ("header", section.key)
            elif row.kind != "placeholder":
                hover = ("row", row.key)
        if hover != self._hover:
            self._hover = hover
            self.update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        if self._hover is not None:
            self._hover = None
            self.update()
        super().leaveEvent(e)

    def contextMenuEvent(self, e):
        hit = self._hit(QPointF(e.pos()))
        if hit is None:
            return
        kind, section, row = hit
        self.menu_requested.emit(section if kind == "header" else row, e.globalPos())

    def keyPressEvent(self, e):
        key = e.key()
        if key not in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Home, Qt.Key.Key_End):
            super().keyPressEvent(e)
            return
        rows = self._navigable()
        if not rows:
            return
        keys = [r.key for r in rows]
        idx = keys.index(self._selected) if self._selected in keys else -1
        if key == Qt.Key.Key_Home:
            new = 0
        elif key == Qt.Key.Key_End:
            new = len(rows) - 1
        elif key == Qt.Key.Key_Down:
            new = min(len(rows) - 1, idx + 1)
        else:
            new = max(0, idx - 1) if idx >= 0 else len(rows) - 1
        if new != idx:
            self.set_selected(rows[new].key)
            self.ensure_visible(rows[new].key)
            self.activated.emit(rows[new])

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.update()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.update()


# --------------------------------------------------------------------------- footer

class _ModeButton(QAbstractButton):
    """Account-style pop-up button: colored badge, mode name and the user's name."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = MODE_INTERN
        self._name = ""
        self._hover = 0.0
        self.menu_open = False
        self._title_font = font("body", weight=QFont.Weight.Medium)
        self._sub_font = font("subheadline")
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("Switch Mode")
        self._anim = QVariantAnimation(self, duration=140, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_hover)
        theme().changed.connect(self.update)

    def set_info(self, mode: str, user_name: str) -> None:
        self._mode, self._name = mode, user_name
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(150, 36)

    def _set_hover(self, v) -> None:
        self._hover = float(v)
        self.update()

    def _animate(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, e):
        self._animate(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate(0.0)
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        rect = QRectF(self.rect())
        if self.isDown() or self.menu_open:
            plate = pal.fill_hover
        else:
            plate = with_alpha(pal.fill, int(pal.fill.alpha() * self._hover))
        if plate.alpha() > 0:
            p.fillPath(icons.squircle_path(rect.adjusted(0.5, 0.5, -0.5, -0.5), 7), plate)

        title, glyph, color = _MODE_INFO.get(self._mode, _MODE_INFO[MODE_INTERN])
        badge = QRectF(6, (rect.height() - 24) / 2, 24, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(system_color(color))
        p.drawEllipse(badge)
        icons.draw_icon(p, glyph, badge.adjusted(5, 5, -5, -5), QColor("#FFFFFF"), 1.1)

        chevron = QRectF(rect.right() - 8 - 11, (rect.height() - 11) / 2, 11, 11)
        icons.draw_icon(p, "chevron_up_down", chevron, mix(pal.tertiary_label, pal.secondary_label, self._hover))

        x = badge.right() + 8
        avail = int(chevron.left() - 6 - x)
        p.setFont(self._title_font)
        p.setPen(pal.label)
        fm = p.fontMetrics()
        if self._name:
            p.drawText(QRectF(x, 2, avail, rect.height() / 2 - 1),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                       fm.elidedText(title, Qt.TextElideMode.ElideRight, avail))
            p.setFont(self._sub_font)
            p.setPen(pal.secondary_label)
            p.drawText(QRectF(x, rect.height() / 2 + 1, avail, rect.height() / 2 - 3),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                       p.fontMetrics().elidedText(self._name, Qt.TextElideMode.ElideRight, avail))
        else:
            p.drawText(QRectF(x, 0, avail, rect.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(title, Qt.TextElideMode.ElideRight, avail))


class _Footer(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(FOOTER_HEIGHT)
        self.mode_button = _ModeButton()
        self.settings_button = IconButton("gear", "Settings", 28, 17)
        row = QHBoxLayout(self)
        row.setContentsMargins(INSET, 1, INSET + 2, 0)
        row.setSpacing(6)
        row.addWidget(self.mode_button, 1)
        row.addWidget(self.settings_button)
        theme().changed.connect(self.update)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(0, 0, self.width(), 1, palette().separator)


# --------------------------------------------------------------------------- sidebar

class Sidebar(QWidget):
    """Finder-style source list with search, library sections, modules and a mode switcher."""

    navigate = Signal(str, object)
    search_changed = Signal(str)
    settings_requested = Signal()
    mode_switch_requested = Signal(str)
    manage_syllabus_requested = Signal()

    def __init__(self, library, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._library = library
        self._settings = settings
        mode = settings.mode()
        self._mode = mode if mode in _MODE_INFO else MODE_INTERN
        self._last_query = ""
        self._silent = False
        self.setMinimumWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = QWidget()
        self._header.setFixedHeight(HEADER_HEIGHT)
        self._header.setProperty("titleBarArea", True)
        header_row = QHBoxLayout(self._header)
        header_row.setContentsMargins(16, 0, 10, 0)
        header_row.setSpacing(8)
        self._app_icon = QLabel()
        self._app_icon.setPixmap(icons.app_icon().pixmap(20, 20))
        self._app_title = QLabel(APP_NAME)
        self._app_title.setFont(font("headline"))
        for lbl in (self._app_icon, self._app_title):
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            header_row.addWidget(lbl)
        header_row.addStretch(1)
        on_theme_change(self._app_title, lambda: self._app_title.setStyleSheet(
            f"color: {rgba(palette().label)}; background: transparent;"))
        layout.addWidget(self._header)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(10, 0, 10, 10)
        self._search = SearchField("Search")
        self._search.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._search.installEventFilter(self)
        search_row.addWidget(self._search)
        layout.addLayout(search_row)
        self._debounce = QTimer(self, singleShot=True, interval=SEARCH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._emit_search)
        self._search.textChanged.connect(self._on_search_text)

        self._list = _SourceList()
        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._scroll.viewport().setObjectName("sidebarViewport")
        self._scroll.viewport().setStyleSheet("#sidebarViewport { background: transparent; }")
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.setWidget(self._list)
        self._list.setAutoFillBackground(False)
        self._list.scroll = self._scroll
        layout.addWidget(self._scroll, 1)

        self._footer = _Footer()
        layout.addWidget(self._footer)

        self._list.activated.connect(self._on_activated)
        self._list.menu_requested.connect(self._on_menu)
        self._list.collapse_changed.connect(self._save_collapsed)
        self._list.edit_button.clicked.connect(self.manage_syllabus_requested)
        self._footer.mode_button.clicked.connect(self._show_mode_menu)
        self._footer.settings_button.clicked.connect(self.settings_requested)

        stored = (settings.get(_COLLAPSED_KEY) or "").split(",")
        self._list.set_collapsed({k for k in stored if k})
        self._list.set_selected(("home", None))
        library.changed.connect(self._on_library_changed)
        settings.changed.connect(self._on_setting_changed)
        theme().changed.connect(self.update)
        self._apply_mode()

    # ------------------------------------------------------------------ public API
    def set_mode(self, mode: str) -> None:
        self._mode = mode if mode in _MODE_INFO else MODE_INTERN
        self._apply_mode()

    def select(self, kind: str, arg: object = None) -> None:
        """Highlight a row without emitting `navigate` (unknown targets clear the selection)."""
        key = (kind, arg if kind == "module" else None)
        self._list.set_selected(key if self._list.has(key) else None)
        if self._list.has(key):
            self._list.ensure_visible(key)

    def focus_search(self) -> None:
        self._search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search.selectAll()

    def clear_search(self) -> None:
        """Empty the search field without emitting `search_changed`."""
        self._silent = True
        try:
            self._search.clear()
        finally:
            self._silent = False
        self._debounce.stop()
        self._last_query = ""

    def refresh(self) -> None:
        """Rebuild modules and counts, keeping the selection when it still exists."""
        try:
            modules = self._library.modules()
            counts = self._library.counts()
        except (LibraryError, sqlite3.Error):
            modules, counts = [], {}
        facilitator = self._mode == MODE_FACILITATOR
        library_rows = [
            _Row("home", None, "Home", "grid"),
            _Row("assistant", None, "Assistant", "sparkles"),
            _Row("all", None, "All Resources", "rectangle_stack"),
            _Row("recent", None, "Recently Added", "clock"),
            _Row("classwork", None, "Classwork", "calendar"),
        ]
        if facilitator:
            library_rows.append(_Row("history", None, "History", "history"))
        module_rows = [_Row("module", m.id, m.name, "folder_fill", m.color, counts.get(m.id, 0)) for m in modules]
        if not module_rows:
            module_rows = [_Row("action", None, "Add Modules\u2026", "plus_circle") if facilitator
                           else _Row("placeholder", None, "No Modules", "folder")]
        self._list.set_sections([_Section("library", "Library", library_rows),
                                 _Section("modules", "Modules", module_rows)])
        self._list.set_edit_visible(facilitator)
        selected = self._list.selected()
        if selected is not None and not self._list.has(selected):
            self._list.set_selected(("home", None))
            self.navigate.emit("home", None)

    # ------------------------------------------------------------------ internals
    def _apply_mode(self) -> None:
        self._footer.mode_button.set_info(self._mode, self._settings.user_name())
        self.refresh()

    def _on_library_changed(self, _part: str = "") -> None:
        self.refresh()

    def _on_setting_changed(self, key: str) -> None:
        if key == KEY_USER_NAME:
            self._footer.mode_button.set_info(self._mode, self._settings.user_name())

    def _save_collapsed(self) -> None:
        try:
            self._settings.set(_COLLAPSED_KEY, ",".join(sorted(self._list.collapsed())) or None)
        except sqlite3.Error:
            pass

    def _on_activated(self, row: _Row) -> None:
        if row.kind == "action":
            self.manage_syllabus_requested.emit()
            return
        if self._search.text():
            self.clear_search()
        self.navigate.emit(row.kind, row.arg)

    def _on_search_text(self, text: str) -> None:
        if self._silent:
            return
        if not text.strip():
            self._debounce.stop()
            self._emit_search()
        else:
            self._debounce.start()

    def _emit_search(self) -> None:
        query = self._search.text().strip()
        if query != self._last_query:
            self._last_query = query
            self.search_changed.emit(query)

    def _on_menu(self, target: object, pos: QPoint) -> None:
        if self._mode != MODE_FACILITATOR:
            return
        on_row = isinstance(target, _Row) and target.kind in ("module", "action")
        on_header = isinstance(target, _Section) and target.key == "modules"
        if not (on_row or on_header):
            return
        menu = popup_menu(self)
        edit = menu.addAction("Edit Modules\u2026")
        if on_row:
            self._list.set_context(target.key)
        chosen = menu.exec(pos)
        self._list.set_context(None)
        if chosen is edit:
            self.manage_syllabus_requested.emit()

    def _show_mode_menu(self) -> None:
        button = self._footer.mode_button
        menu = popup_menu(self)
        menu.setMinimumWidth(max(170, button.width()))
        for mode, (title, _, _) in _MODE_INFO.items():
            action = menu.addAction(_check_icon(mode == self._mode), title)
            action.setData(mode)
        pos = button.mapToGlobal(QPoint(0, -menu.sizeHint().height() - 4))
        button.menu_open = True
        button.update()
        chosen = menu.exec(pos)
        button.menu_open = False
        button.update()
        if chosen is not None and chosen.data() != self._mode:
            self.mode_switch_requested.emit(chosen.data())

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._search and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Down:
            self._list.setFocus(Qt.FocusReason.TabFocusReason)
            return True
        return super().eventFilter(obj, event)

    def sizeHint(self) -> QSize:
        return QSize(240, 600)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), theme().sidebar_color())
