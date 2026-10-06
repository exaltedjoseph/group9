"""Gemini-powered suggestions (module, topic, keywords) for uploaded resources."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Sequence

from PySide6.QtCore import QThread, Signal

from ..constants import DEFAULT_MODEL, KIND_NAMES
from .extract import extract_text, guess_mime
from .library import slugify
from .models import Module, Suggestion, Topic

try:
    from google import genai
    from google.genai import errors, types
except Exception:  # pragma: no cover - the SDK is a hard requirement of the app
    genai = errors = types = None  # type: ignore[assignment]

MAX_EXCERPT_CHARS = 24_000
MAX_KNOWN_KEYWORDS = 60
MAX_INLINE_BYTES = 15 * 1000 * 1000
MAX_KEYWORDS = 8
MAX_KEYWORD_CHARS = 40
SUGGEST_TIMEOUT_MS = 60_000
KEY_CHECK_TIMEOUT_MS = 15_000
INLINE_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"}

MSG_KEY_REJECTED = "Your Gemini API key was rejected. Check it in Settings."
MSG_NO_KEY = "Add a Gemini API key in Settings to get suggestions."
MSG_QUOTA = "You\u2019ve reached your Gemini rate limit or quota. Wait a moment and try again."
MSG_MODEL = "The selected model isn\u2019t available for your key. Choose another model in Settings."
MSG_SERVER = "Gemini is temporarily unavailable. Try again in a moment."
MSG_OFFLINE = "Can\u2019t reach Gemini. Check your internet connection."
MSG_TIMEOUT = "Gemini took too long to respond. Try again in a moment."
MSG_BLOCKED = "Gemini declined to analyze this file. Fill in the details yourself."
MSG_EMPTY = "Gemini didn\u2019t return a suggestion. Try again."
MSG_UNREADABLE = "Gemini\u2019s reply couldn\u2019t be understood. Try again."
MSG_REGION = "Gemini isn\u2019t available in your region for this key."

SYSTEM_INSTRUCTION = """\
You help a facilitator file training materials into an internship program's study library.
Given a syllabus and one uploaded file, suggest where the file belongs and how to tag it.

Rules:
- module_id and topic_id must be copied exactly from the ids in the syllabus. Never invent ids.
- topic_id must belong to the chosen module. Use null when no topic clearly fits.
- Use null for module_id when nothing in the syllabus fits.
- keywords: 3 to 8 short search keywords (1-3 words each), lowercase unless a proper noun or acronym \
(e.g. "Python", "SQL", "pandas"). Reuse the known keywords when they fit. No hashtags.
- title: if the facilitator already gave a title, return it unchanged; otherwise write a short, clear title \
in sentence case.
- description: if the facilitator already gave one, return it unchanged; otherwise write one or two sentences \
describing what the material covers.
- kind: notes, slides, exercise, reference or other.
- confidence: 0 to 1, how sure you are about the module and topic.
- reason: one short sentence explaining the choice.
Reply with JSON only."""

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "module_id": {"type": ["string", "null"], "description": "Id of the best matching module, or null."},
        "topic_id": {"type": ["string", "null"], "description": "Id of a topic inside that module, or null."},
        "keywords": {"type": "array", "items": {"type": "string"}, "minItems": 0, "maxItems": MAX_KEYWORDS,
                     "description": "3-8 short search keywords."},
        "title": {"type": "string", "description": "Title for the resource."},
        "description": {"type": "string", "description": "One or two sentences about the material."},
        "kind": {"type": "string", "enum": list(KIND_NAMES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string", "description": "One short sentence."},
    },
    "required": ["module_id", "topic_id", "keywords", "title", "description", "kind", "confidence", "reason"],
}

_KIND_ALIASES = {
    "note": "notes", "handout": "notes", "slide": "slides", "presentation": "slides", "deck": "slides",
    "exercises": "exercise", "assignment": "exercise", "worksheet": "exercise", "lab": "exercise",
    "references": "reference", "documentation": "reference", "docs": "reference", "cheatsheet": "reference",
}
_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_\-]{20,}")


class SuggestionError(Exception):
    """A problem with a suggestion request whose message is safe to show."""


# ====================================================================== prompt & parsing
def build_prompt(modules: Sequence[Module], file_name: str = "", title: str = "", description: str = "",
                 text_excerpt: str = "", known_keywords: Iterable[str] = (), has_attachment: bool = False) -> str:
    """The user prompt for a suggestion request."""
    lines = ["Syllabus (pick ids only from this list):"]
    if not modules:
        lines.append("(no modules yet; use null for module_id and topic_id)")
    for m in modules:
        desc = f" \u2014 {m.description.strip()}" if m.description.strip() else ""
        lines.append(f'- module_id "{m.id}": {m.name}{desc}')
        if m.topics:
            for t in m.topics:
                lines.append(f'    - topic_id "{t.id}": {t.name}')
        else:
            lines.append("    (no topics)")
    known = _dedupe(str(k).strip() for k in known_keywords)[:MAX_KNOWN_KEYWORDS]
    lines.append("")
    lines.append("Known keywords (reuse when they fit): " + (", ".join(known) if known else "(none yet)"))
    lines.append("")
    lines.append(f"File name: {file_name or '(unknown)'}")
    title, description = title.strip(), description.strip()
    lines.append(f"Facilitator\u2019s title: {title}" if title else
                 "Facilitator\u2019s title: (empty, suggest a short title)")
    lines.append(f"Facilitator\u2019s description: {description}" if description else
                 "Facilitator\u2019s description: (empty, suggest one or two sentences)")
    if has_attachment:
        lines.append("The file itself is attached.")
    excerpt = (text_excerpt or "").strip()
    if excerpt:
        if len(excerpt) > MAX_EXCERPT_CHARS:
            excerpt = excerpt[:MAX_EXCERPT_CHARS].rstrip() + "\n[\u2026 truncated]"
        lines += ["", "Text excerpt from the file:", '"""', excerpt, '"""']
    elif not has_attachment:
        lines += ["", "No text could be extracted from the file; rely on the file name and the details above."]
    return "\n".join(lines)


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for item in items:
        if item and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out


def _load_json(text: str) -> dict:
    raw = (text or "").strip()
    fence = re.search(r"```(?:json|JSON)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
    except ValueError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise SuggestionError(MSG_UNREADABLE) from None
        try:
            data = json.loads(raw[start:end + 1])
        except ValueError:
            raise SuggestionError(MSG_UNREADABLE) from None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        data = data[0]
    if not isinstance(data, dict):
        raise SuggestionError(MSG_UNREADABLE)
    return data


def _text_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        value = value.get("id") or value.get("name") or ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _match(value: str, items: Sequence[Module] | Sequence[Topic]):
    if not value or value.lower() in ("null", "none", "n/a"):
        return None
    low, slug = value.lower(), slugify(value, "")
    for rule in (lambda i: i.id == value, lambda i: i.id.lower() == low, lambda i: i.name.lower() == low,
                 lambda i: bool(slug) and (i.id == slug or slugify(i.name, "") == slug)):
        hit = next((i for i in items if rule(i)), None)
        if hit is not None:
            return hit
    return None


def clean_keywords(raw, known_keywords: Iterable[str] = ()) -> list[str]:
    """Split, strip '#', dedupe and cap keywords; reuses the casing of known keywords."""
    if raw is None:
        return []
    items = re.split(r"[,;\n]", raw) if isinstance(raw, str) else [str(k) for k in raw if k is not None]
    known = {k.lower(): k for k in known_keywords if isinstance(k, str)}
    out: list[str] = []
    for item in items:
        for part in re.split(r"[,;]", item):
            kw = re.sub(r"\s+", " ", part.replace("#", " ")).strip().strip("\"'.:").strip()
            if not kw:
                continue
            if len(kw) > MAX_KEYWORD_CHARS:
                kw = kw[:MAX_KEYWORD_CHARS].rsplit(" ", 1)[0].strip() or kw[:MAX_KEYWORD_CHARS]
            out.append(known.get(kw.lower(), kw))
    return _dedupe(out)[:MAX_KEYWORDS]


def _confidence(value) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.0
    if c != c:
        return 0.0
    return max(0.0, min(1.0, c))


def _kind(value) -> str | None:
    k = _text_value(value).lower()
    if k in KIND_NAMES:
        return k
    return _KIND_ALIASES.get(k)


def parse_suggestion(text: str, modules: Sequence[Module], title: str = "", description: str = "",
                     known_keywords: Iterable[str] = ()) -> Suggestion:
    """Turn the model's JSON reply into a `Suggestion` whose ids exist in `modules`.

    Raises `SuggestionError` when the reply isn't usable JSON.
    """
    data = _load_json(text)
    module_raw = _text_value(data.get("module_id", data.get("module")))
    topic_raw = _text_value(data.get("topic_id", data.get("topic")))
    module = _match(module_raw, modules)
    topic = _match(topic_raw, module.topics) if module else None
    if module is None and topic_raw and not module_raw:
        owners = [(m, t) for m in modules if (t := _match(topic_raw, m.topics)) is not None]
        if len(owners) == 1:
            module, topic = owners[0]

    title, description = title.strip(), description.strip()
    return Suggestion(
        module_id=module.id if module else None,
        topic_id=topic.id if topic else None,
        keywords=clean_keywords(data.get("keywords"), known_keywords),
        title=title or _text_value(data.get("title"))[:120],
        description=description or str(data.get("description") or "").strip()[:600],
        kind=_kind(data.get("kind")),
        confidence=_confidence(data.get("confidence")),
        reason=_text_value(data.get("reason"))[:240],
    )


# ====================================================================== errors
def _redact(text: str, api_key: str = "") -> str:
    if api_key:
        text = text.replace(api_key, "\u2022\u2022\u2022")
    return _KEY_PATTERN.sub("\u2022\u2022\u2022", text)


def _chain(exc: BaseException) -> list[BaseException]:
    out: list[BaseException] = []
    while exc is not None and exc not in out and len(out) < 8:
        out.append(exc)
        exc = exc.__cause__ or exc.__context__
    return out


def _api_error_message(exc) -> str:
    code = int(getattr(exc, "code", 0) or 0)
    status = str(getattr(exc, "status", "") or "").upper()
    detail = f"{getattr(exc, 'message', '') or ''} {getattr(exc, 'details', '') or ''}"
    low = detail.lower()
    if ("API_KEY_INVALID" in detail or "api key" in low and ("invalid" in low or "not valid" in low
                                                           or "expired" in low or "missing" in low)
            or code in (401, 403) or status in ("UNAUTHENTICATED", "PERMISSION_DENIED")):
        return MSG_KEY_REJECTED
    if code == 429 or status == "RESOURCE_EXHAUSTED":
        return MSG_QUOTA
    if code == 404 or status == "NOT_FOUND":
        return MSG_MODEL
    if code == 504 or status == "DEADLINE_EXCEEDED":
        return MSG_TIMEOUT
    if code >= 500:
        return MSG_SERVER
    if status == "FAILED_PRECONDITION" and "location" in low:
        return MSG_REGION
    summary = str(getattr(exc, "message", "") or status or code).strip().splitlines()[0][:160]
    return f"Gemini couldn\u2019t process this request ({summary})."


def _is_network_error(exc: BaseException) -> str | None:
    try:
        import httpx
    except Exception:  # pragma: no cover
        httpx = None
    if httpx is not None:
        if isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
            return MSG_TIMEOUT
        if isinstance(exc, httpx.TransportError):
            return MSG_OFFLINE
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return MSG_OFFLINE
    return None


def friendly_error(exc: BaseException, api_key: str = "") -> str:
    """A short, user-facing message for any exception raised while talking to Gemini."""
    for e in _chain(exc):
        if isinstance(e, SuggestionError):
            return _redact(str(e) or MSG_UNREADABLE, api_key)
        if errors is not None and isinstance(e, errors.APIError):
            return _redact(_api_error_message(e), api_key)
        network = _is_network_error(e)
        if network:
            return network
    first = (str(exc).strip().splitlines() or [""])[0][:160]
    summary = f"{type(exc).__name__}: {first}" if first else type(exc).__name__
    return _redact(f"Something went wrong while asking Gemini ({summary}).", api_key)


# ====================================================================== requests
def _make_client(api_key: str, timeout_ms: int):
    if genai is None:
        raise SuggestionError("The Gemini SDK (google-genai) isn\u2019t installed.")
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))


def _close(client) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _thinking_config(model: str):
    if model.startswith("gemini-3"):
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
    return None


def _response_text(response) -> str:
    feedback = getattr(response, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        raise SuggestionError(MSG_BLOCKED)
    candidates = getattr(response, "candidates", None)
    if candidates is not None and not candidates:
        raise SuggestionError(MSG_EMPTY)
    if candidates:
        reason = str(getattr(candidates[0], "finish_reason", "") or "").upper()
        if any(r in reason for r in ("SAFETY", "PROHIBITED", "BLOCKLIST", "SPII", "RECITATION")):
            raise SuggestionError(MSG_BLOCKED)
    try:
        text = response.text
    except Exception:
        text = None
    if not text or not str(text).strip():
        raise SuggestionError(MSG_EMPTY)
    return str(text)


def _is_bad_request(exc: Exception) -> bool:
    if errors is None or not isinstance(exc, errors.ClientError):
        return False
    return int(getattr(exc, "code", 0) or 0) == 400 and _api_error_message(exc) not in (MSG_KEY_REJECTED, MSG_REGION)


class SuggestWorker(QThread):
    """Asks Gemini where a file belongs; emits `suggested(Suggestion)` or `failed(message)`."""

    suggested = Signal(object)
    failed = Signal(str)

    def __init__(self, api_key: str, model: str, modules: list[Module], file_path: Path | None,
                 title: str = "", description: str = "", text_excerpt: str = "",
                 known_keywords: Iterable[str] = (), parent=None) -> None:
        super().__init__(parent)
        self._api_key = (api_key or "").strip()
        self._model = (model or DEFAULT_MODEL).strip()
        self._modules = list(modules)
        self._file_path = Path(file_path) if file_path else None
        self._title = title or ""
        self._description = description or ""
        self._excerpt = text_excerpt or ""
        self._known = [k for k in known_keywords if isinstance(k, str)]

    def run(self) -> None:
        try:
            suggestion = self.suggest()
        except Exception as exc:
            self.failed.emit(friendly_error(exc, self._api_key))
            return
        self.suggested.emit(suggestion)

    def _inline_part(self):
        path = self._file_path
        if path is None or not path.is_file():
            return None
        mime = guess_mime(path)
        try:
            if mime not in INLINE_MIME_TYPES or path.stat().st_size > MAX_INLINE_BYTES:
                return None
            data = path.read_bytes()
        except OSError:
            return None
        return types.Part.from_bytes(data=data, mime_type=mime)

    def suggest(self) -> Suggestion:
        """Run the request synchronously (used by `run()`)."""
        if not self._api_key:
            raise SuggestionError(MSG_NO_KEY)
        if genai is None:
            raise SuggestionError("The Gemini SDK (google-genai) isn\u2019t installed.")
        attachment = self._inline_part()
        excerpt = self._excerpt
        if not excerpt and attachment is None and self._file_path is not None:
            excerpt = extract_text(self._file_path, MAX_EXCERPT_CHARS)
        prompt = build_prompt(self._modules, self._file_path.name if self._file_path else "", self._title,
                              self._description, excerpt, self._known, has_attachment=attachment is not None)
        contents = [attachment, prompt] if attachment is not None else [prompt]
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_json_schema=RESPONSE_SCHEMA,
            thinking_config=_thinking_config(self._model),
        )
        client = _make_client(self._api_key, SUGGEST_TIMEOUT_MS)
        try:
            try:
                response = client.models.generate_content(model=self._model, contents=contents, config=config)
            except Exception as exc:
                if not _is_bad_request(exc):
                    raise
                fallback = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION,
                                                       response_mime_type="application/json")
                response = client.models.generate_content(model=self._model, contents=contents, config=fallback)
            text = _response_text(response)
        finally:
            _close(client)
        return parse_suggestion(text, self._modules, self._title, self._description, self._known)


class KeyCheckWorker(QThread):
    """Cheaply validates an API key; emits `result(ok, message)`."""

    result = Signal(bool, str)

    def __init__(self, api_key: str, model: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self._api_key = (api_key or "").strip()
        self._model = (model or "").strip()

    def run(self) -> None:
        try:
            ok, message = self.check()
        except Exception as exc:
            ok, message = False, friendly_error(exc, self._api_key)
        self.result.emit(ok, message)

    def check(self) -> tuple[bool, str]:
        if not self._api_key:
            return False, "Enter an API key."
        client = _make_client(self._api_key, KEY_CHECK_TIMEOUT_MS)
        try:
            if self._model:
                client.models.get(model=self._model)
            else:
                next(iter(client.models.list(config={"page_size": 1})), None)
        finally:
            _close(client)
        return True, "Connected"
