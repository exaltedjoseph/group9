from __future__ import annotations

import sys
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from app.core.library import Library  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


def wait_until(predicate, timeout: float = 15.0) -> bool:
    """Processes Qt events until `predicate()` is true or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return bool(predicate())


@pytest.fixture
def lib(tmp_path):
    library = Library(tmp_path / "lib")
    yield library
    library.close()


@pytest.fixture
def make_file(tmp_path):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)

    def _make(name: str, content: str | bytes = "hello") -> Path:
        path = src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    return _make


def make_zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path
