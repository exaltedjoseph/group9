"""The resource library: local files + SQLite index, mirrored to Git-friendly JSON.

Layout of a library folder (this is what gets committed to Git):

    syllabus.json            modules and their topics
    data/resources.json      resource metadata
    data/classwork.json      classwork log
    resources/<module>/...   uploaded files
    classwork/<module>/...   classwork attachments
    .index/index.db          local SQLite index (git-ignored, rebuilt from the JSON when it changes)
"""
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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS modules (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT 'blue', position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS topics (
    module_id TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (module_id, id)
);
CREATE TABLE IF NOT EXISTS resources (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, module_id TEXT NOT NULL, topic_id TEXT,
    kind TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', keywords TEXT NOT NULL DEFAULT '[]',
    filename TEXT NOT NULL, path TEXT NOT NULL, size INTEGER NOT NULL DEFAULT 0, sha256 TEXT NOT NULL DEFAULT '',
    uploader TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL,
    ai_suggested INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_resources_module ON resources(module_id, topic_id);
CREATE TABLE IF NOT EXISTS classwork (
    id TEXT PRIMARY KEY, module_id TEXT NOT NULL, topic_id TEXT, date TEXT NOT NULL, title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '', facilitator TEXT NOT NULL DEFAULT '', attachment TEXT,
    attachment_name TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_classwork_module ON classwork(module_id, date);
CREATE TABLE IF NOT EXISTS text_cache (sha256 TEXT PRIMARY KEY, text TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS resources_fts USING fts5(
    id UNINDEXED, title, keywords, topic, module, description, filename, content,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""

# bm25 weights follow the column order of resources_fts (id is unindexed but still counted)
_BM25 = "bm25(resources_fts, 0.0, 10.0, 6.0, 4.0, 3.0, 3.0, 2.0, 1.0)"

DEFAULT_SYLLABUS: list[dict] = [
    {"name": "Python Fundamentals", "color": "blue",
     "description": "Core Python syntax and problem solving.",
     "topics": ["Variables & Data Types", "Control Flow", "Functions", "Data Structures", "Files & Exceptions"]},
    {"name": "Object-Oriented Programming", "color": "purple",
     "description": "Designing programs with classes and objects.",
     "topics": ["Classes & Objects", "Inheritance & Polymorphism", "Design Principles"]},
    {"name": "Version Control with Git", "color": "orange",
     "description": "Tracking and sharing work with Git and GitHub.",
     "topics": ["Git Basics", "Branching & Merging", "Collaboration & Pull Requests"]},
    {"name": "Databases & SQL", "color": "green",
     "description": "Relational data, SQL and using databases from Python.",
     "topics": ["Relational Design", "SQL Queries", "Python & SQLite"]},
    {"name": "Desktop GUI Development", "color": "teal",
     "description": "Building desktop interfaces in Python.",
     "topics": ["Widgets & Layouts", "Events & Callbacks", "Packaging Apps"]},
    {"name": "Data Analysis", "color": "pink",
     "description": "Working with data using NumPy, pandas and charts.",
     "topics": ["NumPy", "pandas", "Data Visualization"]},
    {"name": "Software Testing", "color": "indigo",
     "description": "Writing reliable code with tests and debugging.",
     "topics": ["Unit Testing", "Test-Driven Development", "Debugging"]},
    {"name": "AI & APIs", "color": "mint",
     "description": "Calling web APIs and working with AI models.",
     "topics": ["Working with APIs", "Prompt Design", "Gemini API"]},
]

_GITIGNORE = ".index/\n.env\n*.tmp\n"
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class LibraryError(Exception):
    """A user-facing problem (message is safe to show in the UI)."""


def slugify(text: str, fallback: str = "item") -> str:
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    norm = norm.replace("&", " and ")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    return slug[:48].strip("-") or fallback


def safe_filename(name: str) -> str:
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().strip(".")
    if not name:
        name = "file"
    stem = name.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED:
        name = "_" + name
    if len(name) > 120:
        p = PurePosixPath(name)
        name = p.stem[: 120 - len(p.suffix)] + p.suffix
    return name


def normalize_keywords(keywords: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for kw in keywords:
        kw = re.sub(r"\s+", " ", str(kw)).strip().strip(",;#").strip()
        if kw and kw.lower() not in seen:
            seen.add(kw.lower())
            out.append(kw)
    return out[:20]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _fts_query(query: str) -> str:
    tokens = re.findall(r"\w+", query, flags=re.UNICODE)
    return " AND ".join(f'"{t}"*' for t in tokens[:12])


def _default_extractor(path: Path) -> str:
    try:
        from .extract import extract_text
    except Exception:
        return ""
    try:
        return extract_text(path) or ""
    except Exception:
        return ""


class Library(QObject):
    changed = Signal(str)                 # "syllabus" | "resources" | "classwork" | "all"
    commit_requested = Signal(str, list)  # commit message, touched paths (relative, posix)

    def __init__(self, root: Path | str, text_extractor: TextExtractor | None = None,
                 index_path: Path | str | None = None) -> None:
        super().__init__()
        self.root = Path(root).resolve()
        self.resources_dir = self.root / "resources"
        self.classwork_dir = self.root / "classwork"
        self.data_dir = self.root / "data"
        self.syllabus_file = self.root / "syllabus.json"
        self.resources_file = self.data_dir / "resources.json"
        self.classwork_file = self.data_dir / "classwork.json"
        self.index_path = Path(index_path) if index_path else self.root / ".index" / "index.db"
        self._extract = text_extractor or _default_extractor
        self._lock = threading.RLock()
        self.created = self._ensure_layout()
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.index_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._db.commit()
        self.sync_from_json()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ================================================================== layout & JSON mirror
    def _ensure_layout(self) -> bool:
        created = not self.syllabus_file.exists()
        for d in (self.root, self.resources_dir, self.classwork_dir, self.data_dir):
            d.mkdir(parents=True, exist_ok=True)
        gitignore = self.root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(_GITIGNORE, encoding="utf-8")
        if created:
            modules = []
            for spec in DEFAULT_SYLLABUS:
                mid = slugify(spec["name"])
                topics = [{"id": slugify(t), "name": t} for t in spec["topics"]]
                modules.append({"id": mid, "name": spec["name"], "description": spec["description"],
                                "color": spec["color"], "topics": topics})
            self._write_json(self.syllabus_file, {"version": 1, "modules": modules})
        if not self.resources_file.exists():
            self._write_json(self.resources_file, {"version": 1, "resources": []})
        if not self.classwork_file.exists():
            self._write_json(self.classwork_file, {"version": 1, "classwork": []})
        return created

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    @staticmethod
    def _read_json(path: Path, key: str) -> list[dict]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise LibraryError(f"Could not read {path.name}: {exc}") from exc
        items = data.get(key, []) if isinstance(data, dict) else []
        return [i for i in items if isinstance(i, dict) and i.get("id")]

    def _json_hash(self) -> str:
        h = hashlib.sha256()
        for path in (self.syllabus_file, self.resources_file, self.classwork_file):
            try:
                h.update(path.read_bytes())
            except OSError:
                pass
            h.update(b"\x00")
        return h.hexdigest()

    def _meta(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self._db.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def sync_from_json(self, force: bool = False) -> bool:
        """Rebuild the SQLite index if the JSON files changed (e.g. after `git pull`)."""
        current = self._json_hash()
        with self._lock:
            if not force and self._meta("json_hash") == current:
                return False
            modules = [Module.from_json(m) for m in self._read_json(self.syllabus_file, "modules")]
            resources = [Resource.from_json(r) for r in self._read_json(self.resources_file, "resources")]
            classwork = [ClassworkEntry.from_json(c) for c in self._read_json(self.classwork_file, "classwork")]
            db = self._db
            db.execute("DELETE FROM modules")
            db.execute("DELETE FROM topics")
            db.execute("DELETE FROM resources")
            db.execute("DELETE FROM classwork")
            db.execute("DELETE FROM resources_fts")
            for pos, m in enumerate(modules):
                self._insert_module(m, pos)
            for r in resources:
                self._insert_resource(r)
            for c in classwork:
                self._insert_classwork(c)
            for r in resources:
                self._index_resource(r)
            self._set_meta("json_hash", current)
            db.commit()
        return True

    def reload(self) -> None:
        """Re-read the JSON mirror (call after pulling changes from Git)."""
        if self.sync_from_json():
            self.changed.emit("all")

    def _export(self, *which: str) -> list[str]:
        """Write the JSON mirror for the given parts; returns the touched relative paths."""
        touched = []
        with self._lock:
            if "syllabus" in which:
                self._write_json(self.syllabus_file, {"version": 1, "modules": [m.to_json() for m in self.modules()]})
                touched.append(self.rel(self.syllabus_file))
            if "resources" in which:
                rows = self._db.execute("SELECT * FROM resources ORDER BY created_at, id").fetchall()
                self._write_json(self.resources_file,
                                 {"version": 1, "resources": [self._resource(r).to_json() for r in rows]})
                touched.append(self.rel(self.resources_file))
            if "classwork" in which:
                rows = self._db.execute("SELECT * FROM classwork ORDER BY date, created_at, id").fetchall()
                self._write_json(self.classwork_file,
                                 {"version": 1, "classwork": [self._classwork(r).to_json() for r in rows]})
                touched.append(self.rel(self.classwork_file))
            self._set_meta("json_hash", self._json_hash())
            self._db.commit()
        return touched

    def _done(self, part: str, message: str, paths: list[str]) -> None:
        self.changed.emit(part)
        self.commit_requested.emit(message, sorted(set(paths)))

    # ================================================================== paths
    def rel(self, path: Path) -> str:
        return Path(path).resolve().relative_to(self.root).as_posix()

    def abs(self, rel_path: str) -> Path:
        p = (self.root / rel_path).resolve()
        if p != self.root and self.root not in p.parents:
            raise LibraryError("Path is outside the library.")
        return p

    def file_path(self, resource: Resource) -> Path:
        return self.abs(resource.path)

    def attachment_path(self, entry: ClassworkEntry) -> Path | None:
        return self.abs(entry.attachment) if entry.attachment else None

    @staticmethod
    def _unique_path(folder: Path, filename: str) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        candidate = folder / filename
        stem, suffix = Path(filename).stem, Path(filename).suffix
        n = 2
        while candidate.exists():
            candidate = folder / f"{stem} {n}{suffix}"
            n += 1
        return candidate

    def copy_to(self, resource: Resource, dest_dir: Path | str) -> Path:
        """Download a copy of the resource file into `dest_dir` (never overwrites)."""
        src = self.file_path(resource)
        if not src.exists():
            raise LibraryError("The file for this resource is missing from the library.")
        dest = self._unique_path(Path(dest_dir), safe_filename(resource.filename))
        shutil.copy2(src, dest)
        return dest

    # ================================================================== syllabus
    def _insert_module(self, m: Module, position: int) -> None:
        self._db.execute("INSERT OR REPLACE INTO modules (id, name, description, color, position) VALUES (?,?,?,?,?)",
                         (m.id, m.name, m.description, m.color, position))
        for tpos, t in enumerate(m.topics):
            self._db.execute("INSERT OR REPLACE INTO topics (module_id, id, name, position) VALUES (?,?,?,?)",
                             (m.id, t.id, t.name, tpos))

    def modules(self) -> list[Module]:
        with self._lock:
            mods = self._db.execute("SELECT * FROM modules ORDER BY position, name").fetchall()
            tops = self._db.execute("SELECT * FROM topics ORDER BY position, name").fetchall()
        by_module: dict[str, list[Topic]] = {}
        for t in tops:
            by_module.setdefault(t["module_id"], []).append(Topic(t["id"], t["name"]))
        return [Module(m["id"], m["name"], m["description"], m["color"], by_module.get(m["id"], [])) for m in mods]

    def module(self, module_id: str | None) -> Module | None:
        if not module_id:
            return None
        return next((m for m in self.modules() if m.id == module_id), None)

    def module_name(self, module_id: str | None) -> str:
        m = self.module(module_id)
        return m.name if m else "Unsorted"

    def topic_name(self, module_id: str | None, topic_id: str | None) -> str:
        m = self.module(module_id)
        t = m.topic(topic_id) if m else None
        return t.name if t else ""

    def _unique_module_id(self, name: str) -> str:
        base = slugify(name, "module")
        existing = {m.id for m in self.modules()}
        mid, n = base, 2
        while mid in existing:
            mid = f"{base}-{n}"
            n += 1
        return mid

    def add_module(self, name: str, description: str = "", color: str | None = None,
                   topics: Iterable[str] = ()) -> Module:
        name = name.strip()
        if not name:
            raise LibraryError("Module name can't be empty.")
        if any(m.name.lower() == name.lower() for m in self.modules()):
            raise LibraryError(f"A module named \u201c{name}\u201d already exists.")
        existing = self.modules()
        if color not in MODULE_COLORS:
            color = MODULE_COLORS[len(existing) % len(MODULE_COLORS)]
        module = Module(self._unique_module_id(name), name, description.strip(), color, [])
        seen: set[str] = set()
        for t in topics:
            t = t.strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                module.topics.append(Topic(self._unique_topic_id(module, t), t))
        with self._lock:
            self._insert_module(module, len(existing))
            self._db.commit()
        self._done("syllabus", f"Add module: {name}", self._export("syllabus"))
        return module

    def update_module(self, module_id: str, name: str | None = None, description: str | None = None,
                      color: str | None = None) -> Module:
        m = self.module(module_id)
        if m is None:
            raise LibraryError("Module not found.")
        if name is not None:
            name = name.strip()
            if not name:
                raise LibraryError("Module name can't be empty.")
            if any(o.id != module_id and o.name.lower() == name.lower() for o in self.modules()):
                raise LibraryError(f"A module named \u201c{name}\u201d already exists.")
            m.name = name
        if description is not None:
            m.description = description.strip()
        if color is not None and color in MODULE_COLORS:
            m.color = color
        with self._lock:
            self._db.execute("UPDATE modules SET name = ?, description = ?, color = ? WHERE id = ?",
                             (m.name, m.description, m.color, m.id))
            self._db.commit()
            self._reindex(module_id=m.id)
        self._done("syllabus", f"Update module: {m.name}", self._export("syllabus"))
        return m

    def move_module(self, module_id: str, new_index: int) -> None:
        mods = self.modules()
        ids = [m.id for m in mods]
        if module_id not in ids:
            return
        ids.remove(module_id)
        ids.insert(max(0, min(new_index, len(ids))), module_id)
        with self._lock:
            for pos, mid in enumerate(ids):
                self._db.execute("UPDATE modules SET position = ? WHERE id = ?", (pos, mid))
            self._db.commit()
        self._done("syllabus", "Reorder modules", self._export("syllabus"))

    def module_usage(self, module_id: str) -> tuple[int, int]:
        """(resource count, classwork count) for a module."""
        with self._lock:
            r = self._db.execute("SELECT COUNT(*) FROM resources WHERE module_id = ?", (module_id,)).fetchone()[0]
            c = self._db.execute("SELECT COUNT(*) FROM classwork WHERE module_id = ?", (module_id,)).fetchone()[0]
        return int(r), int(c)

    def delete_module(self, module_id: str, delete_contents: bool = False) -> None:
        m = self.module(module_id)
        if m is None:
            return
        n_res, n_cw = self.module_usage(module_id)
        if (n_res or n_cw) and not delete_contents:
            parts = []
            if n_res:
                parts.append(f"{n_res} resource{'s' if n_res != 1 else ''}")
            if n_cw:
                parts.append(f"{n_cw} classwork {'entries' if n_cw != 1 else 'entry'}")
            raise LibraryError(f"\u201c{m.name}\u201d still contains {' and '.join(parts)}. "
                               "Move or delete them first.")
        touched: list[str] = []
        if delete_contents:
            for r in self.resources(module_id=module_id):
                touched += self._remove_resource_file(r)
            for c in self.classwork(module_id=module_id):
                touched += self._remove_attachment(c)
        with self._lock:
            self._db.execute("DELETE FROM resources_fts WHERE id IN (SELECT id FROM resources WHERE module_id = ?)",
                             (module_id,))
            self._db.execute("DELETE FROM resources WHERE module_id = ?", (module_id,))
            self._db.execute("DELETE FROM classwork WHERE module_id = ?", (module_id,))
            self._db.execute("DELETE FROM topics WHERE module_id = ?", (module_id,))
            self._db.execute("DELETE FROM modules WHERE id = ?", (module_id,))
            self._db.commit()
        touched += self._export("syllabus", "resources", "classwork")
        self._done("all", f"Delete module: {m.name}", touched)

    @staticmethod
    def _unique_topic_id(module: Module, name: str) -> str:
        base = slugify(name, "topic")
        existing = {t.id for t in module.topics}
        tid, n = base, 2
        while tid in existing:
            tid = f"{base}-{n}"
            n += 1
        return tid

    def add_topic(self, module_id: str, name: str) -> Topic:
        m = self.module(module_id)
        if m is None:
            raise LibraryError("Module not found.")
        name = name.strip()
        if not name:
            raise LibraryError("Topic name can't be empty.")
        if any(t.name.lower() == name.lower() for t in m.topics):
            raise LibraryError(f"\u201c{name}\u201d is already a topic in {m.name}.")
        topic = Topic(self._unique_topic_id(m, name), name)
        with self._lock:
            self._db.execute("INSERT INTO topics (module_id, id, name, position) VALUES (?,?,?,?)",
                             (module_id, topic.id, name, len(m.topics)))
            self._db.commit()
        self._done("syllabus", f"Add topic: {name} ({m.name})", self._export("syllabus"))
        return topic

    def rename_topic(self, module_id: str, topic_id: str, name: str) -> None:
        m = self.module(module_id)
        if m is None or m.topic(topic_id) is None:
            raise LibraryError("Topic not found.")
        name = name.strip()
        if not name:
            raise LibraryError("Topic name can't be empty.")
        if any(t.id != topic_id and t.name.lower() == name.lower() for t in m.topics):
            raise LibraryError(f"\u201c{name}\u201d is already a topic in {m.name}.")
        with self._lock:
            self._db.execute("UPDATE topics SET name = ? WHERE module_id = ? AND id = ?", (name, module_id, topic_id))
            self._db.commit()
            self._reindex(module_id=module_id)
        self._done("syllabus", f"Rename topic: {name} ({m.name})", self._export("syllabus"))

    def delete_topic(self, module_id: str, topic_id: str) -> None:
        m = self.module(module_id)
        t = m.topic(topic_id) if m else None
        if t is None:
            return
        with self._lock:
            self._db.execute("DELETE FROM topics WHERE module_id = ? AND id = ?", (module_id, topic_id))
            self._db.execute("UPDATE resources SET topic_id = NULL WHERE module_id = ? AND topic_id = ?",
                             (module_id, topic_id))
            self._db.execute("UPDATE classwork SET topic_id = NULL WHERE module_id = ? AND topic_id = ?",
                             (module_id, topic_id))
            self._db.commit()
            self._reindex(module_id=module_id)
        self._done("all", f"Delete topic: {t.name} ({m.name})", self._export("syllabus", "resources", "classwork"))

    # ================================================================== resources
    @staticmethod
    def _resource(row: sqlite3.Row) -> Resource:
        try:
            keywords = json.loads(row["keywords"] or "[]")
        except ValueError:
            keywords = []
        return Resource(
            id=row["id"], title=row["title"], module_id=row["module_id"], topic_id=row["topic_id"],
            kind=row["kind"], description=row["description"], keywords=keywords, filename=row["filename"],
            path=row["path"], size=row["size"], sha256=row["sha256"], uploader=row["uploader"],
            created_at=row["created_at"], updated_at=row["updated_at"], ai_suggested=bool(row["ai_suggested"]),
        )

    def _insert_resource(self, r: Resource) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO resources (id, title, module_id, topic_id, kind, description, keywords, filename, "
            "path, size, sha256, uploader, created_at, updated_at, ai_suggested) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r.id, r.title, r.module_id, r.topic_id, r.kind, r.description, json.dumps(r.keywords, ensure_ascii=False),
             r.filename, r.path, r.size, r.sha256, r.uploader, r.created_at, r.updated_at, int(r.ai_suggested)),
        )

    def _content_text(self, r: Resource) -> str:
        if r.sha256:
            row = self._db.execute("SELECT text FROM text_cache WHERE sha256 = ?", (r.sha256,)).fetchone()
            if row:
                return row[0]
        try:
            path = self.file_path(r)
        except LibraryError:
            return ""
        if not path.exists():
            return ""
        text = (self._extract(path) or "")[:200_000]
        if r.sha256:
            self._db.execute("INSERT OR REPLACE INTO text_cache (sha256, text) VALUES (?, ?)", (r.sha256, text))
        return text

    def content_text(self, resource: Resource) -> str:
        """Text extracted from the resource file (cached), used for search and AI suggestions."""
        with self._lock:
            text = self._content_text(resource)
            self._db.commit()
        return text

    def _index_resource(self, r: Resource) -> None:
        module_row = self._db.execute("SELECT name FROM modules WHERE id = ?", (r.module_id,)).fetchone()
        topic_row = self._db.execute("SELECT name FROM topics WHERE module_id = ? AND id = ?",
                                     (r.module_id, r.topic_id)).fetchone() if r.topic_id else None
        self._db.execute("DELETE FROM resources_fts WHERE id = ?", (r.id,))
        self._db.execute(
            "INSERT INTO resources_fts (id, title, keywords, topic, module, description, filename, content) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (r.id, r.title, " ".join(r.keywords), topic_row[0] if topic_row else "",
             module_row[0] if module_row else "", r.description, r.filename, self._content_text(r)),
        )

    def _reindex(self, module_id: str | None = None) -> None:
        sql, params = "SELECT * FROM resources", ()
        if module_id:
            sql, params = sql + " WHERE module_id = ?", (module_id,)
        for row in self._db.execute(sql, params).fetchall():
            self._index_resource(self._resource(row))
        self._db.commit()

    def _validate(self, module_id: str, topic_id: str | None, kind: str) -> tuple[Module, str | None]:
        m = self.module(module_id)
        if m is None:
            raise LibraryError("Choose a module for this resource.")
        if topic_id and m.topic(topic_id) is None:
            topic_id = None
        if kind not in KIND_NAMES:
            raise LibraryError("Unknown resource type.")
        return m, topic_id

    def resources(self, module_id: str | None = None, topic_id: str | None = None, kind: str | None = None,
                  sort: str = "recent") -> list[Resource]:
        where, params = [], []
        if module_id:
            where.append("module_id = ?")
            params.append(module_id)
        if topic_id:
            where.append("topic_id = ?")
            params.append(topic_id)
        if kind:
            where.append("kind = ?")
            params.append(kind)
        order = {
            "recent": "created_at DESC",
            "updated": "updated_at DESC",
            "title": "title COLLATE NOCASE ASC",
            "kind": "kind ASC, title COLLATE NOCASE ASC",
            "size": "size DESC",
        }.get(sort, "created_at DESC")
        sql = "SELECT * FROM resources" + (" WHERE " + " AND ".join(where) if where else "") + f" ORDER BY {order}"
        with self._lock:
            rows = self._db.execute(sql, params).fetchall()
        return [self._resource(r) for r in rows]

    def recent(self, limit: int = 30) -> list[Resource]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM resources ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._resource(r) for r in rows]

    def resource(self, resource_id: str) -> Resource | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM resources WHERE id = ?", (resource_id,)).fetchone()
        return self._resource(row) if row else None

    def counts(self) -> dict[str, int]:
        """Resource count per module id, plus "__all__" and "__classwork__" totals."""
        with self._lock:
            rows = self._db.execute("SELECT module_id, COUNT(*) AS n FROM resources GROUP BY module_id").fetchall()
            total = self._db.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
            cw = self._db.execute("SELECT COUNT(*) FROM classwork").fetchone()[0]
        out = {r["module_id"]: int(r["n"]) for r in rows}
        out["__all__"] = int(total)
        out["__classwork__"] = int(cw)
        return out

    def add_resource(self, source: Path | str, title: str, module_id: str, topic_id: str | None = None,
                     kind: str = "notes", description: str = "", keywords: Iterable[str] = (),
                     uploader: str = "", ai_suggested: bool = False) -> Resource:
        src = Path(source)
        if not src.is_file():
            raise LibraryError("The selected file could not be found.")
        m, topic_id = self._validate(module_id, topic_id, kind)
        filename = safe_filename(src.name)
        dest = self._unique_path(self.resources_dir / m.id, filename)
        shutil.copy2(src, dest)
        now = time.time()
        r = Resource(
            id=_new_id(), title=title.strip() or Path(filename).stem, module_id=m.id, topic_id=topic_id, kind=kind,
            description=description.strip(), keywords=normalize_keywords(keywords), filename=filename,
            path=self.rel(dest), size=dest.stat().st_size, sha256=file_sha256(dest), uploader=uploader.strip(),
            created_at=now, updated_at=now, ai_suggested=ai_suggested,
        )
        with self._lock:
            self._insert_resource(r)
            self._index_resource(r)
            self._db.commit()
        self._done("resources", f"Add resource: {r.title} ({m.name})", [r.path, *self._export("resources")])
        return r

    def update_resource(self, resource_id: str, *, title: str | None = None, module_id: str | None = None,
                        topic_id: str | None = "", kind: str | None = None, description: str | None = None,
                        keywords: Iterable[str] | None = None, replace_file: Path | str | None = None,
                        ai_suggested: bool | None = None) -> Resource:
        """Update fields; `topic_id=""` keeps the current topic, `None` clears it."""
        r = self.resource(resource_id)
        if r is None:
            raise LibraryError("Resource not found.")
        touched = []
        new_module = module_id or r.module_id
        new_topic = r.topic_id if topic_id == "" else topic_id
        if module_id and module_id != r.module_id and topic_id == "":
            new_topic = None
        m, new_topic = self._validate(new_module, new_topic, kind or r.kind)
        if title is not None:
            r.title = title.strip() or r.title
        if kind is not None:
            r.kind = kind
        if description is not None:
            r.description = description.strip()
        if keywords is not None:
            r.keywords = normalize_keywords(keywords)
        if ai_suggested is not None:
            r.ai_suggested = ai_suggested

        if replace_file is not None:
            src = Path(replace_file)
            if not src.is_file():
                raise LibraryError("The selected file could not be found.")
            touched += self._remove_resource_file(r)
            filename = safe_filename(src.name)
            dest = self._unique_path(self.resources_dir / m.id, filename)
            shutil.copy2(src, dest)
            r.filename, r.path = filename, self.rel(dest)
            r.size, r.sha256 = dest.stat().st_size, file_sha256(dest)
            touched.append(r.path)
        elif new_module != r.module_id:
            old = self.file_path(r)
            if old.exists():
                dest = self._unique_path(self.resources_dir / m.id, old.name)
                shutil.move(str(old), str(dest))
                touched += [r.path, self.rel(dest)]
                r.path = self.rel(dest)
        r.module_id, r.topic_id = m.id, new_topic
        r.updated_at = time.time()
        with self._lock:
            self._insert_resource(r)
            self._index_resource(r)
            self._db.commit()
        touched += self._export("resources")
        self._done("resources", f"Update resource: {r.title} ({m.name})", touched)
        return r

    def _remove_resource_file(self, r: Resource) -> list[str]:
        try:
            path = self.file_path(r)
        except LibraryError:
            return []
        if path.exists():
            path.unlink()
        return [r.path]

    def delete_resource(self, resource_id: str) -> None:
        r = self.resource(resource_id)
        if r is None:
            return
        touched = self._remove_resource_file(r)
        with self._lock:
            self._db.execute("DELETE FROM resources WHERE id = ?", (r.id,))
            self._db.execute("DELETE FROM resources_fts WHERE id = ?", (r.id,))
            self._db.commit()
        touched += self._export("resources")
        self._done("resources", f"Delete resource: {r.title}", touched)

    def search(self, query: str, module_id: str | None = None, limit: int = 200) -> list[Resource]:
        """Full-text search over titles, keywords, topics, descriptions, file names and file contents."""
        fts = _fts_query(query)
        if not fts:
            return []
        sql = (f"SELECT r.* FROM resources_fts f JOIN resources r ON r.id = f.id "
               f"WHERE resources_fts MATCH ?" + (" AND r.module_id = ?" if module_id else "") +
               f" ORDER BY {_BM25} LIMIT ?")
        params: list = [fts] + ([module_id] if module_id else []) + [limit]
        with self._lock:
            try:
                rows = self._db.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                return []
        return [self._resource(r) for r in rows]

    def match_snippet(self, resource_id: str, query: str, tokens: int = 14) -> str:
        """Short excerpt of the file contents around the search match ("" if none)."""
        fts = _fts_query(query)
        if not fts:
            return ""
        with self._lock:
            try:
                row = self._db.execute(
                    "SELECT snippet(resources_fts, 7, '', '', '\u2026', ?) FROM resources_fts "
                    "WHERE resources_fts MATCH ? AND id = ?", (tokens, fts, resource_id)).fetchone()
            except sqlite3.OperationalError:
                return ""
        return (row[0] or "").strip() if row else ""

    def all_keywords(self) -> list[str]:
        """Every keyword in use, most frequent first (for autocompletion)."""
        counts: dict[str, int] = {}
        display: dict[str, str] = {}
        with self._lock:
            rows = self._db.execute("SELECT keywords FROM resources").fetchall()
        for row in rows:
            try:
                for kw in json.loads(row[0] or "[]"):
                    counts[kw.lower()] = counts.get(kw.lower(), 0) + 1
                    display.setdefault(kw.lower(), kw)
            except ValueError:
                continue
        return [display[k] for k, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    # ================================================================== classwork
    @staticmethod
    def _classwork(row: sqlite3.Row) -> ClassworkEntry:
        return ClassworkEntry(
            id=row["id"], module_id=row["module_id"], topic_id=row["topic_id"], date=row["date"], title=row["title"],
            description=row["description"], facilitator=row["facilitator"], attachment=row["attachment"],
            attachment_name=row["attachment_name"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def _insert_classwork(self, c: ClassworkEntry) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO classwork (id, module_id, topic_id, date, title, description, facilitator, "
            "attachment, attachment_name, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (c.id, c.module_id, c.topic_id, c.date, c.title, c.description, c.facilitator, c.attachment,
             c.attachment_name, c.created_at, c.updated_at),
        )

    def classwork(self, module_id: str | None = None, topic_id: str | None = None) -> list[ClassworkEntry]:
        where, params = [], []
        if module_id:
            where.append("module_id = ?")
            params.append(module_id)
        if topic_id:
            where.append("topic_id = ?")
            params.append(topic_id)
        sql = ("SELECT * FROM classwork" + (" WHERE " + " AND ".join(where) if where else "")
               + " ORDER BY date DESC, created_at DESC")
        with self._lock:
            rows = self._db.execute(sql, params).fetchall()
        return [self._classwork(r) for r in rows]

    def classwork_entry(self, entry_id: str) -> ClassworkEntry | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM classwork WHERE id = ?", (entry_id,)).fetchone()
        return self._classwork(row) if row else None

    def _store_attachment(self, module: Module, date: str, source: Path | str) -> tuple[str, str]:
        src = Path(source)
        if not src.is_file():
            raise LibraryError("The attachment could not be found.")
        name = safe_filename(src.name)
        dest = self._unique_path(self.classwork_dir / module.id, f"{date} {name}")
        shutil.copy2(src, dest)
        return self.rel(dest), name

    def _remove_attachment(self, c: ClassworkEntry) -> list[str]:
        if not c.attachment:
            return []
        try:
            path = self.abs(c.attachment)
        except LibraryError:
            return []
        if path.exists():
            path.unlink()
        return [c.attachment]

    @staticmethod
    def _check_date(date: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date or ""):
            raise LibraryError("Enter the date as YYYY-MM-DD.")
        return date

    def add_classwork(self, module_id: str, date: str, title: str, description: str = "",
                      topic_id: str | None = None, facilitator: str = "",
                      attachment: Path | str | None = None) -> ClassworkEntry:
        m = self.module(module_id)
        if m is None:
            raise LibraryError("Choose a module for this classwork.")
        title = title.strip()
        if not title:
            raise LibraryError("Give the classwork a title.")
        date = self._check_date(date)
        if topic_id and m.topic(topic_id) is None:
            topic_id = None
        att, att_name = self._store_attachment(m, date, attachment) if attachment else (None, None)
        now = time.time()
        c = ClassworkEntry(_new_id(), m.id, topic_id, date, title, description.strip(), facilitator.strip(),
                           att, att_name, now, now)
        with self._lock:
            self._insert_classwork(c)
            self._db.commit()
        touched = ([att] if att else []) + self._export("classwork")
        self._done("classwork", f"Log classwork: {title} ({m.name}, {date})", touched)
        return c

    def update_classwork(self, entry_id: str, *, module_id: str | None = None, topic_id: str | None = "",
                         date: str | None = None, title: str | None = None, description: str | None = None,
                         attachment: Path | str | None = None, remove_attachment: bool = False) -> ClassworkEntry:
        """Update fields; `topic_id=""` keeps the current topic, `None` clears it."""
        c = self.classwork_entry(entry_id)
        if c is None:
            raise LibraryError("Classwork entry not found.")
        m = self.module(module_id or c.module_id)
        if m is None:
            raise LibraryError("Choose a module for this classwork.")
        touched: list[str] = []
        if topic_id != "":
            c.topic_id = topic_id if topic_id and m.topic(topic_id) else None
        elif m.id != c.module_id:
            c.topic_id = None
        c.module_id = m.id
        if date is not None:
            c.date = self._check_date(date)
        if title is not None:
            if not title.strip():
                raise LibraryError("Give the classwork a title.")
            c.title = title.strip()
        if description is not None:
            c.description = description.strip()
        if remove_attachment or attachment is not None:
            touched += self._remove_attachment(c)
            c.attachment = c.attachment_name = None
        if attachment is not None:
            c.attachment, c.attachment_name = self._store_attachment(m, c.date, attachment)
            touched.append(c.attachment)
        c.updated_at = time.time()
        with self._lock:
            self._insert_classwork(c)
            self._db.commit()
        touched += self._export("classwork")
        self._done("classwork", f"Update classwork: {c.title} ({m.name}, {c.date})", touched)
        return c

    def delete_classwork(self, entry_id: str) -> None:
        c = self.classwork_entry(entry_id)
        if c is None:
            return
        touched = self._remove_attachment(c)
        with self._lock:
            self._db.execute("DELETE FROM classwork WHERE id = ?", (c.id,))
            self._db.commit()
        touched += self._export("classwork")
        self._done("classwork", f"Delete classwork: {c.title} ({c.date})", touched)

    def search_classwork(self, query: str, module_id: str | None = None) -> list[ClassworkEntry]:
        tokens = re.findall(r"\w+", query.lower())
        if not tokens:
            return []
        names = {m.id: m for m in self.modules()}
        out = []
        for c in self.classwork(module_id=module_id):
            m = names.get(c.module_id)
            topic = m.topic(c.topic_id).name if m and m.topic(c.topic_id) else ""
            hay = " ".join([c.title, c.description, c.facilitator, c.date, c.attachment_name or "",
                            m.name if m else "", topic]).lower()
            if all(t in hay for t in tokens):
                out.append(c)
        return out
