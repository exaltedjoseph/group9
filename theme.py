"""Apple-style design tokens: system colors, typography and the global stylesheet."""
# TODO(branch1): implement design system and shared controls.
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
    ...

def C(value: str, alpha: int | None=None) -> QColor:
    ...

def with_alpha(color: QColor, alpha: int) -> QColor:
    ...

@dataclass(frozen=True)
class Palette:
    dark: bool
    accent: QColor
    accent_hover: QColor
    accent_pressed: QColor
    on_accent: QColor
    window: QColor
    header: QColor
    sidebar: QColor
    sidebar_opaque: QColor
    sheet: QColor
    group: QColor
    group_border: QColor
    menu: QColor
    menu_border: QColor
    tooltip: QColor
    tooltip_text: QColor
    dim: QColor
    shadow: QColor
    label: QColor
    secondary_label: QColor
    tertiary_label: QColor
    quaternary_label: QColor
    placeholder: QColor
    separator: QColor
    link: QColor
    fill: QColor
    fill_hover: QColor
    fill_pressed: QColor
    hover: QColor
    selection: QColor
    selection_text: QColor
    selection_inactive: QColor
    control: QColor
    control_border: QColor
    segment_selected: QColor
    field: QColor
    field_border: QColor
    search_field: QColor
    focus_ring: QColor
    scrollbar: QColor
    scrollbar_hover: QColor
    bubble_user: QColor
    bubble_user_text: QColor
    bubble_assistant: QColor
    bubble_assistant_text: QColor
    code_bg: QColor
    code_border: QColor
    red: QColor
    green: QColor
    orange: QColor
    yellow: QColor
    gray: QColor
    traffic_close: QColor
    traffic_minimize: QColor
    traffic_zoom: QColor
    traffic_inactive: QColor
    traffic_glyph: QColor
LIGHT = Palette(dark=False, accent=C('#007AFF'), accent_hover=C('#1A88FF'), accent_pressed=C('#0062CC'), on_accent=C('#FFFFFF'), window=C('#FFFFFF'), header=C('#FFFFFF', 235), sidebar=C('#F2F2F5', 150), sidebar_opaque=C('#EEEEF1'), sheet=C('#F5F5F7'), group=C('#FFFFFF'), group_border=C('#000000', 18), menu=C('#F6F6F6', 252), menu_border=C('#000000', 30), tooltip=C('#FFFFFF'), tooltip_text=C('#000000', 217), dim=C('#000000', 45), shadow=C('#000000', 70), label=C('#000000', 217), secondary_label=C('#000000', 128), tertiary_label=C('#000000', 66), quaternary_label=C('#000000', 26), placeholder=C('#000000', 64), separator=C('#000000', 26), link=C('#0068DA'), fill=C('#000000', 13), fill_hover=C('#000000', 20), fill_pressed=C('#000000', 33), hover=C('#000000', 12), selection=C('#007AFF'), selection_text=C('#FFFFFF'), selection_inactive=C('#000000', 26), control=C('#FFFFFF'), control_border=C('#000000', 30), segment_selected=C('#FFFFFF'), field=C('#FFFFFF'), field_border=C('#000000', 35), search_field=C('#000000', 15), focus_ring=C('#007AFF', 120), scrollbar=C('#000000', 70), scrollbar_hover=C('#000000', 115), bubble_user=C('#0A7CFF'), bubble_user_text=C('#FFFFFF'), bubble_assistant=C('#E9E9EB'), bubble_assistant_text=C('#000000', 222), code_bg=C('#FFFFFF', 200), code_border=C('#000000', 18), red=C('#FF3B30'), green=C('#34C759'), orange=C('#FF9500'), yellow=C('#FFCC00'), gray=C('#8E8E93'), traffic_close=C('#FF5F57'), traffic_minimize=C('#FEBC2E'), traffic_zoom=C('#28C840'), traffic_inactive=C('#000000', 40), traffic_glyph=C('#000000', 140))
DARK = Palette(dark=True, accent=C('#0A84FF'), accent_hover=C('#3395FF'), accent_pressed=C('#0070E0'), on_accent=C('#FFFFFF'), window=C('#1E1E1E'), header=C('#1E1E1E', 235), sidebar=C('#262628', 175), sidebar_opaque=C('#262628'), sheet=C('#2A2A2C'), group=C('#FFFFFF', 12), group_border=C('#FFFFFF', 20), menu=C('#2C2C2E', 252), menu_border=C('#FFFFFF', 28), tooltip=C('#3A3A3C'), tooltip_text=C('#FFFFFF', 230), dim=C('#000000', 120), shadow=C('#000000', 150), label=C('#FFFFFF', 217), secondary_label=C('#FFFFFF', 140), tertiary_label=C('#FFFFFF', 64), quaternary_label=C('#FFFFFF', 26), placeholder=C('#FFFFFF', 77), separator=C('#FFFFFF', 26), link=C('#419CFF'), fill=C('#FFFFFF', 20), fill_hover=C('#FFFFFF', 30), fill_pressed=C('#FFFFFF', 45), hover=C('#FFFFFF', 15), selection=C('#0A84FF'), selection_text=C('#FFFFFF'), selection_inactive=C('#FFFFFF', 30), control=C('#FFFFFF', 36), control_border=C('#FFFFFF', 14), segment_selected=C('#636366'), field=C('#FFFFFF', 15), field_border=C('#FFFFFF', 30), search_field=C('#FFFFFF', 20), focus_ring=C('#0A84FF', 140), scrollbar=C('#FFFFFF', 70), scrollbar_hover=C('#FFFFFF', 115), bubble_user=C('#0A84FF'), bubble_user_text=C('#FFFFFF'), bubble_assistant=C('#3B3B3D'), bubble_assistant_text=C('#FFFFFF', 230), code_bg=C('#000000', 80), code_border=C('#FFFFFF', 18), red=C('#FF453A'), green=C('#30D158'), orange=C('#FF9F0A'), yellow=C('#FFD60A'), gray=C('#98989D'), traffic_close=C('#FF5F57'), traffic_minimize=C('#FEBC2E'), traffic_zoom=C('#28C840'), traffic_inactive=C('#FFFFFF', 45), traffic_glyph=C('#000000', 150))
_SYSTEM_COLORS = {'red': ('#FF3B30', '#FF453A'), 'orange': ('#FF9500', '#FF9F0A'), 'yellow': ('#FFCC00', '#FFD60A'), 'green': ('#34C759', '#30D158'), 'mint': ('#00C7BE', '#63E6E2'), 'teal': ('#30B0C7', '#40CBE0'), 'cyan': ('#32ADE6', '#64D2FF'), 'blue': ('#007AFF', '#0A84FF'), 'indigo': ('#5856D6', '#5E5CE6'), 'purple': ('#AF52DE', '#BF5AF2'), 'pink': ('#FF2D55', '#FF375F'), 'brown': ('#A2845E', '#AC8E68'), 'gray': ('#8E8E93', '#98989D')}

def system_color(name: str, dark: bool | None=None) -> QColor:
    """Apple system color by name ("blue", "orange", ...) for the active appearance."""
    ...
_SANS = ['SF Pro Text', 'SF Pro', '.AppleSystemUIFont', 'SF Pro Display', 'Segoe UI Variable Text', 'Segoe UI Variable', 'Segoe UI', 'Inter', 'Helvetica Neue', 'Arial']
_DISPLAY = ['SF Pro Display', 'SF Pro', '.AppleSystemUIFont', 'SF Pro Text', 'Segoe UI Variable Display', 'Segoe UI Variable', 'Segoe UI', 'Inter', 'Helvetica Neue', 'Arial']
_MONO = ['SF Mono', 'Menlo', 'Cascadia Code', 'Cascadia Mono', 'Consolas', 'Courier New']
TEXT_STYLES: dict[str, tuple[int, QFont.Weight]] = {'large_title': (26, QFont.Weight.Bold), 'title1': (22, QFont.Weight.Bold), 'title2': (17, QFont.Weight.DemiBold), 'title3': (15, QFont.Weight.DemiBold), 'headline': (13, QFont.Weight.DemiBold), 'body': (13, QFont.Weight.Normal), 'message': (14, QFont.Weight.Normal), 'callout': (12, QFont.Weight.Normal), 'subheadline': (11, QFont.Weight.Normal), 'footnote': (10, QFont.Weight.Normal), 'caption': (11, QFont.Weight.Normal)}
_families: dict[str, str] = {}

def load_bundled_fonts() -> None:
    """Register any .otf/.ttf files dropped into assets/fonts (e.g. SF Pro)."""
    ...

def _resolve(candidates: list[str]) -> str:
    ...

def sans_family() -> str:
    ...

def display_family() -> str:
    ...

def mono_family() -> str:
    ...

def font(style: str='body', weight: QFont.Weight | None=None, size: int | None=None) -> QFont:
    """A QFont for one of the TEXT_STYLES (sizes are in pixels, like macOS points)."""
    ...

def mono_font(size: int=12) -> QFont:
    ...

class Theme(QObject):
    """Holds the active palette. Emits `changed` after the palette/stylesheet switch."""
    changed = Signal()

    def __init__(self) -> None:
        ...

    @property
    def mode(self) -> str:
        ...

    @property
    def is_dark(self) -> bool:
        ...

    @property
    def palette(self) -> Palette:
        ...

    def sidebar_color(self) -> QColor:
        ...

    def set_mode(self, mode: str) -> None:
        ...

    @staticmethod
    def _system_dark() -> bool:
        ...

    def _on_system_scheme(self, *_):
        ...

    def _refresh(self, force: bool=False) -> None:
        ...

    def apply(self) -> None:
        ...

    def _make_assets(self, p: Palette) -> dict[str, str]:
        ...
_theme: Theme | None = None

def theme() -> Theme:
    ...

def palette() -> Palette:
    ...

def _qpalette(p: Palette) -> QPalette:
    ...

def build_stylesheet(p: Palette, assets: dict[str, str]) -> str:
    ...
