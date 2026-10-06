"""Per-user settings kept in a local SQLite file (never inside the shared library)."""
# TODO(branch2): implement the data layer and library browsing.
from __future__ import annotations
import os
import sqlite3
import threading
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from ..constants import API_KEY_ENV, DEFAULT_LIBRARY_DIR, DEFAULT_MODEL, DOTENV_FILES, SETTINGS_DB
KEY_API_KEY = 'api_key'
KEY_MODEL = 'model'
KEY_APPEARANCE = 'appearance'
KEY_MODE = 'mode'
KEY_USER_NAME = 'user_name'
KEY_LIBRARY_PATH = 'library_path'
KEY_GIT_ENABLED = 'git_enabled'
KEY_AUTO_PUSH = 'auto_push'
KEY_SIDEBAR_WIDTH = 'sidebar_width'
KEY_WINDOW_GEOMETRY = 'window_geometry'

def read_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, optional quotes, # comments."""
    ...

class Settings(QObject):
    changed = Signal(str)

    def __init__(self, path: Path | str | None=None) -> None:
        ...

    def close(self) -> None:
        ...

    def get(self, key: str, default: str | None=None) -> str | None:
        ...

    def set(self, key: str, value: str | None) -> None:
        ...

    def get_bool(self, key: str, default: bool=False) -> bool:
        ...

    def set_bool(self, key: str, value: bool) -> None:
        ...

    def api_key(self) -> str:
        """Environment variable, then .env file, then the key saved in Settings."""
        ...

    def api_key_source(self) -> str:
        """"env", "dotenv", "settings" or "" when no key is configured."""
        ...

    def _resolve_api_key(self) -> tuple[str, str]:
        ...

    def set_api_key(self, key: str) -> None:
        ...

    def model(self) -> str:
        ...

    def appearance(self) -> str:
        ...

    def mode(self) -> str | None:
        ...

    def user_name(self) -> str:
        ...

    def library_path(self) -> Path:
        ...

    def git_enabled(self) -> bool:
        ...

    def auto_push(self) -> bool:
        ...
