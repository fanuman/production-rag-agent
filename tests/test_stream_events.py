"""Tests for the streaming event protocol (src/rag/pipeline.py: sse and answer_stream).

No network, no Redis, no Chroma: OpenAI, the semantic cache, the vector store, the
embedding call and the cost log are all replaced by tiny fakes, so these run anywhere
(including CI) in well under a second.
"""
import json
import os
from types import SimpleNamespace

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-unit-tests")

from src.rag import pipeline as pl  # noqa: E402
from src.rag.pipeline import RAGPipeline, sse  # noqa: E402


# ---------- helpers -------------------------------------------------------------

def parse(raw_events):
    """Turn raw SSE text back into [(event_name, payload), ...] the way the browser does."""
    events = []
    for block in "".join(raw_events).split("\n\n"):
        if not block:
            continue
        lines = block.split("\n")
        name = lines[0].removeprefix("event: ")
        payload = json.loads("".join(line.removeprefix("data: ") for line in lines[1:]))
        events.append((name, payload))
    return events


def reply_text(events):
    return "".join(p["t"] for name, p in events if name == "token")


class FakeCache:
    def __init__(self, hit=None):
        self.hit = hit
        self.stored = []

    def check(self, query_embedding):
        return self.hit

    def store(self, *args):
        self.stored.append(args)


class FakeCosts:
    def __init__(self):
        self.labels = []

    def record(self, model, input_tokens, output_tokens, label):
        self.labels.append(label)


def completion(tool_calls=None):
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=tool_calls))],
    )


def tool_call(name="CheckAvailability", arguments='{"sku": "TP-PCK-003"}', call_id="call_1"):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


class FakeOpenAI:
    """Agent-loop calls return `tool_calls` the first time (or every time if always_tools),
    then a plain message. Streaming calls return the pieces in `stream_text`."""

    def __init__(self, tool_calls=None, always_tools=False, stream_text=("Hello", " world")):
        self.tool_calls = tool_calls
        self.always_tools = always_tools
        self.stream_text = stream_text
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            chunks = [
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=t))], usage=None)
                for t in self.stream_text
            ]
            chunks.append(SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5)))
            return iter(chunks)
        agent_calls = [c for c in self.calls if not c.get("stream")]
        if self.tool_calls and (self.always_tools or len(agent_calls) == 1):
            return completion(self.tool_calls)
        return completion(None)


def make_pipeline(monkeypatch, cache_hit=None, distances=(0.2,), **openai_kwargs):
    client = FakeOpenAI(**openai_kwargs)
    cache = FakeCache(cache_hit)
    costs = FakeCosts()
    collection = SimpleNamespace(query=lambda **kw: {
        "documents": [["chunk about packs"] * len(distances)],
        "metadatas": [[{"source": "product_catalog.txt"}] * len(distances)],
        "distances": [list(distances)],
    })
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr(pl, "OpenAI", lambda: client)
    monkeypatch.setattr(pl, "SemanticCache", lambda: cache)
    monkeypatch.setattr(pl, "get_embedding", lambda text: [0.0])
    monkeypatch.setattr(pl, "get_collection", lambda: collection)
    monkeypatch.setattr(pl, "cost_tracker", costs)
    return RAGPipeline(), client, cache, costs


# ---------- the wire format -----------------------------------------------------

def test_sse_keeps_newlines_inside_one_event():
    raw = sse("token", {"t": "- one\n- two\n\nthree"})
    assert raw.count("\n\n") == 1 and raw.endswith("\n\n")  # exactly one event terminator
    assert parse([raw]) == [("token", {"t": "- one\n- two\n\nthree"})]


# ---------- answer_stream -------------------------------------------------------

def test_plain_answer_streams_steps_tokens_and_done(monkeypatch):
    p, client, cache, costs = make_pipeline(monkeypatch)
    events = parse(p.answer_stream("What is your return policy?"))

    names = [n for n, _ in events]
    assert names[0] == "step" and names[-1] == "done"
    assert events[0][1]["status"] == "running"
    assert events[1][1] == {"id": "search", "label": "Searched store documents",
                            "detail": "product_catalog.txt", "status": "done"}
    assert reply_text(events) == "Hello world"
    assert events[-1][1] == {"sources": ["product_catalog.txt"], "cached": False, "fallback": False}
    assert len(cache.stored) == 1  # no tool used, so the answer is cached


def test_newlines_in_tokens_survive(monkeypatch):
    p, *_ = make_pipeline(monkeypatch, stream_text=("Options:", "\n\n", "- a", "\n", "- b"))
    assert reply_text(parse(p.answer_stream("hi"))) == "Options:\n\n- a\n- b"


def test_streaming_call_asks_for_usage_and_cost_is_logged(monkeypatch):
    p, client, cache, costs = make_pipeline(monkeypatch)
    list(p.answer_stream("hi"))
    stream_call = [c for c in client.calls if c.get("stream")][0]
    assert stream_call["stream_options"] == {"include_usage": True}
    assert "stream_answer" in costs.labels


def test_tool_use_emits_trail_and_product_card(monkeypatch):
    p, client, cache, costs = make_pipeline(monkeypatch, tool_calls=[tool_call()])
    events = parse(p.answer_stream("Is the SummitCarry backpack in stock?"))

    steps = [pl_ for n, pl_ in events if n == "step" and pl_["id"] == "call_1"]
    assert [s["status"] for s in steps] == ["running", "done"]
    assert steps[0]["label"] == "Checking live stock" and steps[1]["label"] == "Checked live stock"
    assert steps[0]["detail"] == "TP-PCK-003"

    products = [pl_ for n, pl_ in events if n == "product"]
    assert len(products) == 1
    assert products[0]["sku"] == "TP-PCK-003" and products[0]["stock"] == 0
    assert cache.stored == []  # live stock must never be cached


def test_unknown_sku_gives_no_product_card(monkeypatch):
    p, *_ = make_pipeline(monkeypatch, tool_calls=[tool_call(arguments='{"sku": "NOPE-1"}')])
    events = parse(p.answer_stream("hi"))
    assert [n for n, _ in events if n == "product"] == []


def test_out_of_scope_question_gets_the_fallback_message(monkeypatch):
    p, client, cache, costs = make_pipeline(monkeypatch, distances=(0.95, 0.9))
    events = parse(p.answer_stream("What is the capital of France?"))
    assert reply_text(events) == p.FALLBACK_MESSAGE
    assert events[-1] == ("done", {"sources": [], "cached": False, "fallback": True})
    assert client.calls == []  # no model call was made


def test_cache_hit_is_served_without_calling_the_model(monkeypatch):
    p, client, cache, costs = make_pipeline(monkeypatch, cache_hit={"response": "saved answer", "full_context": ""})
    events = parse(p.answer_stream("hi"))
    assert reply_text(events) == "saved answer"
    assert events[-1] == ("done", {"sources": [], "cached": True, "fallback": False})
    assert client.calls == []


def test_runaway_agent_loop_ends_with_a_safe_message(monkeypatch):
    p, *_ = make_pipeline(monkeypatch, tool_calls=[tool_call()], always_tools=True)
    p.max_iterations = 2
    events = parse(p.answer_stream("hi"))
    assert "wasn't able to fully work through" in reply_text(events)
    assert events[-1][1]["fallback"] is True


def test_failure_becomes_an_error_event_without_leaking_details(monkeypatch):
    p, *_ = make_pipeline(monkeypatch)

    def boom(text):
        raise RuntimeError("secret internal detail: redis at 10.0.0.5 refused")

    monkeypatch.setattr(pl, "get_embedding", boom)
    events = parse(p.answer_stream("hi"))
    assert events[-1][0] == "error"
    assert "secret" not in events[-1][1]["message"]


# ---------- the non-streaming path still works the same -------------------------

def test_run_agent_loop_still_returns_the_old_triple(monkeypatch):
    p, *_ = make_pipeline(monkeypatch, tool_calls=[tool_call()])
    messages = [{"role": "user", "content": "hi"}]
    out_messages, parts, hit_cap = p._run_agent_loop(messages)
    assert hit_cap is False
    assert len(parts) == 1 and "SummitCarry" in parts[0]
    assert out_messages is messages
