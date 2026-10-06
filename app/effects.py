"""Windows DWM helpers: live blur materials, dark title metrics, rounded corners and
native frame styles for a frameless window. Every function is a safe no-op elsewhere."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"

# DWM window attributes
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWA_MICA_EFFECT = 1029  # undocumented, Windows 11 21H2

DWMSBT_NONE = 1
DWMSBT_MAINWINDOW = 2       # Mica
DWMSBT_TRANSIENTWINDOW = 3  # Acrylic
DWMSBT_TABBEDWINDOW = 4     # Mica Alt

DWMWCP_ROUND = 2

# SetWindowCompositionAttribute
WCA_ACCENT_POLICY = 19
ACCENT_DISABLED = 0
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4

# window styles
GWL_STYLE = -16
WS_MAXIMIZEBOX = 0x00010000
WS_MINIMIZEBOX = 0x00020000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_CAPTION = 0x00C00000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

# messages / hit-test codes
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCACTIVATE = 0x0086
WM_NCLBUTTONDOWN = 0x00A1
WM_SYSCOMMAND = 0x0112
HTCLIENT = 1
HTCAPTION = 2
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17

SM_CXSIZEFRAME = 32
SM_CYSIZEFRAME = 33
SM_CXPADDEDBORDER = 92


class MARGINS(ctypes.Structure):
    _fields_ = [("cxLeftWidth", ctypes.c_int), ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int), ("cyBottomHeight", ctypes.c_int)]


class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.POINTER(ACCENT_POLICY)),
                ("SizeOfData", ctypes.c_size_t)]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


if IS_WINDOWS:
    _user32 = ctypes.windll.user32
    _dwm = ctypes.windll.dwmapi
    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    _user32.IsZoomed.argtypes = [wintypes.HWND]
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    _dwm.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.POINTER(MARGINS)]
    try:
        _swca = _user32.SetWindowCompositionAttribute
        _swca.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA)]
        _swca.restype = wintypes.BOOL
    except AttributeError:  # pragma: no cover
        _swca = None


def windows_build() -> int:
    if not IS_WINDOWS:
        return 0
    return sys.getwindowsversion().build


def _set_attr(hwnd: int, attr: int, value: int) -> bool:
    val = ctypes.c_int(value)
    return _dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0


def set_dark_mode(hwnd: int, dark: bool) -> None:
    if IS_WINDOWS:
        _set_attr(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0)


def set_round_corners(hwnd: int) -> None:
    if IS_WINDOWS and windows_build() >= 22000:
        _set_attr(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)


def extend_frame(hwnd: int, all_sides: bool = True) -> None:
    if not IS_WINDOWS:
        return
    m = MARGINS(-1, -1, -1, -1) if all_sides else MARGINS(0, 0, 1, 0)
    _dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(m))


def add_frame_styles(hwnd: int) -> None:
    """Give a Qt frameless window the native styles it needs for snap, animations and shadow."""
    if not IS_WINDOWS:
        return
    style = _user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    style |= WS_CAPTION | WS_THICKFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX | WS_SYSMENU
    _user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style)
    _user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)


def set_system_backdrop(hwnd: int, kind: int = DWMSBT_TRANSIENTWINDOW) -> bool:
    """Windows 11 22H2+ backdrop (Acrylic / Mica). Requires an extended frame."""
    if not IS_WINDOWS:
        return False
    build = windows_build()
    if build >= 22621:
        return _set_attr(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, kind)
    if build >= 22000:
        return _set_attr(hwnd, DWMWA_MICA_EFFECT, 1)
    return False


def set_acrylic(hwnd: int, tint_rgba: tuple[int, int, int, int]) -> bool:
    """Windows 10 style acrylic via SetWindowCompositionAttribute."""
    if not IS_WINDOWS or _swca is None:
        return False
    r, g, b, a = tint_rgba
    accent = ACCENT_POLICY()
    accent.AccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND
    accent.AccentFlags = 2
    accent.GradientColor = (a << 24) | (b << 16) | (g << 8) | r  # ABGR
    data = WINDOWCOMPOSITIONATTRIBDATA()
    data.Attribute = WCA_ACCENT_POLICY
    data.Data = ctypes.pointer(accent)
    data.SizeOfData = ctypes.sizeof(accent)
    return bool(_swca(hwnd, ctypes.byref(data)))


def apply_material(hwnd: int, dark: bool) -> str:
    """Best available live blur for the window. Returns "backdrop", "acrylic" or "none"."""
    if not IS_WINDOWS:
        return "none"
    set_dark_mode(hwnd, dark)
    set_round_corners(hwnd)
    extend_frame(hwnd, all_sides=True)
    if windows_build() >= 22621 and set_system_backdrop(hwnd, DWMSBT_TRANSIENTWINDOW):
        return "backdrop"
    tint = (32, 32, 34, 200) if dark else (242, 242, 245, 200)
    if set_acrylic(hwnd, tint):
        return "acrylic"
    return "none"


# --------------------------------------------------------------------------- frame metrics

def is_maximized(hwnd: int) -> bool:
    return bool(IS_WINDOWS and _user32.IsZoomed(hwnd))


def resize_border_thickness(hwnd: int, horizontal: bool = True) -> int:
    """Width of the invisible sizing border in physical pixels (DPI aware)."""
    if not IS_WINDOWS:
        return 0
    try:
        dpi = _user32.GetDpiForWindow(hwnd)
        frame = _user32.GetSystemMetricsForDpi(SM_CXSIZEFRAME if horizontal else SM_CYSIZEFRAME, dpi)
        padded = _user32.GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi)
    except AttributeError:
        frame = _user32.GetSystemMetrics(SM_CXSIZEFRAME if horizontal else SM_CYSIZEFRAME)
        padded = _user32.GetSystemMetrics(SM_CXPADDEDBORDER)
    return frame + padded


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom
