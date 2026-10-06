"""Frameless main window: Windows caption buttons, translucent sidebar and content stack."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QByteArray, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (QAbstractButton, QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox,
                               QComboBox, QHBoxLayout, QLineEdit, QStackedWidget, QTabBar, QWidget)

from .. import effects
from ..constants import APP_NAME, MODE_FACILITATOR, MODE_INTERN
from ..core import settings as S
from ..theme import palette, theme
from .toolbar import CAPTION_BUTTON_WIDTH

TITLEBAR_HEIGHT = 52
WM_NCMOUSEMOVE, WM_NCLBUTTONUP, WM_NCLBUTTONDBLCLK, WM_NCMOUSELEAVE = 0x00A0, 0x00A2, 0x00A3, 0x02A2
HTMAXBUTTON = 9
SIDEBAR_MIN, SIDEBAR_MAX, SIDEBAR_DEFAULT = 200, 360, 240
_INTERACTIVE = (QAbstractButton, QLineEdit, QAbstractSpinBox, QComboBox, QAbstractSlider, QTabBar,
                QAbstractScrollArea)


# --------------------------------------------------------------------------- caption buttons

MINIMIZE, MAXIMIZE, CLOSE = range(3)
_CLOSE_RED = QColor("#C42B1C")


class CaptionButtons(QWidget):
    """Windows 11 minimize / maximize / close buttons. The maximize button is reported to Windows
    as HTMAXBUTTON, so hovering it opens Snap Layouts; its clicks arrive as non-client messages."""

    W = CAPTION_BUTTON_WIDTH

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._win = window
        self._hover = -1
        self._pressed = -1
        self.setFixedSize(3 * self.W, TITLEBAR_HEIGHT)
        self.setMouseTracking(True)
        families = set(QFontDatabase.families())
        family = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), None)
        self._glyph_font = QFont(family) if family else None
        if self._glyph_font is not None:
            self._glyph_font.setPixelSize(10)
        theme().changed.connect(self.update)

    def button_rect(self, index: int) -> QRect:
        return QRect(index * self.W, 0, self.W, self.height())

    def index_at(self, pos: QPoint) -> int:
        if not self.rect().contains(pos):
            return -1
        return min(2, pos.x() // self.W)

    def hover_index(self) -> int:
        return self._hover

    def set_hover(self, index: int) -> None:
        if index != self._hover:
            self._hover = index
            if index < 0:
                self._pressed = -1
            self.update()

    def set_pressed(self, index: int) -> None:
        if index != self._pressed:
            self._pressed = index
            self.update()

    def pressed_index(self) -> int:
        return self._pressed

    def trigger(self, index: int) -> None:
        if index == MINIMIZE:
            self._win.showMinimized()
        elif index == MAXIMIZE:
            self._win.showNormal() if self._win.isMaximized() else self._win.showMaximized()
        elif index == CLOSE:
            self._win.close()

    def mouseMoveEvent(self, e):
        self.set_hover(self.index_at(e.position().toPoint()))

    def leaveEvent(self, e):
        self.set_hover(-1)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.set_pressed(self.index_at(e.position().toPoint()))

    def mouseReleaseEvent(self, e):
        index = self.index_at(e.position().toPoint())
        pressed = self._pressed
        self.set_pressed(-1)
        if e.button() == Qt.MouseButton.LeftButton and index == pressed and index >= 0:
            self.trigger(index)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = palette()
        dark = theme().is_dark
        active = self._win.isActiveWindow()
        for i in range(3):
            r = self.button_rect(i)
            glyph = QColor(pal.label if active else pal.tertiary_label)
            if i == CLOSE and (self._hover == i or self._pressed == i):
                p.fillRect(r, _CLOSE_RED if self._pressed != i else _CLOSE_RED.lighter(112))
                glyph = QColor("#FFFFFF")
            elif self._pressed == i:
                p.fillRect(r, QColor(255, 255, 255, 11) if dark else QColor(0, 0, 0, 6))
                glyph.setAlphaF(glyph.alphaF() * 0.75)
            elif self._hover == i:
                p.fillRect(r, QColor(255, 255, 255, 15) if dark else QColor(0, 0, 0, 10))
            self._draw_glyph(p, i, r, glyph)

    def _draw_glyph(self, p: QPainter, index: int, r: QRect, color: QColor) -> None:
        maximized = self._win.isMaximized()
        if self._glyph_font is not None:
            code = {MINIMIZE: "\uE921", MAXIMIZE: "\uE923" if maximized else "\uE922", CLOSE: "\uE8BB"}[index]
            p.setFont(self._glyph_font)
            p.setPen(color)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, code)
            return
        c = QRectF(r).center()
        p.setPen(QPen(color, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if index == MINIMIZE:
            p.drawLine(QPointF(c.x() - 5, c.y()), QPointF(c.x() + 5, c.y()))
        elif index == MAXIMIZE:
            p.drawRect(QRectF(c.x() - 5, c.y() - 5, 10, 10))
        else:
            p.drawLine(QPointF(c.x() - 5, c.y() - 5), QPointF(c.x() + 5, c.y() + 5))
            p.drawLine(QPointF(c.x() + 5, c.y() - 5), QPointF(c.x() - 5, c.y() + 5))


# --------------------------------------------------------------------------- frameless base

class FramelessWindow(QWidget):
    """Top-level window without a system title bar that keeps native snap, resize, shadow and
    rounded corners on Windows, with a live acrylic backdrop where we paint transparent pixels."""

    RESIZE_MARGIN = 6

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.material = "none"
        self._native_ready = False
        self.caption = CaptionButtons(self)
        theme().changed.connect(self._on_theme)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.caption.move(self.width() - self.caption.width(), 0)
        self.caption.raise_()

    # -- native setup
    def showEvent(self, e):
        super().showEvent(e)
        if not self._native_ready and effects.IS_WINDOWS:
            self._native_ready = True
            hwnd = int(self.winId())
            effects.add_frame_styles(hwnd)
            self.material = effects.apply_material(hwnd, theme().is_dark)
            theme().material = self.material != "none"
            theme().changed.emit()
        self.caption.raise_()

    def _on_theme(self) -> None:
        if self._native_ready:
            effects.set_dark_mode(int(self.winId()), theme().is_dark)
            if self.material == "acrylic":
                effects.apply_material(int(self.winId()), theme().is_dark)
        self.update()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() in (e.Type.ActivationChange, e.Type.WindowStateChange):
            self.caption.update()

    # -- drag regions
    def _is_caption(self, local: QPoint) -> bool:
        if local.y() >= TITLEBAR_HEIGHT or local.y() < 0:
            return False
        w = self.childAt(local)
        if w is None:
            return True
        if w is self.caption:
            return False
        while w is not None and w is not self:
            if isinstance(w, _INTERACTIVE) and w.isEnabled():
                return False
            if w.property("titleBarArea"):
                return True
            w = w.parentWidget()
        return False

    def nativeEvent(self, event_type, message):
        if not effects.IS_WINDOWS or event_type != b"windows_generic_MSG":
            return super().nativeEvent(event_type, message)
        msg = wintypes.MSG.from_address(int(message))
        hwnd = msg.hWnd
        if msg.message == effects.WM_NCCALCSIZE and msg.wParam:
            if effects.is_maximized(hwnd):
                params = effects.NCCALCSIZE_PARAMS.from_address(msg.lParam)
                bx = effects.resize_border_thickness(hwnd, True)
                by = effects.resize_border_thickness(hwnd, False)
                rc = params.rgrc[0]
                rc.left += bx
                rc.top += by
                rc.right -= bx
                rc.bottom -= by
            return True, 0
        if msg.message == effects.WM_NCHITTEST:
            x = ctypes.c_short(msg.lParam & 0xFFFF).value
            y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
            left, top, right, bottom = effects.window_rect(hwnd)
            dpr = self.devicePixelRatioF() or 1.0
            if not effects.is_maximized(hwnd):
                m = int(self.RESIZE_MARGIN * dpr)
                on_l, on_r = x < left + m, x >= right - m
                on_t, on_b = y < top + m, y >= bottom - m
                if on_t and on_l:
                    return True, effects.HTTOPLEFT
                if on_t and on_r:
                    return True, effects.HTTOPRIGHT
                if on_b and on_l:
                    return True, effects.HTBOTTOMLEFT
                if on_b and on_r:
                    return True, effects.HTBOTTOMRIGHT
                if on_l:
                    return True, effects.HTLEFT
                if on_r:
                    return True, effects.HTRIGHT
                if on_t:
                    return True, effects.HTTOP
                if on_b:
                    return True, effects.HTBOTTOM
            local = QPoint(int((x - left) / dpr), int((y - top) / dpr))
            if effects.is_maximized(hwnd):
                local -= QPoint(int(effects.resize_border_thickness(hwnd, True) / dpr),
                                int(effects.resize_border_thickness(hwnd, False) / dpr))
            if self.caption.isVisible() and self.caption.geometry().contains(local) \
                    and self.caption.index_at(local - self.caption.pos()) == MAXIMIZE:
                return True, HTMAXBUTTON
            if self._is_caption(local):
                return True, effects.HTCAPTION
            return True, effects.HTCLIENT
        if msg.message == WM_NCMOUSEMOVE:
            if msg.wParam == HTMAXBUTTON:
                self.caption.set_hover(MAXIMIZE)
            elif self.caption.hover_index() == MAXIMIZE:
                self.caption.set_hover(-1)
        elif msg.message == WM_NCMOUSELEAVE:
            if self.caption.hover_index() == MAXIMIZE:
                self.caption.set_hover(-1)
        elif msg.message in (effects.WM_NCLBUTTONDOWN, WM_NCLBUTTONDBLCLK) and msg.wParam == HTMAXBUTTON:
            self.caption.set_pressed(MAXIMIZE)
            return True, 0
        elif msg.message == WM_NCLBUTTONUP and msg.wParam == HTMAXBUTTON:
            if self.caption.pressed_index() == MAXIMIZE:
                self.caption.set_pressed(-1)
                self.caption.trigger(MAXIMIZE)
            return True, 0
        return super().nativeEvent(event_type, message)

    def paintEvent(self, _):
        if self.material == "none":
            p = QPainter(self)
            p.fillRect(self.rect(), palette().window)


# --------------------------------------------------------------------------- main window

class _SidebarHandle(QWidget):
    """Invisible drag handle on the sidebar edge."""

    def __init__(self, owner: "MainWindow") -> None:
        super().__init__(owner)
        self._owner = owner
        self._drag_x: float | None = None
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setFixedWidth(7)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_x = e.globalPosition().x() - self._owner.sidebar_width

    def mouseMoveEvent(self, e):
        if self._drag_x is not None:
            self._owner.set_sidebar_width(int(e.globalPosition().x() - self._drag_x))

    def mouseReleaseEvent(self, e):
        if self._drag_x is not None:
            self._drag_x = None
            self._owner.save_sidebar_width()


class _Body(QWidget):
    """Holds sidebar + content; paints the hairline between them."""

    def __init__(self, owner: "MainWindow") -> None:
        super().__init__(owner)
        self._owner = owner
        theme().changed.connect(self.update)

    def paintEvent(self, _):
        if not self._owner.sidebar.isVisible():
            return
        p = QPainter(self)
        x = self._owner.sidebar.geometry().right() + 1
        p.fillRect(x, 0, 1, self.height(), palette().window)
        p.fillRect(x, 0, 1, self.height(), palette().separator)


class MainWindow(FramelessWindow):
    def __init__(self, settings, library, git) -> None:
        super().__init__()
        from .assistant_view import AssistantView
        from .classwork_sheet import ClassworkSheet
        from .classwork_view import ClassworkView
        from .history_view import HistoryView
        from .home_view import HomeView
        from .library_view import LibraryView
        from .resource_sheet import ResourceSheet
        from .settings_sheet import SettingsSheet
        from .sidebar import Sidebar
        from .syllabus_sheet import SyllabusSheet
        from .welcome import WelcomeView

        self.settings = settings
        self.library = library
        self.git = git
        self.mode = settings.mode() or MODE_INTERN
        self._nav: tuple[str, object] = ("home", None)

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(920, 600)

        self.body = _Body(self)
        row = QHBoxLayout(self.body)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.sidebar = Sidebar(library, settings)
        self.sidebar_width = max(SIDEBAR_MIN, min(SIDEBAR_MAX, int(settings.get(S.KEY_SIDEBAR_WIDTH) or SIDEBAR_DEFAULT)))
        self.sidebar.setFixedWidth(self.sidebar_width)
        row.addWidget(self.sidebar)
        row.addSpacing(1)

        self.stack = QStackedWidget()
        self.home_view = HomeView(library, settings)
        self.assistant_view = AssistantView(library, settings)
        self.library_view = LibraryView(library, settings)
        self.classwork_view = ClassworkView(library, settings)
        self.history_view = HistoryView(git)
        for w in (self.home_view, self.assistant_view, self.library_view, self.classwork_view,
                  self.history_view):
            self.stack.addWidget(w)
        row.addWidget(self.stack, 1)

        self.welcome = WelcomeView(settings, self)
        self.handle = _SidebarHandle(self)

        self.resource_sheet = ResourceSheet(self, library, settings)
        self.classwork_sheet = ClassworkSheet(self, library, settings)
        self.syllabus_sheet = SyllabusSheet(self, library)
        self.settings_sheet = SettingsSheet(self, settings, library, git)

        self._wire()
        self._shortcuts()
        self._restore_geometry()

        if settings.mode() is None:
            self._show_welcome(True)
        else:
            self._apply_mode(self.mode)
            self._navigate("home", None)
            self._show_welcome(False)
        self.caption.raise_()

    # ------------------------------------------------------------------ wiring
    def _wire(self) -> None:
        sb = self.sidebar
        sb.navigate.connect(self._navigate)
        sb.search_changed.connect(self._on_search)
        sb.settings_requested.connect(self.settings_sheet.open)
        sb.mode_switch_requested.connect(self.set_mode)
        sb.manage_syllabus_requested.connect(self._open_syllabus)

        lv = self.library_view
        lv.add_resource_requested.connect(self._add_resource)
        lv.edit_resource_requested.connect(self._edit_resource)
        lv.log_classwork_requested.connect(self._log_classwork)
        lv.edit_classwork_requested.connect(self._edit_classwork)
        lv.explain_resource_requested.connect(self._explain_resource)
        self.classwork_view.log_classwork_requested.connect(self._log_classwork)
        self.classwork_view.edit_classwork_requested.connect(self._edit_classwork)

        home = self.home_view
        home.navigate.connect(self._go)
        home.open_resource_requested.connect(self._open_resource)
        home.add_resource_requested.connect(self._add_resource)
        home.log_classwork_requested.connect(self._log_classwork)
        home.ask_assistant_requested.connect(self._ask_assistant)
        self.assistant_view.settings_requested.connect(self.settings_sheet.open)
        self.assistant_view.open_resource_requested.connect(self._open_resource)

        self.resource_sheet.saved.connect(self._on_resource_saved)
        self.resource_sheet.settings_requested.connect(self.settings_sheet.open)
        self.settings_sheet.mode_changed.connect(self.set_mode)
        self.welcome.mode_chosen.connect(self._on_mode_chosen)

        self.library.commit_requested.connect(self._commit)
        self.git.pulled.connect(self.library.reload)
        self.git.operation_failed.connect(self._git_failed)

    def _shortcuts(self) -> None:
        def sc(seq, fn):
            s = QShortcut(QKeySequence(seq), self)
            s.setContext(Qt.ShortcutContext.WindowShortcut)
            s.activated.connect(fn)

        sc("Ctrl+F", self.sidebar.focus_search)
        sc("Ctrl+,", self.settings_sheet.open)
        sc("Ctrl+N", lambda: self._add_resource(self._current_module(), []))
        sc("Ctrl+L", lambda: self._log_classwork(self._current_module()))
        sc("Ctrl+1", lambda: self._go("home"))
        sc("Ctrl+2", lambda: self._go("all"))
        sc("Ctrl+3", lambda: self._go("recent"))
        sc("Ctrl+4", lambda: self._go("classwork"))
        sc("Ctrl+K", lambda: self._go("assistant"))
        sc("F5", self._reload)

    # ------------------------------------------------------------------ navigation
    def _go(self, kind: str, arg=None) -> None:
        self.sidebar.clear_search()
        self.sidebar.select(kind, arg)
        self._navigate(kind, arg)

    def _navigate(self, kind: str, arg) -> None:
        if kind == "history" and self.mode != MODE_FACILITATOR:
            kind, arg = "all", None
        self._nav = (kind, arg)
        if kind == "home":
            self.home_view.refresh()
            self.stack.setCurrentWidget(self.home_view)
        elif kind == "assistant":
            self.stack.setCurrentWidget(self.assistant_view)
        elif kind == "classwork":
            self.classwork_view.show_all()
            self.stack.setCurrentWidget(self.classwork_view)
        elif kind == "history":
            self.history_view.refresh()
            self.stack.setCurrentWidget(self.history_view)
        else:
            if kind == "recent":
                self.library_view.show_recent()
            elif kind == "module" and arg:
                self.library_view.show_module(arg)
            else:
                self.library_view.show_all()
            self.stack.setCurrentWidget(self.library_view)

    def _on_search(self, query: str) -> None:
        if query.strip():
            self.library_view.show_search(query)
            self.stack.setCurrentWidget(self.library_view)
        else:
            self._navigate(*self._nav)

    def _current_module(self):
        return self._nav[1] if self._nav[0] == "module" else None

    def _reload(self) -> None:
        self.library.reload()
        self._navigate(*self._nav)

    # ------------------------------------------------------------------ modes
    def _show_welcome(self, visible: bool) -> None:
        self.welcome.setVisible(visible)
        self.body.setVisible(not visible)
        self.handle.setVisible(not visible)
        if visible:
            self.welcome.raise_()
        self._layout_children()
        self.caption.raise_()

    def _on_mode_chosen(self, mode: str) -> None:
        self.set_mode(mode)
        self._go("home")
        self._show_welcome(False)

    def set_mode(self, mode: str) -> None:
        if mode not in (MODE_FACILITATOR, MODE_INTERN):
            return
        if self.settings.mode() != mode:
            self.settings.set(S.KEY_MODE, mode)
        self._apply_mode(mode)
        if self._nav[0] == "history" and mode != MODE_FACILITATOR:
            self._go("all")

    def _apply_mode(self, mode: str) -> None:
        self.mode = mode
        self.sidebar.set_mode(mode)
        self.home_view.set_mode(mode)
        self.assistant_view.set_mode(mode)
        self.library_view.set_mode(mode)
        self.classwork_view.set_mode(mode)

    def _facilitator(self) -> bool:
        return self.mode == MODE_FACILITATOR

    # ------------------------------------------------------------------ actions
    def _add_resource(self, module_id, files) -> None:
        if self._facilitator():
            self.resource_sheet.open_add(module_id, list(files or []))

    def _edit_resource(self, resource_id: str) -> None:
        if self._facilitator():
            self.resource_sheet.open_edit(resource_id)

    def _log_classwork(self, module_id) -> None:
        if self._facilitator():
            self.classwork_sheet.open_add(module_id)

    def _edit_classwork(self, entry_id: str) -> None:
        if self._facilitator():
            self.classwork_sheet.open_edit(entry_id)

    def _open_syllabus(self) -> None:
        if self._facilitator():
            self.syllabus_sheet.open()

    def _open_resource(self, resource_id: str) -> None:
        self._go("all")
        self.library_view.select_resource(resource_id)

    def _ask_assistant(self, prompt: str) -> None:
        self._go("assistant")
        if prompt.strip():
            self.assistant_view.ask(prompt)

    def _explain_resource(self, resource_id: str) -> None:
        self._go("assistant")
        self.assistant_view.explain_resource(resource_id)

    def _on_resource_saved(self, resource_id: str) -> None:
        if self.stack.currentWidget() is self.library_view:
            self.library_view.select_resource(resource_id)

    def _commit(self, message: str, paths: list) -> None:
        if self.settings.git_enabled():
            self.git.commit(message, list(paths))

    def _git_failed(self, message: str) -> None:
        try:
            from .actions import show_toast
            show_toast(self, message, "warning")
        except Exception:
            pass

    # ------------------------------------------------------------------ layout
    def set_sidebar_width(self, width: int) -> None:
        self.sidebar_width = max(SIDEBAR_MIN, min(SIDEBAR_MAX, width))
        self.sidebar.setFixedWidth(self.sidebar_width)
        self._layout_children()

    def save_sidebar_width(self) -> None:
        self.settings.set(S.KEY_SIDEBAR_WIDTH, str(self.sidebar_width))

    def _layout_children(self) -> None:
        r = self.rect()
        self.body.setGeometry(r)
        self.welcome.setGeometry(r)
        self.handle.setGeometry(self.sidebar_width - 3, TITLEBAR_HEIGHT, 7, max(0, r.height() - TITLEBAR_HEIGHT))
        self.handle.raise_()
        for sheet in (self.resource_sheet, self.classwork_sheet, self.syllabus_sheet, self.settings_sheet):
            if sheet.isVisible():
                sheet.raise_()
        self.caption.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout_children()

    def _restore_geometry(self) -> None:
        raw = self.settings.get(S.KEY_WINDOW_GEOMETRY)
        if raw:
            try:
                if self.restoreGeometry(QByteArray.fromBase64(raw.encode("ascii"))):
                    return
            except Exception:
                pass
        self.resize(1240, 800)
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            self.move(screen.center() - self.rect().center())

    def closeEvent(self, e):
        self.settings.set(S.KEY_WINDOW_GEOMETRY, bytes(self.saveGeometry().toBase64()).decode("ascii"))
        super().closeEvent(e)
