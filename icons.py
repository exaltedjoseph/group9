"""Vector icons drawn in the spirit of SF Symbols (24-unit design grid)."""
# TODO(branch1): implement design system and shared controls.
from __future__ import annotations
import math
from functools import lru_cache
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap, QRadialGradient, QTransform
STROKE = 1.7

def squircle_path(rect: QRectF, radius: float) -> QPainterPath:
    """Rounded rect with Apple-style continuous ("squircle") corners."""
    ...

def _stroke(path: QPainterPath, width: float) -> QPainterPath:
    ...

def _poly(*pts: tuple[float, float], close: bool=False) -> QPainterPath:
    ...

def _circle(cx: float, cy: float, r: float) -> QPainterPath:
    ...

def _rrect(x: float, y: float, w: float, h: float, r: float) -> QPainterPath:
    ...

def _star(cx: float, cy: float, r: float, pinch: float=0.12) -> QPainterPath:
    """Four-pointed sparkle (Gemini-like) with concave sides."""
    ...

def _gear(cx: float, cy: float, outer: float, inner: float, teeth: int=8) -> QPainterPath:
    ...

def _shape(name: str, weight: float) -> QPainterPath:
    ...

@lru_cache(maxsize=256)
def _cached_shape(name: str, weight: float) -> QPainterPath:
    ...

def draw_icon(painter: QPainter, name: str, rect: QRectF, color: QColor, weight: float=1.0) -> None:
    """Paint icon `name` into `rect` (square) with `color`."""
    ...

def icon_pixmap(name: str, color: QColor, size: int, dpr: float=2.0, weight: float=1.0) -> QPixmap:
    ...

def make_icon(name: str, color: QColor, size: int=16, weight: float=1.0) -> QIcon:
    ...
_FILE_COLORS = {'pdf': '#E5352B', 'ppt': '#E8692A', 'pptx': '#E8692A', 'key': '#E8692A', 'odp': '#E8692A', 'doc': '#2B6DE5', 'docx': '#2B6DE5', 'pages': '#2B6DE5', 'odt': '#2B6DE5', 'rtf': '#2B6DE5', 'xls': '#22A355', 'xlsx': '#22A355', 'csv': '#22A355', 'numbers': '#22A355', 'ods': '#22A355', 'png': '#A550D8', 'jpg': '#A550D8', 'jpeg': '#A550D8', 'gif': '#A550D8', 'webp': '#A550D8', 'svg': '#A550D8', 'heic': '#A550D8', 'bmp': '#A550D8', 'mp4': '#5856D6', 'mov': '#5856D6', 'mkv': '#5856D6', 'avi': '#5856D6', 'webm': '#5856D6', 'mp3': '#E0367A', 'wav': '#E0367A', 'm4a': '#E0367A', 'zip': '#8E8E93', 'rar': '#8E8E93', '7z': '#8E8E93', 'tar': '#8E8E93', 'gz': '#8E8E93', 'py': '#14A0B4', 'ipynb': '#F37726', 'js': '#C9A800', 'ts': '#2F74C0', 'html': '#E4572E', 'css': '#2965F1', 'java': '#B07219', 'c': '#555555', 'cpp': '#00599C', 'sql': '#D18A00', 'json': '#8E8E93', 'md': '#6E6E73', 'txt': '#6E6E73'}

def file_color(ext: str) -> QColor:
    ...

def draw_file_icon(painter: QPainter, rect: QRectF, ext: str, dark: bool=False) -> None:
    """macOS-style document icon: white page, folded corner and a colored extension label."""
    ...

def draw_app_icon(painter: QPainter, rect: QRectF) -> None:
    """macOS-style app icon: blue-indigo squircle with a white open book."""
    ...

def app_icon() -> QIcon:
    ...
