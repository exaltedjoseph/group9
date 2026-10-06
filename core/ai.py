"""Gemini-powered suggestions (module, topic, keywords) for uploaded resources."""
# TODO(branch4): implement the Gemini AI integration and Assistant.
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
except Exception:
    genai = errors = types = None
MAX_EXCERPT_CHARS = 24000
MAX_KNOWN_KEYWORDS = 60
MAX_INLINE_BYTES = 15 * 1000 * 1000
MAX_KEYWORDS = 8
MAX_KEYWORD_CHARS = 40
SUGGEST_TIMEOUT_MS = 60000
KEY_CHECK_TIMEOUT_MS = 15000
INLINE_MIME_TYPES = {'application/pdf', 'image/png', 'image/jpeg', 'image/webp', 'image/heic', 'image/heif'}
MSG_KEY_REJECTED = 'Your Gemini API key was rejected. Check it in Settings.'
MSG_NO_KEY = 'Add a Gemini API key in Settings to get suggestions.'
MSG_QUOTA = 'You’ve reached your Gemini rate limit or quota. Wait a moment and try again.'
MSG_MODEL = 'The selected model isn’t available for your key. Choose another model in Settings.'
MSG_SERVER = 'Gemini is temporarily unavailable. Try again in a moment.'
MSG_OFFLINE = 'Can’t reach Gemini. Check your internet connection.'
MSG_TIMEOUT = 'Gemini took too long to respond. Try again in a moment.'
MSG_BLOCKED = 'Gemini declined to analyze this file. Fill in the details yourself.'
MSG_EMPTY = 'Gemini didn’t return a suggestion. Try again.'
MSG_UNREADABLE = 'Gemini’s reply couldn’t be understood. Try again.'
MSG_REGION = 'Gemini isn’t available in your region for this key.'
SYSTEM_INSTRUCTION = 'You help a facilitator file training materials into an internship program\'s study library.\nGiven a syllabus and one uploaded file, suggest where the file belongs and how to tag it.\n\nRules:\n- module_id and topic_id must be copied exactly from the ids in the syllabus. Never invent ids.\n- topic_id must belong to the chosen module. Use null when no topic clearly fits.\n- Use null for module_id when nothing in the syllabus fits.\n- keywords: 3 to 8 short search keywords (1-3 words each), lowercase unless a proper noun or acronym (e.g. "Python", "SQL", "pandas"). Reuse the known keywords when they fit. No hashtags.\n- title: if the facilitator already gave a title, return it unchanged; otherwise write a short, clear title in sentence case.\n- description: if the facilitator already gave one, return it unchanged; otherwise write one or two sentences describing what the material covers.\n- kind: notes, slides, exercise, reference or other.\n- confidence: 0 to 1, how sure you are about the module and topic.\n- reason: one short sentence explaining the choice.\nReply with JSON only.'
RESPONSE_SCHEMA: dict = {'type': 'object', 'properties': {'module_id': {'type': ['string', 'null'], 'description': 'Id of the best matching module, or null.'}, 'topic_id': {'type': ['string', 'null'], 'description': 'Id of a topic inside that module, or null.'}, 'keywords': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 0, 'maxItems': MAX_KEYWORDS, 'description': '3-8 short search keywords.'}, 'title': {'type': 'string', 'description': 'Title for the resource.'}, 'description': {'type': 'string', 'description': 'One or two sentences about the material.'}, 'kind': {'type': 'string', 'enum': list(KIND_NAMES)}, 'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1}, 'reason': {'type': 'string', 'description': 'One short sentence.'}}, 'required': ['module_id', 'topic_id', 'keywords', 'title', 'description', 'kind', 'confidence', 'reason']}
_KIND_ALIASES = {'note': 'notes', 'handout': 'notes', 'slide': 'slides', 'presentation': 'slides', 'deck': 'slides', 'exercises': 'exercise', 'assignment': 'exercise', 'worksheet': 'exercise', 'lab': 'exercise', 'references': 'reference', 'documentation': 'reference', 'docs': 'reference', 'cheatsheet': 'reference'}
_KEY_PATTERN = re.compile('AIza[0-9A-Za-z_\\-]{20,}')

class SuggestionError(Exception):
    """A problem with a suggestion request whose message is safe to show."""

def build_prompt(modules: Sequence[Module], file_name: str='', title: str='', description: str='', text_excerpt: str='', known_keywords: Iterable[str]=(), has_attachment: bool=False) -> str:
    """The user prompt for a suggestion request."""
    ...

def _dedupe(items: Iterable[str]) -> list[str]:
    ...

def _load_json(text: str) -> dict:
    ...

def _text_value(value) -> str:
    ...

def _match(value: str, items: Sequence[Module] | Sequence[Topic]):
    ...

def clean_keywords(raw, known_keywords: Iterable[str]=()) -> list[str]:
    """Split, strip '#', dedupe and cap keywords; reuses the casing of known keywords."""
    ...

def _confidence(value) -> float:
    ...

def _kind(value) -> str | None:
    ...

def parse_suggestion(text: str, modules: Sequence[Module], title: str='', description: str='', known_keywords: Iterable[str]=()) -> Suggestion:
    """Turn the model's JSON reply into a `Suggestion` whose ids exist in `modules`.

    Raises `SuggestionError` when the reply isn't usable JSON.
    """
    ...

def _redact(text: str, api_key: str='') -> str:
    ...

def _chain(exc: BaseException) -> list[BaseException]:
    ...

def _api_error_message(exc) -> str:
    ...

def _is_network_error(exc: BaseException) -> str | None:
    ...

def friendly_error(exc: BaseException, api_key: str='') -> str:
    """A short, user-facing message for any exception raised while talking to Gemini."""
    ...

def _make_client(api_key: str, timeout_ms: int):
    ...

def _close(client) -> None:
    ...

def _thinking_config(model: str):
    ...

def _response_text(response) -> str:
    ...

def _is_bad_request(exc: Exception) -> bool:
    ...

class SuggestWorker(QThread):
    """Asks Gemini where a file belongs; emits `suggested(Suggestion)` or `failed(message)`."""
    suggested = Signal(object)
    failed = Signal(str)

    def __init__(self, api_key: str, model: str, modules: list[Module], file_path: Path | None, title: str='', description: str='', text_excerpt: str='', known_keywords: Iterable[str]=(), parent=None) -> None:
        ...

    def run(self) -> None:
        ...

    def _inline_part(self):
        ...

    def suggest(self) -> Suggestion:
        """Run the request synchronously (used by `run()`)."""
        ...

class KeyCheckWorker(QThread):
    """Cheaply validates an API key; emits `result(ok, message)`."""
    result = Signal(bool, str)

    def __init__(self, api_key: str, model: str | None=None, parent=None) -> None:
        ...

    def run(self) -> None:
        ...

    def check(self) -> tuple[bool, str]:
        ...
