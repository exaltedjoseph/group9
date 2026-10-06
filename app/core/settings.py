"""Per-user settings kept in a local SQLite file (never inside the shared library)."""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ..constants import API_KEY_ENV, DEFAULT_LIBRARY_DIR, DEFAULT_MODEL, DOTENV_FILES, SETTINGS_DB

KEY_API_KEY = "api_key"
KEY_MODEL = "model"
KEY_APPEARANCE = "appearance"      # system | light | dark
KEY_MODE = "mode"                  # facilitator | intern
KEY_USER_NAME = "user_name"
KEY_LIBRARY_PATH = "library_path"
KEY_GIT_ENABLED = "git_enabled"    # "1" | "0"
KEY_AUTO_PUSH = "auto_push"        # "1" | "0"
KEY_SIDEBAR_WIDTH = "sidebar_width"
KEY_WINDOW_GEOMETRY = "window_geometry"


def read_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, optional quotes, # comments."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key.strip()] = value
    return values


class Settings(QObject):
    changed = Signal(str)  # key

    def __init__(self, path: Path | str | None = None) -> None:
        super().__init__()
        self.path = Path(path) if path else SETTINGS_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------------ raw access
    def get(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return default if row is None or row[0] is None else row[0]

    def set(self, key: str, value: str | None) -> None:
        with self._lock:
            if value is None:
                self._db.execute("DELETE FROM settings WHERE key = ?", (key,))
            else:
                self._db.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
            self._db.commit()
        self.changed.emit(key)

    def get_bool(self, key: str, default: bool = False) -> bool:
        v = self.get(key)
        return default if v is None else v == "1"

    def set_bool(self, key: str, value: bool) -> None:
        self.set(key, "1" if value else "0")

    # ------------------------------------------------------------------ API key
    def api_key(self) -> str:
        """Environment variable, then .env file, then the key saved in Settings."""
        key, _ = self._resolve_api_key()
        return key

    def api_key_source(self) -> str:
        """"env", "dotenv", "settings" or "" when no key is configured."""
        _, source = self._resolve_api_key()
        return source

    def _resolve_api_key(self) -> tuple[str, str]:
        env = os.environ.get(API_KEY_ENV, "").strip()
        if env:
            return env, "env"
        for path in DOTENV_FILES:
            value = read_dotenv(path).get(API_KEY_ENV, "").strip()
            if value:
                return value, "dotenv"
        stored = (self.get(KEY_API_KEY) or "").strip()
        return (stored, "settings") if stored else ("", "")

    def set_api_key(self, key: str) -> None:
        self.set(KEY_API_KEY, key.strip() or None)

    # ------------------------------------------------------------------ typed accessors
    def model(self) -> str:
        return self.get(KEY_MODEL) or DEFAULT_MODEL

    def appearance(self) -> str:
        return self.get(KEY_APPEARANCE) or "system"

    def mode(self) -> str | None:
        return self.get(KEY_MODE)

    def user_name(self) -> str:
        return self.get(KEY_USER_NAME) or os.environ.get("USERNAME") or os.environ.get("USER") or ""

    def library_path(self) -> Path:
        stored = self.get(KEY_LIBRARY_PATH)
        return Path(stored) if stored else DEFAULT_LIBRARY_DIR

    def git_enabled(self) -> bool:
        return self.get_bool(KEY_GIT_ENABLED, True)

    def auto_push(self) -> bool:
        return self.get_bool(KEY_AUTO_PUSH, False)
