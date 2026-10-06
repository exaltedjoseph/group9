from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors, types

from app.constants import MODE_FACILITATOR, MODE_INTERN
from app.core import ai, assistant
from app.core.assistant import (ChatWorker, build_contents, build_system_prompt, build_user_turn, chunk_text,
                                query_terms, resource_context, retrieval_context, retrieve, trim_history)
from tests.conftest import wait_until

FAKE_KEY = "AIzaFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE123"


@pytest.fixture
def library(lib, make_file):
    lib.add_resource(make_file("loops.txt", "A for loop repeats code for each item. While loops check a condition."),
                     "Python loops", "python-fundamentals", "control-flow", "notes", "Loops explained.",
                     ["loops", "iteration"])
    lib.add_resource(make_file("branches.txt", "git branch creates a branch; git merge joins branches."),
                     "Git branching cheat sheet", "version-control-with-git", "branching-and-merging", "reference",
                     "", ["git", "branching"])
    lib.add_classwork("python-fundamentals", "2026-10-05", "Loop drills", topic_id="control-flow")
    return lib


# ---------------------------------------------------------------------- system prompt & context
def test_system_prompt_lists_syllabus_resources_and_rules(library):
    prompt = build_system_prompt(library, MODE_INTERN, today=date(2026, 10, 6))
    assert "tutor" in prompt and "Markdown" in prompt
    assert "Never invent" in prompt and "file names" in prompt
    assert "isn\u2019t in your library" in prompt
    assert "Python Fundamentals \u2014 Core Python syntax and problem solving." in prompt
    assert "Control Flow" in prompt and "Branching & Merging" in prompt
    assert "\u201cPython loops\u201d \u2014 Python Fundamentals \u203a Control Flow" in prompt
    assert "keywords: loops, iteration" in prompt
    assert "loops.txt" not in prompt
    assert "2026-10-05: Loop drills" in prompt
    assert "Tuesday, 2026-10-06" in prompt
    assert "intern" in prompt


def test_system_prompt_mode_and_empty_library(lib):
    prompt = build_system_prompt(lib, MODE_FACILITATOR)
    assert "facilitator" in prompt
    assert "no resources yet" in prompt


def test_resource_context_includes_metadata_and_text(library):
    r = library.search("loops")[0]
    label, text = resource_context(library, r.id)
    assert label == "Python loops"
    assert "Module: Python Fundamentals" in text and "Topic: Control Flow" in text
    assert "Keywords: loops, iteration" in text and "Description: Loops explained." in text
    assert "A for loop repeats code" in text
    assert resource_context(library, "missing") == ("", "")


def test_resource_context_truncates(lib, make_file):
    r = lib.add_resource(make_file("big.txt", "word " * 10_000), "Big notes", "python-fundamentals")
    _, text = resource_context(lib, r.id, max_chars=500)
    assert "truncated" in text and len(text) < 900


def test_retrieval_finds_relevant_resources(library):
    assert query_terms("Can you explain how git branching works?") == ["git", "branching"]
    hits = retrieve(library, "How do while loops work in Python?")
    assert hits and hits[0].title == "Python loops"
    text, ids = retrieval_context(library, "explain git branching please")
    assert ids and library.resource(ids[0]).title == "Git branching cheat sheet"
    assert "git merge joins branches" in text
    assert retrieval_context(library, "thanks!") == ("", [])
    loops_id = hits[0].id
    assert loops_id not in [r.id for r in retrieve(library, "loops", exclude=[loops_id])]


def test_user_turn_and_history():
    assert build_user_turn("Hi") == "Hi"
    turn = build_user_turn("Explain this", "### Attached resource")
    assert turn.index("<library_context>") < turn.index("### Attached resource") < turn.index("Explain this")
    assert len(build_user_turn("q", "x" * 50_000)) < assistant.MAX_CONTEXT_CHARS + 500
    history = [("model", "stray"), *[(r, f"m{i}") for i in range(30) for r in ("user", "model")]]
    trimmed = trim_history(history)
    assert len(trimmed) <= assistant.MAX_HISTORY_MESSAGES and trimmed[0][0] == "user"
    contents = build_contents([("user", "a"), ("model", "b")], "c", "ctx")
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert "ctx" in contents[-1].parts[0].text and contents[-1].parts[0].text.endswith("c")


# ---------------------------------------------------------------------- streaming (mocked client)
def _chunk(text=None, finish=None, block=None, thought=None):
    parts = []
    if thought:
        parts.append(SimpleNamespace(text=thought, thought=True))
    if text is not None:
        parts.append(SimpleNamespace(text=text, thought=None))
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts), finish_reason=finish)],
        prompt_feedback=SimpleNamespace(block_reason=block) if block else None,
    )


def _api_error(cls, code, status, message):
    return cls(code, {"error": {"code": code, "status": status, "message": message}})


class FakeGenai:
    def __init__(self):
        self.calls: list[dict] = []
        self.clients: list[dict] = []
        self.streams: list = []
        self.closed = 0

    def Client(self, *, api_key, http_options=None):  # noqa: N802 - mirrors genai.Client
        self.clients.append({"api_key": api_key, "http_options": http_options})
        fake = self

        class _Models:
            def generate_content_stream(self, *, model, contents, config=None):
                fake.calls.append({"model": model, "contents": contents, "config": config})
                item = fake.streams.pop(0)
                if isinstance(item, BaseException):
                    raise item

                def gen():
                    for c in item:
                        if isinstance(c, BaseException):
                            raise c
                        yield c
                return gen()

        class _Client:
            models = _Models()

            def close(self):
                fake.closed += 1

        return _Client()


@pytest.fixture
def fake(monkeypatch):
    f = FakeGenai()
    monkeypatch.setattr(ai.genai, "Client", f.Client)
    return f


def _run(worker):
    out = {"chunks": [], "ok": [], "err": []}
    worker.chunk.connect(out["chunks"].append)
    worker.finished_ok.connect(out["ok"].append)
    worker.failed.connect(out["err"].append)
    worker.run()
    return out


def test_chat_worker_streams_and_accumulates(fake):
    fake.streams = [[_chunk("A **loop** "), _chunk(thought="thinking\u2026"), _chunk("repeats code."),
                     _chunk("", finish="STOP")]]
    w = ChatWorker(FAKE_KEY, "gemini-3.8-flash", "SYSTEM", [("user", "hi"), ("model", "hello")],
                   "What is a loop?", "### Attached resource: \u201cPython loops\u201d")
    out = _run(w)
    assert out["err"] == []
    assert out["chunks"] == ["A **loop** ", "repeats code."]
    assert out["ok"] == ["A **loop** repeats code."]
    call = fake.calls[0]
    assert call["model"] == "gemini-3.8-flash"
    assert [c.role for c in call["contents"]] == ["user", "model", "user"]
    last = call["contents"][-1].parts[0].text
    assert "Python loops" in last and last.endswith("What is a loop?")
    assert call["config"].system_instruction == "SYSTEM"
    assert call["config"].thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert fake.clients[0]["api_key"] == FAKE_KEY
    assert fake.clients[0]["http_options"].timeout == assistant.CHAT_TIMEOUT_MS
    assert fake.closed == 1


def test_chat_worker_cancel_stops_emitting(fake):
    fake.streams = [[_chunk("one "), _chunk("two "), _chunk("three")]]
    w = ChatWorker(FAKE_KEY, "gemini-2.5-flash", "S", [], "q")
    out = {"chunks": [], "ok": [], "err": []}

    def on_chunk(text):
        out["chunks"].append(text)
        w.cancel()

    w.chunk.connect(on_chunk)
    w.finished_ok.connect(out["ok"].append)
    w.failed.connect(out["err"].append)
    w.run()
    assert out == {"chunks": ["one "], "ok": [], "err": []}
    assert fake.calls[0]["config"].thinking_config is None


def test_chat_worker_retries_without_thinking_on_bad_request(fake):
    fake.streams = [_api_error(errors.ClientError, 400, "INVALID_ARGUMENT", "Unknown field thinking_level"),
                    [_chunk("ok")]]
    out = _run(ChatWorker(FAKE_KEY, "gemini-3.8-flash", "S", [], "q"))
    assert out["ok"] == ["ok"] and len(fake.calls) == 2
    assert fake.calls[1]["config"].thinking_config is None


@pytest.mark.parametrize("stream, expected", [
    (_api_error(errors.ClientError, 400, "INVALID_ARGUMENT", "API key not valid. API_KEY_INVALID"),
     ai.MSG_KEY_REJECTED),
    (_api_error(errors.ClientError, 429, "RESOURCE_EXHAUSTED", "quota"), ai.MSG_QUOTA),
    (_api_error(errors.ServerError, 503, "UNAVAILABLE", "overloaded"), ai.MSG_SERVER),
    ([httpx.ConnectError("offline")], ai.MSG_OFFLINE),
    ([httpx.ReadTimeout("slow")], ai.MSG_TIMEOUT),
    ([_chunk(None, block="SAFETY")], assistant.MSG_CHAT_BLOCKED),
    ([_chunk("", finish="SAFETY")], assistant.MSG_CHAT_BLOCKED),
    ([_chunk("")], assistant.MSG_CHAT_EMPTY),
])
def test_chat_worker_error_mapping(fake, stream, expected):
    fake.streams = [stream]
    out = _run(ChatWorker(FAKE_KEY, "gemini-2.5-flash", "S", [], "q"))
    assert out["ok"] == [] and out["err"] == [expected]
    assert FAKE_KEY not in out["err"][0]
    assert fake.closed == 1


def test_chat_worker_error_redacts_key(fake):
    fake.streams = [RuntimeError(f"boom {FAKE_KEY}")]
    out = _run(ChatWorker(FAKE_KEY, "gemini-2.5-flash", "S", [], "q"))
    assert out["err"] and FAKE_KEY not in out["err"][0]


def test_chat_worker_missing_key_makes_no_call(fake):
    out = _run(ChatWorker("", "gemini-3.8-flash", "S", [], "q"))
    assert out["err"] == [assistant.MSG_NO_KEY] and fake.clients == []


def test_chunk_text_fallback():
    assert chunk_text(SimpleNamespace(text="plain")) == "plain"
    assert chunk_text(_chunk("hi", thought="hidden")) == "hi"


def test_chat_worker_runs_in_thread(fake, qapp):
    fake.streams = [[_chunk("Hello "), _chunk("there")]]
    w = ChatWorker(FAKE_KEY, "gemini-3.8-flash", "S", [], "q")
    got: list[str] = []
    chunks: list[str] = []
    w.chunk.connect(chunks.append)
    w.finished_ok.connect(got.append)
    w.start()
    assert w.wait(10_000)
    assert wait_until(lambda: bool(got))
    assert got == ["Hello there"] and "".join(chunks) == "Hello there"
