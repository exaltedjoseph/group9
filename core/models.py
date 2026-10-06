"""Plain data objects shared by the core and the UI."""
# TODO(branch2): implement the data layer and library browsing.
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath

@dataclass
class Topic:
    id: str
    name: str

@dataclass
class Module:
    id: str
    name: str
    description: str = ''
    color: str = 'blue'
    topics: list[Topic] = field(default_factory=list)

    def topic(self, topic_id: str | None) -> Topic | None:
        ...

    def to_json(self) -> dict:
        ...

    @classmethod
    def from_json(cls, d: dict) -> 'Module':
        ...

@dataclass
class Resource:
    id: str
    title: str
    module_id: str
    topic_id: str | None
    kind: str
    description: str
    keywords: list[str]
    filename: str
    path: str
    size: int
    sha256: str
    uploader: str
    created_at: float
    updated_at: float
    ai_suggested: bool = False

    @property
    def ext(self) -> str:
        ...

    def to_json(self) -> dict:
        ...

    @classmethod
    def from_json(cls, d: dict) -> 'Resource':
        ...

@dataclass
class ClassworkEntry:
    id: str
    module_id: str
    topic_id: str | None
    date: str
    title: str
    description: str
    facilitator: str
    attachment: str | None
    attachment_name: str | None
    created_at: float
    updated_at: float

    def to_json(self) -> dict:
        ...

    @classmethod
    def from_json(cls, d: dict) -> 'ClassworkEntry':
        ...

@dataclass
class Suggestion:
    """AI suggestion for a resource; ids always refer to the existing syllabus."""
    module_id: str | None
    topic_id: str | None
    keywords: list[str]
    title: str = ''
    description: str = ''
    kind: str | None = None
    confidence: float = 0.0
    reason: str = ''

@dataclass
class Commit:
    hash: str
    short_hash: str
    author: str
    timestamp: float
    message: str
