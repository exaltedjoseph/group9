"""Windows DWM helpers: live blur materials, dark title metrics, rounded corners and
native frame styles for a frameless window. Every function is a safe no-op elsewhere."""
# TODO(branch1): implement design system and shared controls.
from __future__ import annotations
import ctypes
import sys
from ctypes import wintypes
IS_WINDOWS = sys.platform == 'win32'
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWA_MICA_EFFECT = 1029
DWMSBT_NONE = 1
DWMSBT_MAINWINDOW = 2
DWMSBT_TRANSIENTWINDOW = 3
DWMSBT_TABBEDWINDOW = 4
DWMWCP_ROUND = 2
WCA_ACCENT_POLICY = 19
ACCENT_DISABLED = 0
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
GWL_STYLE = -16
WS_MAXIMIZEBOX = 65536
WS_MINIMIZEBOX = 131072
WS_THICKFRAME = 262144
WS_SYSMENU = 524288
WS_CAPTION = 12582912
SWP_NOSIZE = 1
SWP_NOMOVE = 2
SWP_NOZORDER = 4
SWP_NOACTIVATE = 16
SWP_FRAMECHANGED = 32
WM_NCCALCSIZE = 131
WM_NCHITTEST = 132
WM_NCACTIVATE = 134
WM_NCLBUTTONDOWN = 161
WM_SYSCOMMAND = 274
HTCLIENT = 1
HTCAPTION = 2
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = (10, 11, 12, 13, 14)
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = (15, 16, 17)
SM_CXSIZEFRAME = 32
SM_CYSIZEFRAME = 33
SM_CXPADDEDBORDER = 92

class MARGINS(ctypes.Structure):
    _fields_ = [('cxLeftWidth', ctypes.c_int), ('cxRightWidth', ctypes.c_int), ('cyTopHeight', ctypes.c_int), ('cyBottomHeight', ctypes.c_int)]

class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [('AccentState', ctypes.c_int), ('AccentFlags', ctypes.c_int), ('GradientColor', ctypes.c_uint), ('AnimationId', ctypes.c_int)]

class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [('Attribute', ctypes.c_int), ('Data', ctypes.POINTER(ACCENT_POLICY)), ('SizeOfData', ctypes.c_size_t)]

class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [('rgrc', wintypes.RECT * 3), ('lppos', ctypes.c_void_p)]
if IS_WINDOWS:
    _user32 = ctypes.windll.user32
    _dwm = ctypes.windll.dwmapi
    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    _user32.IsZoomed.argtypes = [wintypes.HWND]
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    _dwm.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.POINTER(MARGINS)]
    try:
        _swca = _user32.SetWindowCompositionAttribute
        _swca.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA)]
        _swca.restype = wintypes.BOOL
    except AttributeError:
        _swca = None

def windows_build() -> int:
    ...

def _set_attr(hwnd: int, attr: int, value: int) -> bool:
    ...

def set_dark_mode(hwnd: int, dark: bool) -> None:
    ...

def set_round_corners(hwnd: int) -> None:
    ...

def extend_frame(hwnd: int, all_sides: bool=True) -> None:
    ...

def add_frame_styles(hwnd: int) -> None:
    """Give a Qt frameless window the native styles it needs for snap, animations and shadow."""
    ...

def set_system_backdrop(hwnd: int, kind: int=DWMSBT_TRANSIENTWINDOW) -> bool:
    """Windows 11 22H2+ backdrop (Acrylic / Mica). Requires an extended frame."""
    ...

def set_acrylic(hwnd: int, tint_rgba: tuple[int, int, int, int]) -> bool:
    """Windows 10 style acrylic via SetWindowCompositionAttribute."""
    ...

def apply_material(hwnd: int, dark: bool) -> str:
    """Best available live blur for the window. Returns "backdrop", "acrylic" or "none"."""
    ...

def is_maximized(hwnd: int) -> bool:
    ...

def resize_border_thickness(hwnd: int, horizontal: bool=True) -> int:
    """Width of the invisible sizing border in physical pixels (DPI aware)."""
    ...

def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    ...
