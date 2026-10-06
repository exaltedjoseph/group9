"""Apple-style design tokens: system colors, typography and the global stylesheet."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from .constants import FONTS_DIR


def rgba(color: QColor) -> str:
    """QColor -> QSS rgba() string (alpha 0-255)."""
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"


def C(value: str, alpha: int | None = None) -> QColor:
    color = QColor(value)
    if alpha is not None:
        color.setAlpha(alpha)
    return color


def with_alpha(color: QColor, alpha: int) -> QColor:
    c = QColor(color)
    c.setAlpha(alpha)
    return c


@dataclass(frozen=True)
class Palette:
    dark: bool
    # accent (systemBlue)
    accent: QColor
    accent_hover: QColor
    accent_pressed: QColor
    on_accent: QColor
    # surfaces
    window: QColor          # main content background
    header: QColor          # translucent toolbar over content
    sidebar: QColor         # tint drawn over the live blur material
    sidebar_opaque: QColor  # used when no blur material is available
    sheet: QColor
    group: QColor           # grouped "inset" rows inside sheets
    group_border: QColor
    menu: QColor
    menu_border: QColor
    tooltip: QColor
    tooltip_text: QColor
    dim: QColor             # overlay behind sheets
    shadow: QColor
    # labels
    label: QColor
    secondary_label: QColor
    tertiary_label: QColor
    quaternary_label: QColor
    placeholder: QColor
    separator: QColor
    link: QColor
    # fills and controls
    fill: QColor
    fill_hover: QColor
    fill_pressed: QColor
    hover: QColor           # list row hover
    selection: QColor       # selected sidebar row (focused)
    selection_text: QColor
    selection_inactive: QColor
    control: QColor         # push button face
    control_border: QColor
    segment_selected: QColor
    field: QColor
    field_border: QColor
    search_field: QColor
    focus_ring: QColor
    scrollbar: QColor
    scrollbar_hover: QColor
    # chat
    bubble_user: QColor
    bubble_user_text: QColor
    bubble_assistant: QColor
    bubble_assistant_text: QColor
    code_bg: QColor
    code_border: QColor
    # system colors
    red: QColor
    green: QColor
    orange: QColor
    yellow: QColor
    gray: QColor
    # window controls
    traffic_close: QColor
    traffic_minimize: QColor
    traffic_zoom: QColor
    traffic_inactive: QColor
    traffic_glyph: QColor


LIGHT = Palette(
    dark=False,
    accent=C("#007AFF"),
    accent_hover=C("#1A88FF"),
    accent_pressed=C("#0062CC"),
    on_accent=C("#FFFFFF"),
    window=C("#FFFFFF"),
    header=C("#FFFFFF", 235),
    sidebar=C("#F2F2F5", 150),
    sidebar_opaque=C("#EEEEF1"),
    sheet=C("#F5F5F7"),
    group=C("#FFFFFF"),
    group_border=C("#000000", 18),
    menu=C("#F6F6F6", 252),
    menu_border=C("#000000", 30),
    tooltip=C("#FFFFFF"),
    tooltip_text=C("#000000", 217),
    dim=C("#000000", 45),
    shadow=C("#000000", 70),
    label=C("#000000", 217),
    secondary_label=C("#000000", 128),
    tertiary_label=C("#000000", 66),
    quaternary_label=C("#000000", 26),
    placeholder=C("#000000", 64),
    separator=C("#000000", 26),
    link=C("#0068DA"),
    fill=C("#000000", 13),
    fill_hover=C("#000000", 20),
    fill_pressed=C("#000000", 33),
    hover=C("#000000", 12),
    selection=C("#007AFF"),
    selection_text=C("#FFFFFF"),
    selection_inactive=C("#000000", 26),
    control=C("#FFFFFF"),
    control_border=C("#000000", 30),
    segment_selected=C("#FFFFFF"),
    field=C("#FFFFFF"),
    field_border=C("#000000", 35),
    search_field=C("#000000", 15),
    focus_ring=C("#007AFF", 120),
    scrollbar=C("#000000", 70),
    scrollbar_hover=C("#000000", 115),
    bubble_user=C("#0A7CFF"),
    bubble_user_text=C("#FFFFFF"),
    bubble_assistant=C("#E9E9EB"),
    bubble_assistant_text=C("#000000", 222),
    code_bg=C("#FFFFFF", 200),
    code_border=C("#000000", 18),
    red=C("#FF3B30"),
    green=C("#34C759"),
    orange=C("#FF9500"),
    yellow=C("#FFCC00"),
    gray=C("#8E8E93"),
    traffic_close=C("#FF5F57"),
    traffic_minimize=C("#FEBC2E"),
    traffic_zoom=C("#28C840"),
    traffic_inactive=C("#000000", 40),
    traffic_glyph=C("#000000", 140),
)

DARK = Palette(
    dark=True,
    accent=C("#0A84FF"),
    accent_hover=C("#3395FF"),
    accent_pressed=C("#0070E0"),
    on_accent=C("#FFFFFF"),
    window=C("#1E1E1E"),
    header=C("#1E1E1E", 235),
    sidebar=C("#262628", 175),
    sidebar_opaque=C("#262628"),
    sheet=C("#2A2A2C"),
    group=C("#FFFFFF", 12),
    group_border=C("#FFFFFF", 20),
    menu=C("#2C2C2E", 252),
    menu_border=C("#FFFFFF", 28),
    tooltip=C("#3A3A3C"),
    tooltip_text=C("#FFFFFF", 230),
    dim=C("#000000", 120),
    shadow=C("#000000", 150),
    label=C("#FFFFFF", 217),
    secondary_label=C("#FFFFFF", 140),
    tertiary_label=C("#FFFFFF", 64),
    quaternary_label=C("#FFFFFF", 26),
    placeholder=C("#FFFFFF", 77),
    separator=C("#FFFFFF", 26),
    link=C("#419CFF"),
    fill=C("#FFFFFF", 20),
    fill_hover=C("#FFFFFF", 30),
    fill_pressed=C("#FFFFFF", 45),
    hover=C("#FFFFFF", 15),
    selection=C("#0A84FF"),
    selection_text=C("#FFFFFF"),
    selection_inactive=C("#FFFFFF", 30),
    control=C("#FFFFFF", 36),
    control_border=C("#FFFFFF", 14),
    segment_selected=C("#636366"),
    field=C("#FFFFFF", 15),
    field_border=C("#FFFFFF", 30),
    search_field=C("#FFFFFF", 20),
    focus_ring=C("#0A84FF", 140),
    scrollbar=C("#FFFFFF", 70),
    scrollbar_hover=C("#FFFFFF", 115),
    bubble_user=C("#0A84FF"),
    bubble_user_text=C("#FFFFFF"),
    bubble_assistant=C("#3B3B3D"),
    bubble_assistant_text=C("#FFFFFF", 230),
    code_bg=C("#000000", 80),
    code_border=C("#FFFFFF", 18),
    red=C("#FF453A"),
    green=C("#30D158"),
    orange=C("#FF9F0A"),
    yellow=C("#FFD60A"),
    gray=C("#98989D"),
    traffic_close=C("#FF5F57"),
    traffic_minimize=C("#FEBC2E"),
    traffic_zoom=C("#28C840"),
    traffic_inactive=C("#FFFFFF", 45),
    traffic_glyph=C("#000000", 150),
)


_SYSTEM_COLORS = {
    "red": ("#FF3B30", "#FF453A"),
    "orange": ("#FF9500", "#FF9F0A"),
    "yellow": ("#FFCC00", "#FFD60A"),
    "green": ("#34C759", "#30D158"),
    "mint": ("#00C7BE", "#63E6E2"),
    "teal": ("#30B0C7", "#40CBE0"),
    "cyan": ("#32ADE6", "#64D2FF"),
    "blue": ("#007AFF", "#0A84FF"),
    "indigo": ("#5856D6", "#5E5CE6"),
    "purple": ("#AF52DE", "#BF5AF2"),
    "pink": ("#FF2D55", "#FF375F"),
    "brown": ("#A2845E", "#AC8E68"),
    "gray": ("#8E8E93", "#98989D"),
}


def system_color(name: str, dark: bool | None = None) -> QColor:
    """Apple system color by name ("blue", "orange", ...) for the active appearance."""
    if dark is None:
        dark = theme().is_dark
    light_hex, dark_hex = _SYSTEM_COLORS.get(name, _SYSTEM_COLORS["blue"])
    return QColor(dark_hex if dark else light_hex)


# --------------------------------------------------------------------------- typography

_SANS = ["SF Pro Text", "SF Pro", ".AppleSystemUIFont", "SF Pro Display",
         "Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", "Inter", "Helvetica Neue", "Arial"]
_DISPLAY = ["SF Pro Display", "SF Pro", ".AppleSystemUIFont", "SF Pro Text",
            "Segoe UI Variable Display", "Segoe UI Variable", "Segoe UI", "Inter", "Helvetica Neue", "Arial"]
_MONO = ["SF Mono", "Menlo", "Cascadia Code", "Cascadia Mono", "Consolas", "Courier New"]

# name -> (pixel size, weight). Mirrors the macOS dynamic type ramp.
TEXT_STYLES: dict[str, tuple[int, QFont.Weight]] = {
    "large_title": (26, QFont.Weight.Bold),
    "title1": (22, QFont.Weight.Bold),
    "title2": (17, QFont.Weight.DemiBold),
    "title3": (15, QFont.Weight.DemiBold),
    "headline": (13, QFont.Weight.DemiBold),
    "body": (13, QFont.Weight.Normal),
    "message": (14, QFont.Weight.Normal),
    "callout": (12, QFont.Weight.Normal),
    "subheadline": (11, QFont.Weight.Normal),
    "footnote": (10, QFont.Weight.Normal),
    "caption": (11, QFont.Weight.Normal),
}

_families: dict[str, str] = {}


def load_bundled_fonts() -> None:
    """Register any .otf/.ttf files dropped into assets/fonts (e.g. SF Pro)."""
    if not FONTS_DIR.is_dir():
        return
    for path in sorted(FONTS_DIR.iterdir()):
        if path.suffix.lower() in (".otf", ".ttf"):
            QFontDatabase.addApplicationFont(str(path))
    _families.clear()


def _resolve(candidates: list[str]) -> str:
    available = set(QFontDatabase.families())
    for name in candidates:
        if name in available:
            return name
    return QApplication.font().family()


def sans_family() -> str:
    if "sans" not in _families:
        _families["sans"] = _resolve(_SANS)
    return _families["sans"]


def display_family() -> str:
    if "display" not in _families:
        _families["display"] = _resolve(_DISPLAY)
    return _families["display"]


def mono_family() -> str:
    if "mono" not in _families:
        _families["mono"] = _resolve(_MONO)
    return _families["mono"]


def font(style: str = "body", weight: QFont.Weight | None = None, size: int | None = None) -> QFont:
    """A QFont for one of the TEXT_STYLES (sizes are in pixels, like macOS points)."""
    px, default_weight = TEXT_STYLES[style]
    px = size or px
    f = QFont(display_family() if px >= 20 else sans_family())
    f.setPixelSize(px)
    f.setWeight(weight if weight is not None else default_weight)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    if px >= 20:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 99)
    return f


def mono_font(size: int = 12) -> QFont:
    f = QFont(mono_family())
    f.setPixelSize(size)
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


# --------------------------------------------------------------------------- theme manager

class Theme(QObject):
    """Holds the active palette. Emits `changed` after the palette/stylesheet switch."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._mode = "system"
        self._dark = self._system_dark()
        self.material = False  # True when the window has a live blur backdrop
        self._asset_dir = Path(tempfile.gettempdir()) / "GeminiChatAssets"
        self._asset_dir.mkdir(parents=True, exist_ok=True)
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_system_scheme)

    # -- state
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_dark(self) -> bool:
        return self._dark

    @property
    def palette(self) -> Palette:
        return DARK if self._dark else LIGHT

    def sidebar_color(self) -> QColor:
        p = self.palette
        return p.sidebar if self.material else p.sidebar_opaque

    def set_mode(self, mode: str) -> None:
        if mode not in ("system", "light", "dark"):
            mode = "system"
        self._mode = mode
        self._refresh(force=True)

    # -- internals
    @staticmethod
    def _system_dark() -> bool:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark

    def _on_system_scheme(self, *_):
        if self._mode == "system":
            self._refresh()

    def _refresh(self, force: bool = False) -> None:
        dark = self._system_dark() if self._mode == "system" else self._mode == "dark"
        if dark == self._dark and not force:
            return
        self._dark = dark
        self.apply()
        self.changed.emit()

    def apply(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        p = self.palette
        app.setPalette(_qpalette(p))
        app.setStyleSheet(build_stylesheet(p, self._make_assets(p)))

    def _make_assets(self, p: Palette) -> dict[str, str]:
        from . import icons

        suffix = "dark" if p.dark else "light"
        out = {}
        for name, color in (("chevron_up_down", p.secondary_label), ("chevron_down", p.secondary_label)):
            path = self._asset_dir / f"{name}_{suffix}.png"
            icons.icon_pixmap(name, color, 12, 2.0).save(str(path))
            out[name] = path.as_posix()
        return out


_theme: Theme | None = None


def theme() -> Theme:
    global _theme
    if _theme is None:
        _theme = Theme()
    return _theme


def palette() -> Palette:
    return theme().palette


def _qpalette(p: Palette) -> QPalette:
    qp = QPalette()
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
        qp.setColor(group, QPalette.ColorRole.Window, p.window)
        qp.setColor(group, QPalette.ColorRole.Base, p.window)
        qp.setColor(group, QPalette.ColorRole.AlternateBase, p.window)
        qp.setColor(group, QPalette.ColorRole.Button, p.window)
        qp.setColor(group, QPalette.ColorRole.Highlight, p.accent)
        qp.setColor(group, QPalette.ColorRole.HighlightedText, p.on_accent)
        qp.setColor(group, QPalette.ColorRole.ToolTipBase, p.tooltip)
        qp.setColor(group, QPalette.ColorRole.ToolTipText, p.tooltip_text)
        qp.setColor(group, QPalette.ColorRole.Link, p.link)
        qp.setColor(group, QPalette.ColorRole.PlaceholderText, p.placeholder)
        text = p.tertiary_label if group == QPalette.ColorGroup.Disabled else p.label
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
            qp.setColor(group, role, text)
    return qp


def build_stylesheet(p: Palette, assets: dict[str, str]) -> str:
    accent_soft = rgba(with_alpha(p.accent, 90))
    disabled_accent = rgba(with_alpha(p.accent, 100))
    return f"""
QWidget {{ color: {rgba(p.label)}; }}
QLabel {{ background: transparent; }}
QToolTip {{
    background: {rgba(p.tooltip)}; color: {rgba(p.tooltip_text)};
    border: 1px solid {rgba(p.menu_border)}; border-radius: 6px; padding: 4px 7px;
}}

QScrollArea, QAbstractScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px 1px 2px 0; }}
QScrollBar::handle:vertical {{ background: {rgba(p.scrollbar)}; border-radius: 3px; min-height: 36px; margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {rgba(p.scrollbar_hover)}; border-radius: 4px; margin: 0 1px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0 2px 1px 2px; }}
QScrollBar::handle:horizontal {{ background: {rgba(p.scrollbar)}; border-radius: 3px; min-width: 36px; margin: 2px 0; }}
QScrollBar::handle:horizontal:hover {{ background: {rgba(p.scrollbar_hover)}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QMenu {{
    background: {rgba(p.menu)}; border: 1px solid {rgba(p.menu_border)};
    border-radius: 8px; padding: 5px;
}}
QMenu::item {{ padding: 4px 24px 4px 12px; border-radius: 5px; color: {rgba(p.label)}; background: transparent; }}
QMenu::item:selected {{ background: {rgba(p.accent)}; color: {rgba(p.on_accent)}; }}
QMenu::item:disabled {{ color: {rgba(p.tertiary_label)}; }}
QMenu::separator {{ height: 1px; background: {rgba(p.separator)}; margin: 5px 10px; }}
QMenu::icon {{ padding-left: 8px; }}

QLineEdit, QPlainTextEdit, QTextEdit {{
    background: {rgba(p.field)}; color: {rgba(p.label)};
    border: 1px solid {rgba(p.field_border)}; border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {accent_soft}; selection-color: {rgba(p.label)};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {rgba(p.accent)}; }}
QLineEdit:disabled {{ color: {rgba(p.tertiary_label)}; }}

QPushButton {{
    background: {rgba(p.control)}; color: {rgba(p.label)};
    border: 1px solid {rgba(p.control_border)}; border-radius: 6px;
    padding: 4px 14px; min-height: 18px;
}}
QPushButton:hover {{ background: {rgba(p.fill_hover) if p.dark else rgba(p.control)}; border-color: {rgba(p.field_border)}; }}
QPushButton:pressed {{ background: {rgba(p.fill_pressed)}; }}
QPushButton:disabled {{ color: {rgba(p.tertiary_label)}; }}
QPushButton:focus {{ outline: none; }}
QPushButton[variant="primary"] {{ background: {rgba(p.accent)}; color: {rgba(p.on_accent)}; border: 1px solid {rgba(p.accent)}; }}
QPushButton[variant="primary"]:hover {{ background: {rgba(p.accent_hover)}; border-color: {rgba(p.accent_hover)}; }}
QPushButton[variant="primary"]:pressed {{ background: {rgba(p.accent_pressed)}; border-color: {rgba(p.accent_pressed)}; }}
QPushButton[variant="primary"]:disabled {{ background: {disabled_accent}; border-color: transparent; color: rgba(255, 255, 255, 170); }}
QPushButton[variant="destructive"] {{ background: {rgba(p.red)}; color: #FFFFFF; border: 1px solid {rgba(p.red)}; }}
QPushButton[variant="destructive"]:hover {{ background: {rgba(p.red.lighter(108))}; }}
QPushButton[variant="destructive"]:pressed {{ background: {rgba(p.red.darker(115))}; }}
QPushButton[variant="plain"] {{ background: transparent; border: none; color: {rgba(p.accent)}; padding: 2px 4px; }}
QPushButton[variant="plain"]:hover {{ color: {rgba(p.accent_hover)}; }}
QPushButton[variant="plain"]:pressed {{ color: {rgba(p.accent_pressed)}; }}
QPushButton[variant="large"] {{ padding: 7px 18px; border-radius: 8px; }}

QComboBox {{
    background: {rgba(p.control)}; color: {rgba(p.label)};
    border: 1px solid {rgba(p.control_border)}; border-radius: 6px;
    padding: 4px 26px 4px 10px; min-height: 18px;
}}
QComboBox:hover {{ border-color: {rgba(p.field_border)}; }}
QComboBox:focus {{ border-color: {rgba(p.accent)}; }}
QComboBox::drop-down {{ border: none; width: 22px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url({assets.get("chevron_up_down", "")}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {rgba(p.menu)}; border: 1px solid {rgba(p.menu_border)}; border-radius: 8px;
    padding: 4px; outline: 0; color: {rgba(p.label)};
    selection-background-color: {rgba(p.accent)}; selection-color: {rgba(p.on_accent)};
}}
QComboBox QAbstractItemView::item {{ min-height: 24px; padding: 0 8px; border-radius: 5px; }}

QListView, QListWidget, QTreeView {{ background: transparent; border: none; outline: 0; }}
QSplitter::handle {{ background: {rgba(p.separator)}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
"""
