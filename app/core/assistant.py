"""Gemini study assistant: tutor prompt, library retrieval and a streaming chat worker."""
from __future__ import annotations

import re
from datetime import date
from typing import Iterable, Sequence

from PySide6.QtCore import QThread, Signal

from ..constants import DEFAULT_MODEL, KIND_NAMES, MODE_FACILITATOR
from .ai import SuggestionError, _close, _is_bad_request, _make_client, _thinking_config, friendly_error
from .library import Library
from .models import Resource

try:
    from google.genai import types
except Exception:  # pragma: no cover - the SDK is a hard requirement of the app
    types = None  # type: ignore[assignment]

MAX_CONTEXT_CHARS = 20_000
MAX_ATTACHED_CHARS = 16_000
SNIPPET_CHARS = 1_500
MAX_SOURCES = 3
MAX_HISTORY_MESSAGES = 20
MAX_PROMPT_RESOURCES = 150
MAX_PROMPT_CLASSWORK = 8
CHAT_TIMEOUT_MS = 120_000

MSG_NO_KEY = "Add a Gemini API key in Settings to use the Assistant."
MSG_CHAT_BLOCKED = "Gemini declined to answer this. Try rephrasing your question."
MSG_CHAT_EMPTY = "Gemini didn\u2019t return an answer. Try again."

_BLOCKED_REASONS = ("SAFETY", "PROHIBITED", "BLOCKLIST", "SPII", "RECITATION")

TUTOR_RULES = """\
You are the Study Assistant inside \u201cStudy Library\u201d, a desktop app for an internship training program. \
You are a friendly, patient tutor who explains study materials and concepts.

How to answer:
- Explain clearly and simply, step by step, with short concrete examples (code examples for programming topics).
- Use Markdown: short paragraphs, bullet lists, **bold** for key terms, headings only for longer answers, \
and fenced code blocks with a language tag.
- Keep answers focused on the question. Prefer a concise answer and offer to go deeper.
- Ground your answers in the library. When a resource listed below is relevant, mention it by its exact \
title in quotes so the user can open it.
- When library material is included with a message, base your answer on it and say which resource it came from.
- If something isn\u2019t covered by the library, say so plainly (for example \u201cThis isn\u2019t in your \
library yet\u201d), then give a general explanation if it helps.
- Never invent resources, titles, file names, modules or classwork that aren\u2019t listed below.
- For quizzes, ask one question at a time and wait for the answer before giving feedback.
- Answer in the language the user writes in."""

_AUDIENCE = {
    MODE_FACILITATOR: "You are talking with a facilitator who runs the program. Help them explain concepts, "
                      "prepare examples, exercises and quizzes for their interns, and plan sessions.",
    "intern": "You are talking with an intern in the program. Help them understand the material, practise, "
              "and plan their studies. Encourage them and check their understanding.",
}

_STOPWORDS = set("""
a about above after again all also am an and any are as at be because been before being below between both but
by can could did do does doing down during each few for from further had has have having he her here hers him
his how i if in into is it its itself just let lets like me more most my myself no nor not now of off on once
only or other our ours out over own please same she should so some such than that the their them then there
these they this those through to too under until up very was we were what when where which while who whom why
will with would you your yours yourself
explain explanation simply simple quiz summarize summarise summary help make plan week study topic topics
resource resources library tell give show example examples using use work works mean means thing things
""".split())


# ====================================================================== system prompt
def _resource_line(library: Library, r: Resource) -> str:
    where = library.module_name(r.module_id)
    topic = library.topic_name(r.module_id, r.topic_id)
    if topic:
        where += f" \u203a {topic}"
    line = f"- \u201c{r.title}\u201d \u2014 {where} \u00b7 {KIND_NAMES.get(r.kind, 'Other')}"
    if r.keywords:
        line += " \u00b7 keywords: " + ", ".join(r.keywords[:8])
    return line


def build_system_prompt(library: Library, mode: str = "intern", today: date | None = None) -> str:
    """The tutor's system instruction: rules, audience, syllabus and a compact resource list."""
    today = today or date.today()
    lines = [TUTOR_RULES, "", _AUDIENCE.get(mode, _AUDIENCE["intern"]),
             f"Today is {today.strftime('%A')}, {today.isoformat()}."]
    try:
        modules = library.modules()
        resources = library.resources(sort="title")
        classwork = library.classwork()[:MAX_PROMPT_CLASSWORK]
    except Exception:
        modules, resources, classwork = [], [], []

    lines += ["", "## Syllabus"]
    if not modules:
        lines.append("(no modules yet)")
    for m in modules:
        desc = f" \u2014 {m.description.strip()}" if m.description.strip() else ""
        lines.append(f"- {m.name}{desc}")
        if m.topics:
            lines.append("  Topics: " + "; ".join(t.name for t in m.topics))

    lines += ["", "## Resources in the library (title \u2014 module \u203a topic \u00b7 type \u00b7 keywords)"]
    if not resources:
        lines.append("(the library has no resources yet)")
    for r in resources[:MAX_PROMPT_RESOURCES]:
        lines.append(_resource_line(library, r))
    if len(resources) > MAX_PROMPT_RESOURCES:
        lines.append(f"(\u2026 and {len(resources) - MAX_PROMPT_RESOURCES} more)")

    if classwork:
        lines += ["", "## Recent classwork sessions"]
        for c in classwork:
            topic = library.topic_name(c.module_id, c.topic_id)
            where = library.module_name(c.module_id) + (f" \u203a {topic}" if topic else "")
            lines.append(f"- {c.date}: {c.title} ({where})")
    return "\n".join(lines)


# ====================================================================== context
def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n[\u2026 truncated]"


def _metadata(library: Library, r: Resource) -> list[str]:
    topic = library.topic_name(r.module_id, r.topic_id)
    lines = [f"Title: {r.title}", f"Module: {library.module_name(r.module_id)}"]
    if topic:
        lines.append(f"Topic: {topic}")
    lines.append(f"Type: {KIND_NAMES.get(r.kind, 'Other')}")
    if r.keywords:
        lines.append("Keywords: " + ", ".join(r.keywords))
    if r.description:
        lines.append(f"Description: {r.description}")
    return lines


def _content(library: Library, r: Resource) -> str:
    try:
        return library.content_text(r) or ""
    except Exception:
        return ""


def resource_context(library: Library, resource_id: str, max_chars: int = MAX_ATTACHED_CHARS) -> tuple[str, str]:
    """(label, text) describing one resource for the model; ("", "") if it doesn't exist."""
    try:
        r = library.resource(resource_id)
    except Exception:
        r = None
    if r is None:
        return "", ""
    lines = [f"### Attached resource: \u201c{r.title}\u201d", *_metadata(library, r), ""]
    text = _content(library, r)
    if text.strip():
        lines += ["Content:", _truncate(text, max_chars)]
    else:
        lines.append("(No text could be extracted from this file; rely on the details above.)")
    return r.title, "\n".join(lines)


def query_terms(query: str) -> list[str]:
    """Meaningful search words from a chat message."""
    out: list[str] = []
    for token in re.findall(r"\w+", (query or "").lower(), flags=re.UNICODE):
        if len(token) < 2 or token in _STOPWORDS or token.isdigit():
            continue
        if token not in out:
            out.append(token)
    return out[:8]


def retrieve(library: Library, query: str, limit: int = MAX_SOURCES, exclude: Iterable[str] = ()) -> list[Resource]:
    """Resources most relevant to a chat message (all-terms matches first, then the best partial matches)."""
    terms = query_terms(query)
    skip = set(exclude)
    if not terms or limit <= 0:
        return []
    found: dict[str, Resource] = {}
    order: list[str] = []
    try:
        for r in library.search(" ".join(terms), limit=limit * 2):
            if r.id not in skip and r.id not in found:
                found[r.id] = r
                order.append(r.id)
        if len(order) < limit:
            scores: dict[str, float] = {}
            hits: dict[str, int] = {}
            for term in terms:
                for rank, r in enumerate(library.search(term, limit=20)):
                    if r.id in skip or r.id in found:
                        continue
                    scores[r.id] = scores.get(r.id, 0.0) + 1.0 / (rank + 1)
                    hits[r.id] = hits.get(r.id, 0) + 1
                    found.setdefault(r.id, r)
            need = max(1, -(-len(terms) // 3))
            partial = sorted((i for i in scores if hits[i] >= need), key=lambda i: (-hits[i], -scores[i]))
            order += partial
    except Exception:
        return [found[i] for i in order[:limit]]
    return [found[i] for i in order[:limit]]


def _snippet(text: str, terms: Sequence[str], chars: int) -> str:
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    if len(text) <= chars:
        return text
    low = text.lower()
    positions = [p for p in (low.find(t) for t in terms) if p >= 0]
    start = max(0, min(positions) - chars // 4) if positions else 0
    piece = text[start:start + chars].strip()
    return ("\u2026" if start else "") + piece + "\u2026"


def retrieval_context(library: Library, query: str, limit: int = MAX_SOURCES, exclude: Iterable[str] = (),
                      snippet_chars: int = SNIPPET_CHARS) -> tuple[str, list[str]]:
    """(context text, resource ids) with short excerpts of the resources relevant to `query`."""
    hits = retrieve(library, query, limit, exclude)
    if not hits:
        return "", []
    terms = query_terms(query)
    blocks = []
    for r in hits:
        lines = [f"### Library resource: \u201c{r.title}\u201d", *_metadata(library, r)]
        excerpt = _snippet(_content(library, r), terms, snippet_chars)
        if excerpt:
            lines += ["Excerpt:", excerpt]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks), [r.id for r in hits]


def build_user_turn(message: str, context: str = "") -> str:
    """The text sent for the user's turn, with library material prepended."""
    context = _truncate(context, MAX_CONTEXT_CHARS)
    if not context:
        return message
    return ("Material from the study library that may help (use it when relevant and say which resource "
            "you used):\n<library_context>\n" + context + "\n</library_context>\n\nMy message:\n" + message)


def trim_history(history: Sequence[tuple[str, str]], limit: int = MAX_HISTORY_MESSAGES) -> list[tuple[str, str]]:
    """The most recent messages, starting with a user turn and with valid roles only."""
    items = [(role, text) for role, text in history if role in ("user", "model") and (text or "").strip()]
    items = items[-limit:]
    while items and items[0][0] != "user":
        items.pop(0)
    return items


def build_contents(history: Sequence[tuple[str, str]], message: str, context: str = "") -> list:
    contents = [types.Content(role=role, parts=[types.Part.from_text(text=text)])
                for role, text in trim_history(history)]
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=build_user_turn(message, context))]))
    return contents


# ====================================================================== streaming
def _chunk_blocked(chunk) -> bool:
    feedback = getattr(chunk, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        return True
    for cand in getattr(chunk, "candidates", None) or []:
        reason = str(getattr(cand, "finish_reason", "") or "").upper()
        if any(r in reason for r in _BLOCKED_REASONS):
            return True
    return False


def chunk_text(chunk) -> str:
    """Visible text of a streamed chunk (thought parts are skipped)."""
    candidates = getattr(chunk, "candidates", None)
    if candidates:
        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None)
        if parts is not None:
            return "".join(p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False))
    try:
        return str(getattr(chunk, "text", "") or "")
    except Exception:
        return ""


class ChatWorker(QThread):
    """Streams one tutor reply: `chunk(text)` per piece, then `finished_ok(full)` or `failed(message)`."""

    chunk = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, api_key: str, model: str, system_prompt: str, history: Sequence[tuple[str, str]],
                 message: str, context: str = "", parent=None) -> None:
        super().__init__(parent)
        self._api_key = (api_key or "").strip()
        self._model = (model or DEFAULT_MODEL).strip()
        self._system_prompt = system_prompt or ""
        self._history = list(history)
        self._message = message or ""
        self._context = context or ""
        self._cancelled = False
        self._emitted = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        try:
            text = self.stream()
        except Exception as exc:
            if not self._cancelled:
                self.failed.emit(friendly_error(exc, self._api_key))
            return
        if not self._cancelled:
            self.finished_ok.emit(text)

    def _config(self, thinking: bool):
        return types.GenerateContentConfig(system_instruction=self._system_prompt,
                                           thinking_config=_thinking_config(self._model) if thinking else None)

    def _stream_once(self, client, contents, config, parts: list[str]) -> bool:
        blocked = False
        stream = client.models.generate_content_stream(model=self._model, contents=contents, config=config)
        try:
            for chunk in stream:
                if self._cancelled:
                    break
                blocked = blocked or _chunk_blocked(chunk)
                piece = chunk_text(chunk)
                if piece:
                    parts.append(piece)
                    self._emitted = True
                    self.chunk.emit(piece)
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        return blocked

    def stream(self) -> str:
        """Run the request synchronously (used by `run()`); returns the full reply."""
        if not self._api_key:
            raise SuggestionError(MSG_NO_KEY)
        if types is None:
            raise SuggestionError("The Gemini SDK (google-genai) isn\u2019t installed.")
        contents = build_contents(self._history, self._message, self._context)
        parts: list[str] = []
        client = _make_client(self._api_key, CHAT_TIMEOUT_MS)
        try:
            thinking = _thinking_config(self._model) is not None
            try:
                blocked = self._stream_once(client, contents, self._config(thinking), parts)
            except Exception as exc:
                if not thinking or self._emitted or not _is_bad_request(exc):
                    raise
                blocked = self._stream_once(client, contents, self._config(False), parts)
        finally:
            _close(client)
        text = "".join(parts)
        if not text.strip() and not self._cancelled:
            raise SuggestionError(MSG_CHAT_BLOCKED if blocked else MSG_CHAT_EMPTY)
        return text
