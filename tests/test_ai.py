from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors, types

from app.core import ai
from app.core.ai import (KeyCheckWorker, SuggestionError, SuggestWorker, build_prompt, clean_keywords,
                         friendly_error, parse_suggestion)
from app.core.models import Module, Suggestion, Topic

FAKE_KEY = "AIzaFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE123"

MODULES = [
    Module("python-fundamentals", "Python Fundamentals", "Core Python syntax.", "blue",
           [Topic("control-flow", "Control Flow"), Topic("functions", "Functions")]),
    Module("databases-and-sql", "Databases & SQL", "Relational data.", "green",
           [Topic("sql-queries", "SQL Queries"), Topic("python-and-sqlite", "Python & SQLite")]),
    Module("empty-module", "Empty Module", "", "gray", []),
]


def _reply(**overrides) -> str:
    data = {"module_id": "python-fundamentals", "topic_id": "control-flow", "keywords": ["loops", "python"],
            "title": "Loops", "description": "About loops.", "kind": "notes", "confidence": 0.9,
            "reason": "It covers loops."}
    data.update(overrides)
    return json.dumps(data)


# ---------------------------------------------------------------------- build_prompt
def test_build_prompt_lists_syllabus_and_inputs():
    prompt = build_prompt(MODULES, "loops.pdf", "My title", "", "for i in range(3): print(i)", ["loops", "Python"])
    assert 'module_id "python-fundamentals": Python Fundamentals' in prompt
    assert "Core Python syntax." in prompt
    assert 'topic_id "control-flow": Control Flow' in prompt
    assert 'topic_id "sql-queries": SQL Queries' in prompt
    assert "loops, Python" in prompt
    assert "File name: loops.pdf" in prompt
    assert "My title" in prompt
    assert "description: (empty" in prompt
    assert "for i in range(3)" in prompt


def test_build_prompt_truncates_excerpt_and_keywords():
    excerpt = "word " * 20_000
    known = [f"kw{i}" for i in range(200)] + ["KW1"]
    prompt = build_prompt(MODULES, "big.txt", text_excerpt=excerpt, known_keywords=known)
    assert len(prompt) < ai.MAX_EXCERPT_CHARS + 3000
    assert "truncated" in prompt
    assert "kw59" in prompt and "kw60," not in prompt and "kw61" not in prompt


def test_build_prompt_attachment_and_no_modules():
    prompt = build_prompt([], "photo.png", has_attachment=True)
    assert "no modules yet" in prompt and "attached" in prompt
    assert "No text could be extracted" not in prompt
    assert "No text could be extracted" in build_prompt(MODULES, "x.bin")


# ---------------------------------------------------------------------- parse_suggestion
def test_parse_valid():
    s = parse_suggestion(_reply(), MODULES)
    assert s == Suggestion("python-fundamentals", "control-flow", ["loops", "python"], "Loops", "About loops.",
                           "notes", 0.9, "It covers loops.")


def test_parse_code_fence_and_prose():
    s = parse_suggestion("```json\n" + _reply() + "\n```", MODULES)
    assert s.module_id == "python-fundamentals"
    s2 = parse_suggestion("Sure! Here you go: " + _reply(kind="slides") + " Hope it helps.", MODULES)
    assert s2.kind == "slides"


def test_parse_invalid_ids_become_none():
    s = parse_suggestion(_reply(module_id="made-up", topic_id="control-flow"), MODULES)
    assert s.module_id is None and s.topic_id is None
    s = parse_suggestion(_reply(module_id="python-fundamentals", topic_id="nonsense"), MODULES)
    assert s.module_id == "python-fundamentals" and s.topic_id is None
    s = parse_suggestion(_reply(module_id=None, topic_id=None), MODULES)
    assert s.module_id is None and s.topic_id is None


def test_parse_topic_from_other_module_dropped():
    s = parse_suggestion(_reply(module_id="python-fundamentals", topic_id="sql-queries"), MODULES)
    assert s.module_id == "python-fundamentals" and s.topic_id is None


def test_parse_module_and_topic_by_name_or_slug():
    s = parse_suggestion(_reply(module_id="databases & sql", topic_id="SQL Queries"), MODULES)
    assert (s.module_id, s.topic_id) == ("databases-and-sql", "sql-queries")
    s = parse_suggestion(_reply(module_id="Python-Fundamentals", topic_id="Control flow"), MODULES)
    assert (s.module_id, s.topic_id) == ("python-fundamentals", "control-flow")
    s = parse_suggestion(json.dumps({"module": "Databases and SQL", "topic": "python & sqlite"}), MODULES)
    assert (s.module_id, s.topic_id) == ("databases-and-sql", "python-and-sqlite")


def test_parse_infers_module_from_unique_topic():
    s = parse_suggestion(_reply(module_id=None, topic_id="sql-queries"), MODULES)
    assert (s.module_id, s.topic_id) == ("databases-and-sql", "sql-queries")


def test_parse_keywords_cleanup():
    raw = ["#Loops", "loops", "for, while", "  iteration  ", "", None, "x" * 60, "a; b", "c", "d", "e", "f"]
    s = parse_suggestion(_reply(keywords=raw), MODULES)
    assert s.keywords[:4] == ["Loops", "for", "while", "iteration"]
    assert len(s.keywords) == 8
    assert all(len(k) <= 40 and "#" not in k and "," not in k for k in s.keywords)
    assert parse_suggestion(_reply(keywords="sql, joins, #db"), MODULES).keywords == ["sql", "joins", "db"]
    assert parse_suggestion(_reply(keywords=None), MODULES).keywords == []


def test_clean_keywords_reuses_known_casing():
    assert clean_keywords(["python", "SQL"], known_keywords=["Python", "sql"]) == ["Python", "sql"]


@pytest.mark.parametrize("value, expected", [(1.7, 1.0), (-0.2, 0.0), ("0.4", 0.4), ("high", 0.0), (None, 0.0)])
def test_parse_confidence_clamped(value, expected):
    assert parse_suggestion(_reply(confidence=value), MODULES).confidence == expected


def test_parse_kind_and_echo_title():
    s = parse_suggestion(_reply(kind="Presentation"), MODULES)
    assert s.kind == "slides"
    assert parse_suggestion(_reply(kind="video"), MODULES).kind is None
    s = parse_suggestion(_reply(title="AI title", description="AI desc"), MODULES, title="Mine", description="")
    assert s.title == "Mine" and s.description == "AI desc"


@pytest.mark.parametrize("bad", ["", "not json at all", "{broken: json", "[1, 2]", "```json\n{oops\n```"])
def test_parse_malformed_raises(bad):
    with pytest.raises(SuggestionError):
        parse_suggestion(bad, MODULES)


def test_parse_list_wrapped_object():
    assert parse_suggestion("[" + _reply() + "]", MODULES).module_id == "python-fundamentals"


# ---------------------------------------------------------------------- friendly_error
def _api_error(cls, code, status, message, reason=None):
    body = {"error": {"code": code, "status": status, "message": message}}
    if reason:
        body["error"]["details"] = [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason}]
    return cls(code, body)


@pytest.mark.parametrize("exc, expected", [
    (_api_error(errors.ClientError, 400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.",
                "API_KEY_INVALID"), ai.MSG_KEY_REJECTED),
    (_api_error(errors.ClientError, 401, "UNAUTHENTICATED", "Missing credentials"), ai.MSG_KEY_REJECTED),
    (_api_error(errors.ClientError, 403, "PERMISSION_DENIED", "Denied"), ai.MSG_KEY_REJECTED),
    (_api_error(errors.ClientError, 429, "RESOURCE_EXHAUSTED", "Quota exceeded"), ai.MSG_QUOTA),
    (_api_error(errors.ClientError, 404, "NOT_FOUND", "models/x is not found"), ai.MSG_MODEL),
    (_api_error(errors.ServerError, 500, "INTERNAL", "boom"), ai.MSG_SERVER),
    (_api_error(errors.ServerError, 503, "UNAVAILABLE", "overloaded"), ai.MSG_SERVER),
    (httpx.ConnectError("getaddrinfo failed"), ai.MSG_OFFLINE),
    (httpx.ConnectTimeout("timed out"), ai.MSG_OFFLINE),
    (httpx.ReadTimeout("timed out"), ai.MSG_TIMEOUT),
    (OSError("network down"), ai.MSG_OFFLINE),
    (TimeoutError(), ai.MSG_OFFLINE),
    (SuggestionError(ai.MSG_BLOCKED), ai.MSG_BLOCKED),
])
def test_friendly_error_mapping(exc, expected):
    assert friendly_error(exc) == expected


def test_friendly_error_follows_cause_chain():
    try:
        try:
            raise httpx.ConnectError("no route")
        except httpx.ConnectError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as exc:
        assert friendly_error(exc) == ai.MSG_OFFLINE


def test_friendly_error_generic_is_short_and_redacted():
    msg = friendly_error(ValueError(f"bad thing with key {FAKE_KEY}\nTraceback line 2"))
    assert "ValueError" in msg and "bad thing" in msg
    assert FAKE_KEY not in msg and "Traceback" not in msg
    other = friendly_error(RuntimeError("secret-xyz leaked"), api_key="secret-xyz")
    assert "secret-xyz" not in other
    bad_request = friendly_error(_api_error(errors.ClientError, 400, "INVALID_ARGUMENT", "Bad schema field"))
    assert "Bad schema field" in bad_request


# ---------------------------------------------------------------------- workers (mocked client)
class FakeModels:
    def __init__(self, owner):
        self.owner = owner

    def generate_content(self, *, model, contents, config=None):
        self.owner.calls.append({"model": model, "contents": contents, "config": config})
        result = self.owner.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def get(self, *, model, config=None):
        self.owner.calls.append({"get": model})
        if self.owner.get_error:
            raise self.owner.get_error
        return SimpleNamespace(name=f"models/{model}")

    def list(self, *, config=None):
        self.owner.calls.append({"list": config})
        if self.owner.get_error:
            raise self.owner.get_error
        return iter([SimpleNamespace(name="models/a")])


class FakeGenai:
    def __init__(self):
        self.calls: list[dict] = []
        self.clients: list[dict] = []
        self.responses: list = []
        self.get_error: BaseException | None = None
        self.closed = 0

    def Client(self, *, api_key, http_options=None):  # noqa: N802 - mirrors genai.Client
        self.clients.append({"api_key": api_key, "http_options": http_options})
        fake = self

        class _Client:
            models = FakeModels(fake)

            def close(self):
                fake.closed += 1

        return _Client()


def _response(text, finish="STOP", block=None):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=finish)],
                           prompt_feedback=SimpleNamespace(block_reason=block) if block else None)


@pytest.fixture
def fake(monkeypatch):
    f = FakeGenai()
    monkeypatch.setattr(ai.genai, "Client", f.Client)
    return f


def _run(worker):
    out = {"ok": [], "err": []}
    worker.suggested.connect(out["ok"].append)
    worker.failed.connect(out["err"].append)
    worker.run()
    return out


def test_suggest_worker_text_file(fake, tmp_path):
    src = tmp_path / "loops.txt"
    src.write_text("A lesson about while loops", encoding="utf-8")
    fake.responses = [_response(_reply(module_id="Python Fundamentals", title="Ignored"))]
    w = SuggestWorker(FAKE_KEY, "gemini-3.8-flash", MODULES, src, title="Typed title", known_keywords=["Loops"])
    out = _run(w)
    assert out["err"] == []
    s = out["ok"][0]
    assert s.module_id == "python-fundamentals" and s.title == "Typed title" and s.keywords[0] == "Loops"
    call = fake.calls[0]
    assert call["model"] == "gemini-3.8-flash"
    assert len(call["contents"]) == 1 and "while loops" in call["contents"][0]
    cfg = call["config"]
    assert cfg.response_mime_type == "application/json" and cfg.response_json_schema == ai.RESPONSE_SCHEMA
    assert cfg.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert fake.clients[0]["api_key"] == FAKE_KEY
    assert fake.clients[0]["http_options"].timeout == ai.SUGGEST_TIMEOUT_MS
    assert fake.closed == 1


def test_suggest_worker_sends_images_inline(fake, tmp_path):
    img = tmp_path / "diagram.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    fake.responses = [_response(_reply())]
    out = _run(SuggestWorker(FAKE_KEY, "gemini-2.5-flash", MODULES, img))
    assert out["ok"] and not out["err"]
    contents = fake.calls[0]["contents"]
    assert isinstance(contents[0], types.Part)
    assert contents[0].inline_data.mime_type == "image/png"
    assert contents[0].inline_data.data.startswith(b"\x89PNG")
    assert "diagram.png" in contents[1] and "attached" in contents[1]
    assert fake.calls[0]["config"].thinking_config is None


def test_suggest_worker_large_pdf_sent_as_text_only(fake, tmp_path, monkeypatch):
    pdf = tmp_path / "huge.pdf"
    pdf.write_bytes(b"%PDF-1.4 tiny")
    monkeypatch.setattr(ai, "MAX_INLINE_BYTES", 5)
    fake.responses = [_response(_reply())]
    out = _run(SuggestWorker(FAKE_KEY, "gemini-3.8-flash", MODULES, pdf, text_excerpt="Excerpt given"))
    assert out["ok"]
    assert len(fake.calls[0]["contents"]) == 1 and "Excerpt given" in fake.calls[0]["contents"][0]


def test_suggest_worker_retries_bad_request_without_schema(fake, tmp_path):
    fake.responses = [_api_error(errors.ClientError, 400, "INVALID_ARGUMENT", "Unknown field thinking_level"),
                      _response("```json\n" + _reply() + "\n```")]
    out = _run(SuggestWorker(FAKE_KEY, "gemini-3.8-flash", MODULES, None, text_excerpt="loops"))
    assert out["ok"] and not out["err"]
    assert len(fake.calls) == 2
    retry_cfg = fake.calls[1]["config"]
    assert retry_cfg.response_json_schema is None and retry_cfg.thinking_config is None


@pytest.mark.parametrize("response_or_error, expected", [
    (_api_error(errors.ClientError, 400, "INVALID_ARGUMENT", "API key not valid", "API_KEY_INVALID"),
     ai.MSG_KEY_REJECTED),
    (_api_error(errors.ClientError, 429, "RESOURCE_EXHAUSTED", "quota"), ai.MSG_QUOTA),
    (httpx.ConnectError("offline"), ai.MSG_OFFLINE),
    (_response("not json"), ai.MSG_UNREADABLE),
    (_response(""), ai.MSG_EMPTY),
    (_response(None, finish="SAFETY"), ai.MSG_BLOCKED),
    (_response(None, block="SAFETY"), ai.MSG_BLOCKED),
])
def test_suggest_worker_failures(fake, response_or_error, expected):
    fake.responses = [response_or_error]
    out = _run(SuggestWorker(FAKE_KEY, "gemini-3.8-flash", MODULES, None, text_excerpt="x"))
    assert out["ok"] == [] and out["err"] == [expected]
    assert len(fake.calls) == 1
    assert FAKE_KEY not in out["err"][0]


def test_suggest_worker_missing_key_makes_no_call(fake):
    out = _run(SuggestWorker("", "gemini-3.8-flash", MODULES, None))
    assert out["err"] == [ai.MSG_NO_KEY] and fake.clients == []


def test_suggest_worker_runs_in_thread(fake, qapp):
    fake.responses = [_response(_reply())]
    w = SuggestWorker(FAKE_KEY, "gemini-3.8-flash", MODULES, None, text_excerpt="loops")
    got = []
    w.suggested.connect(got.append)
    w.start()
    assert w.wait(10_000)
    qapp.processEvents()
    assert got and got[0].module_id == "python-fundamentals"


def test_key_check_ok_with_model(fake):
    w = KeyCheckWorker(FAKE_KEY, "gemini-3.8-flash")
    out = []
    w.result.connect(lambda ok, msg: out.append((ok, msg)))
    w.run()
    assert out == [(True, "Connected")]
    assert fake.calls == [{"get": "gemini-3.8-flash"}]
    assert fake.clients[0]["http_options"].timeout == ai.KEY_CHECK_TIMEOUT_MS


def test_key_check_lists_models_without_model(fake):
    w = KeyCheckWorker(FAKE_KEY)
    out = []
    w.result.connect(lambda ok, msg: out.append((ok, msg)))
    w.run()
    assert out == [(True, "Connected")] and "list" in fake.calls[0]


def test_key_check_failures(fake):
    fake.get_error = _api_error(errors.ClientError, 400, "INVALID_ARGUMENT", "API key not valid", "API_KEY_INVALID")
    out = []
    w = KeyCheckWorker(FAKE_KEY, "gemini-3.8-flash")
    w.result.connect(lambda ok, msg: out.append((ok, msg)))
    w.run()
    assert out == [(False, ai.MSG_KEY_REJECTED)]
    out.clear()
    empty = KeyCheckWorker("  ")
    empty.result.connect(lambda ok, msg: out.append((ok, msg)))
    empty.run()
    assert out[0][0] is False
