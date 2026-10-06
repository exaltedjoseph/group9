"""Plain data objects shared by the core and the UI."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath


@dataclass
class Topic:
    id: str
    name: str


@dataclass
class Module:
    id: str                 # stable slug, also the folder name under resources/
    name: str
    description: str = ""
    color: str = "blue"     # Apple system color name
    topics: list[Topic] = field(default_factory=list)

    def topic(self, topic_id: str | None) -> Topic | None:
        return next((t for t in self.topics if t.id == topic_id), None)

    def to_json(self) -> dict:
        return {"id": self.id, "name": self.name, "description": self.description, "color": self.color,
                "topics": [{"id": t.id, "name": t.name} for t in self.topics]}

    @classmethod
    def from_json(cls, d: dict) -> "Module":
        return cls(id=d["id"], name=d.get("name", d["id"]), description=d.get("description", ""),
                   color=d.get("color", "blue"),
                   topics=[Topic(t["id"], t.get("name", t["id"])) for t in d.get("topics", [])])


@dataclass
class Resource:
    id: str
    title: str
    module_id: str
    topic_id: str | None
    kind: str               # see constants.RESOURCE_KINDS
    description: str
    keywords: list[str]
    filename: str           # original file name shown to users
    path: str               # posix path relative to the library root
    size: int
    sha256: str
    uploader: str
    created_at: float
    updated_at: float
    ai_suggested: bool = False

    @property
    def ext(self) -> str:
        return PurePosixPath(self.filename).suffix.lower().lstrip(".")

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "Resource":
        return cls(
            id=d["id"], title=d.get("title", ""), module_id=d.get("module_id", ""), topic_id=d.get("topic_id"),
            kind=d.get("kind", "other"), description=d.get("description", ""),
            keywords=list(d.get("keywords", [])), filename=d.get("filename", ""), path=d.get("path", ""),
            size=int(d.get("size", 0)), sha256=d.get("sha256", ""), uploader=d.get("uploader", ""),
            created_at=float(d.get("created_at", 0)), updated_at=float(d.get("updated_at", 0)),
            ai_suggested=bool(d.get("ai_suggested", False)),
        )


@dataclass
class ClassworkEntry:
    id: str
    module_id: str
    topic_id: str | None
    date: str               # ISO date, yyyy-mm-dd
    title: str
    description: str
    facilitator: str
    attachment: str | None  # posix path relative to the library root
    attachment_name: str | None
    created_at: float
    updated_at: float

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict) -> "ClassworkEntry":
        return cls(
            id=d["id"], module_id=d.get("module_id", ""), topic_id=d.get("topic_id"), date=d.get("date", ""),
            title=d.get("title", ""), description=d.get("description", ""), facilitator=d.get("facilitator", ""),
            attachment=d.get("attachment"), attachment_name=d.get("attachment_name"),
            created_at=float(d.get("created_at", 0)), updated_at=float(d.get("updated_at", 0)),
        )


@dataclass
class Suggestion:
    """AI suggestion for a resource; ids always refer to the existing syllabus."""
    module_id: str | None
    topic_id: str | None
    keywords: list[str]
    title: str = ""
    description: str = ""
    kind: str | None = None
    confidence: float = 0.0
    reason: str = ""


@dataclass
class Commit:
    hash: str
    short_hash: str
    author: str
    timestamp: float
    message: str
