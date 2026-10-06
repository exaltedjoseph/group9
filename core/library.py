"""The resource library: local files + SQLite index, mirrored to Git-friendly JSON.

Layout of a library folder (this is what gets committed to Git):

    syllabus.json            modules and their topics
    data/resources.json      resource metadata
    data/classwork.json      classwork log
    resources/<module>/...   uploaded files
    classwork/<module>/...   classwork attachments
    .index/index.db          local SQLite index (git-ignored, rebuilt from the JSON when it changes)
"""
# TODO(branch2): implement the data layer and library browsing.
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import unicodedata
import uuid
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable
from PySide6.QtCore import QObject, Signal
from ..constants import KIND_NAMES, MODULE_COLORS
from .models import ClassworkEntry, Module, Resource, Topic
TextExtractor = Callable[[Path], str]
_SCHEMA = "\nCREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);\nCREATE TABLE IF NOT EXISTS modules (\n    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',\n    color TEXT NOT NULL DEFAULT 'blue', position INTEGER NOT NULL DEFAULT 0\n);\nCREATE TABLE IF NOT EXISTS topics (\n    module_id TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0,\n    PRIMARY KEY (module_id, id)\n);\nCREATE TABLE IF NOT EXISTS resources (\n    id TEXT PRIMARY KEY, title TEXT NOT NULL, module_id TEXT NOT NULL, topic_id TEXT,\n    kind TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', keywords TEXT NOT NULL DEFAULT '[]',\n    filename TEXT NOT NULL, path TEXT NOT NULL, size INTEGER NOT NULL DEFAULT 0, sha256 TEXT NOT NULL DEFAULT '',\n    uploader TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL,\n    ai_suggested INTEGER NOT NULL DEFAULT 0\n);\nCREATE INDEX IF NOT EXISTS idx_resources_module ON resources(module_id, topic_id);\nCREATE TABLE IF NOT EXISTS classwork (\n    id TEXT PRIMARY KEY, module_id TEXT NOT NULL, topic_id TEXT, date TEXT NOT NULL, title TEXT NOT NULL,\n    description TEXT NOT NULL DEFAULT '', facilitator TEXT NOT NULL DEFAULT '', attachment TEXT,\n    attachment_name TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL\n);\nCREATE INDEX IF NOT EXISTS idx_classwork_module ON classwork(module_id, date);\nCREATE TABLE IF NOT EXISTS text_cache (sha256 TEXT PRIMARY KEY, text TEXT NOT NULL);\nCREATE VIRTUAL TABLE IF NOT EXISTS resources_fts USING fts5(\n    id UNINDEXED, title, keywords, topic, module, description, filename, content,\n    tokenize = 'unicode61 remove_diacritics 2'\n);\n"
_BM25 = 'bm25(resources_fts, 0.0, 10.0, 6.0, 4.0, 3.0, 3.0, 2.0, 1.0)'
DEFAULT_SYLLABUS: list[dict] = [{'name': 'Python Fundamentals', 'color': 'blue', 'description': 'Core Python syntax and problem solving.', 'topics': ['Variables & Data Types', 'Control Flow', 'Functions', 'Data Structures', 'Files & Exceptions']}, {'name': 'Object-Oriented Programming', 'color': 'purple', 'description': 'Designing programs with classes and objects.', 'topics': ['Classes & Objects', 'Inheritance & Polymorphism', 'Design Principles']}, {'name': 'Version Control with Git', 'color': 'orange', 'description': 'Tracking and sharing work with Git and GitHub.', 'topics': ['Git Basics', 'Branching & Merging', 'Collaboration & Pull Requests']}, {'name': 'Databases & SQL', 'color': 'green', 'description': 'Relational data, SQL and using databases from Python.', 'topics': ['Relational Design', 'SQL Queries', 'Python & SQLite']}, {'name': 'Desktop GUI Development', 'color': 'teal', 'description': 'Building desktop interfaces in Python.', 'topics': ['Widgets & Layouts', 'Events & Callbacks', 'Packaging Apps']}, {'name': 'Data Analysis', 'color': 'pink', 'description': 'Working with data using NumPy, pandas and charts.', 'topics': ['NumPy', 'pandas', 'Data Visualization']}, {'name': 'Software Testing', 'color': 'indigo', 'description': 'Writing reliable code with tests and debugging.', 'topics': ['Unit Testing', 'Test-Driven Development', 'Debugging']}, {'name': 'AI & APIs', 'color': 'mint', 'description': 'Calling web APIs and working with AI models.', 'topics': ['Working with APIs', 'Prompt Design', 'Gemini API']}]
_GITIGNORE = '.index/\n.env\n*.tmp\n'
_WINDOWS_RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}

class LibraryError(Exception):
    """A user-facing problem (message is safe to show in the UI)."""

def slugify(text: str, fallback: str='item') -> str:
    ...

def safe_filename(name: str) -> str:
    ...

def normalize_keywords(keywords: Iterable[str]) -> list[str]:
    ...

def file_sha256(path: Path) -> str:
    ...

def _new_id() -> str:
    ...

def _fts_query(query: str) -> str:
    ...

def _default_extractor(path: Path) -> str:
    ...

class Library(QObject):
    changed = Signal(str)
    commit_requested = Signal(str, list)

    def __init__(self, root: Path | str, text_extractor: TextExtractor | None=None, index_path: Path | str | None=None) -> None:
        ...

    def close(self) -> None:
        ...

    def _ensure_layout(self) -> bool:
        ...

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        ...

    @staticmethod
    def _read_json(path: Path, key: str) -> list[dict]:
        ...

    def _json_hash(self) -> str:
        ...

    def _meta(self, key: str) -> str | None:
        ...

    def _set_meta(self, key: str, value: str) -> None:
        ...

    def sync_from_json(self, force: bool=False) -> bool:
        """Rebuild the SQLite index if the JSON files changed (e.g. after `git pull`)."""
        ...

    def reload(self) -> None:
        """Re-read the JSON mirror (call after pulling changes from Git)."""
        ...

    def _export(self, *which: str) -> list[str]:
        """Write the JSON mirror for the given parts; returns the touched relative paths."""
        ...

    def _done(self, part: str, message: str, paths: list[str]) -> None:
        ...

    def rel(self, path: Path) -> str:
        ...

    def abs(self, rel_path: str) -> Path:
        ...

    def file_path(self, resource: Resource) -> Path:
        ...

    def attachment_path(self, entry: ClassworkEntry) -> Path | None:
        ...

    @staticmethod
    def _unique_path(folder: Path, filename: str) -> Path:
        ...

    def copy_to(self, resource: Resource, dest_dir: Path | str) -> Path:
        """Download a copy of the resource file into `dest_dir` (never overwrites)."""
        ...

    def _insert_module(self, m: Module, position: int) -> None:
        ...

    def modules(self) -> list[Module]:
        ...

    def module(self, module_id: str | None) -> Module | None:
        ...

    def module_name(self, module_id: str | None) -> str:
        ...

    def topic_name(self, module_id: str | None, topic_id: str | None) -> str:
        ...

    def _unique_module_id(self, name: str) -> str:
        ...

    def add_module(self, name: str, description: str='', color: str | None=None, topics: Iterable[str]=()) -> Module:
        ...

    def update_module(self, module_id: str, name: str | None=None, description: str | None=None, color: str | None=None) -> Module:
        ...

    def move_module(self, module_id: str, new_index: int) -> None:
        ...

    def module_usage(self, module_id: str) -> tuple[int, int]:
        """(resource count, classwork count) for a module."""
        ...

    def delete_module(self, module_id: str, delete_contents: bool=False) -> None:
        ...

    @staticmethod
    def _unique_topic_id(module: Module, name: str) -> str:
        ...

    def add_topic(self, module_id: str, name: str) -> Topic:
        ...

    def rename_topic(self, module_id: str, topic_id: str, name: str) -> None:
        ...

    def delete_topic(self, module_id: str, topic_id: str) -> None:
        ...

    @staticmethod
    def _resource(row: sqlite3.Row) -> Resource:
        ...

    def _insert_resource(self, r: Resource) -> None:
        ...

    def _content_text(self, r: Resource) -> str:
        ...

    def content_text(self, resource: Resource) -> str:
        """Text extracted from the resource file (cached), used for search and AI suggestions."""
        ...

    def _index_resource(self, r: Resource) -> None:
        ...

    def _reindex(self, module_id: str | None=None) -> None:
        ...

    def _validate(self, module_id: str, topic_id: str | None, kind: str) -> tuple[Module, str | None]:
        ...

    def resources(self, module_id: str | None=None, topic_id: str | None=None, kind: str | None=None, sort: str='recent') -> list[Resource]:
        ...

    def recent(self, limit: int=30) -> list[Resource]:
        ...

    def resource(self, resource_id: str) -> Resource | None:
        ...

    def counts(self) -> dict[str, int]:
        """Resource count per module id, plus "__all__" and "__classwork__" totals."""
        ...

    def add_resource(self, source: Path | str, title: str, module_id: str, topic_id: str | None=None, kind: str='notes', description: str='', keywords: Iterable[str]=(), uploader: str='', ai_suggested: bool=False) -> Resource:
        ...

    def update_resource(self, resource_id: str, *, title: str | None=None, module_id: str | None=None, topic_id: str | None='', kind: str | None=None, description: str | None=None, keywords: Iterable[str] | None=None, replace_file: Path | str | None=None, ai_suggested: bool | None=None) -> Resource:
        """Update fields; `topic_id=""` keeps the current topic, `None` clears it."""
        ...

    def _remove_resource_file(self, r: Resource) -> list[str]:
        ...

    def delete_resource(self, resource_id: str) -> None:
        ...

    def search(self, query: str, module_id: str | None=None, limit: int=200) -> list[Resource]:
        """Full-text search over titles, keywords, topics, descriptions, file names and file contents."""
        ...

    def match_snippet(self, resource_id: str, query: str, tokens: int=14) -> str:
        """Short excerpt of the file contents around the search match ("" if none)."""
        ...

    def all_keywords(self) -> list[str]:
        """Every keyword in use, most frequent first (for autocompletion)."""
        ...

    @staticmethod
    def _classwork(row: sqlite3.Row) -> ClassworkEntry:
        ...

    def _insert_classwork(self, c: ClassworkEntry) -> None:
        ...

    def classwork(self, module_id: str | None=None, topic_id: str | None=None) -> list[ClassworkEntry]:
        ...

    def classwork_entry(self, entry_id: str) -> ClassworkEntry | None:
        ...

    def _store_attachment(self, module: Module, date: str, source: Path | str) -> tuple[str, str]:
        ...

    def _remove_attachment(self, c: ClassworkEntry) -> list[str]:
        ...

    @staticmethod
    def _check_date(date: str) -> str:
        ...

    def add_classwork(self, module_id: str, date: str, title: str, description: str='', topic_id: str | None=None, facilitator: str='', attachment: Path | str | None=None) -> ClassworkEntry:
        ...

    def update_classwork(self, entry_id: str, *, module_id: str | None=None, topic_id: str | None='', date: str | None=None, title: str | None=None, description: str | None=None, attachment: Path | str | None=None, remove_attachment: bool=False) -> ClassworkEntry:
        """Update fields; `topic_id=""` keeps the current topic, `None` clears it."""
        ...

    def delete_classwork(self, entry_id: str) -> None:
        ...

    def search_classwork(self, query: str, module_id: str | None=None) -> list[ClassworkEntry]:
        ...
