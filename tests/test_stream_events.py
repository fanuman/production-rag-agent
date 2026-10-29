"""Tests for the pipeline (src/rag/pipeline.py): the live events from answer_stream()
and the finished dict from answer().

No network, no Redis, no Chroma: OpenAI, the semantic cache, the vector store, the
embedding call and the cost log are all replaced by tiny fakes, so these run anywhere
(including CI) in well under a second.
"""
import os
from types import SimpleNamespace

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-unit-tests")

from src.rag import pipeline as pl  # noqa: E402
from src.rag.pipeline import RAGPipeline  # noqa: E402


# ---------- helpers -------------------------------------------------------------

def reply_text(events):
    return "".join(data["t"] for name, data in events if name == "token")


def names(events):
    return [name for name, _ in events]


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


def tool_call(name="CheckAvailability", arguments='{"sku": "TP-PCK-003"}', call_id="call_1"):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


class FakeOpenAI:
    """Every model call in the loop is streamed. While `tool_calls` are configured, the first
    call is a "tool turn" (the requests arrive in pieces, like the real API; every call if
    always_tools) and any other call is a text turn that streams `stream_text`.
    `parse` is the structured-output call that answer() makes at the end."""

    def __init__(self, tool_calls=None, always_tools=False, stream_text=("Hello", " world"), tool_turn_text=""):
        self.tool_calls = tool_calls
        self.always_tools = always_tools
        self.stream_text = stream_text
        self.tool_turn_text = tool_turn_text   # words the model writes before asking for a tool
        self.calls = []         # streamed calls
        self.parse_calls = []   # structured-output calls
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create, parse=self._parse))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.tool_calls and (self.always_tools or len(self.calls) == 1):
            return iter(self._tool_chunks())
        return iter(self._text_chunks())

    def _parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        parsed = SimpleNamespace(answer="Structured answer", sources_used=["returns_policy.txt"])
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
                               choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])

    @staticmethod
    def _chunk(content=None, tool_pieces=None):
        delta = SimpleNamespace(content=content, tool_calls=tool_pieces)
        return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)

    @staticmethod
    def _usage_chunk():
        return SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))

    def _text_chunks(self):
        return [self._chunk(content=t) for t in self.stream_text] + [self._usage_chunk()]

    def _tool_chunks(self):
        chunks = [self._chunk(content=self.tool_turn_text)] if self.tool_turn_text else []
        for i, tc in enumerate(self.tool_calls):
            args = tc.function.arguments
            half = len(args) // 2   # the JSON arguments arrive in two pieces
            first = SimpleNamespace(index=i, id=tc.id, function=SimpleNamespace(name=tc.function.name, arguments=args[:half]))
            second = SimpleNamespace(index=i, id=None, function=SimpleNamespace(name=None, arguments=args[half:]))
            chunks += [self._chunk(tool_pieces=[first]), self._chunk(tool_pieces=[second])]
        return chunks + [self._usage_chunk()]


def make_pipeline(monkeypatch, cache_hit=None, distances=(0.2,), pipeline_kwargs=None, sources=None, **openai_kwargs):
    """`sources` = the file names the search finds (one chunk each); default is one product_catalog.txt chunk."""
    if sources:
        distances = (0.2,) * len(sources)
    names = list(sources) if sources else ["product_catalog.txt"] * len(distances)
    client = FakeOpenAI(**openai_kwargs)
    cache = FakeCache(cache_hit)
    costs = FakeCosts()
    collection = SimpleNamespace(query=lambda **kw: {
        "documents": [["chunk about packs"] * len(distances)],
        "metadatas": [[{"source": name} for name in names]],
        "distances": [list(distances)],
    })
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr(pl, "OpenAI", lambda: client)
    monkeypatch.setattr(pl, "SemanticCache", lambda: cache)
    monkeypatch.setattr(pl, "get_embedding", lambda text: [0.0])
    monkeypatch.setattr(pl, "get_collection", lambda: collection)
    monkeypatch.setattr(pl, "cost_tracker", costs)
    return RAGPipeline(**(pipeline_kwargs or {})), client, cache, costs


# ---------- answer_stream: the live events --------------------------------------

def test_plain_answer_streams_steps_tokens_and_done(monkeypatch):
    p, client, cache, costs = make_pipeline(monkeypatch)
    events = list(p.answer_stream("What is your return policy?"))

    assert names(events)[0] == "step" and names(events)[-1] == "done"
    assert events[0][1]["status"] == "running"
    assert events[1] == ("step", {"id": "search", "label": "Searched store documents",
                                  "detail": "product_catalog.txt", "status": "done"})
    assert reply_text(events) == "Hello world"
    assert events[-1] == ("done", {"sources": ["product_catalog.txt"], "cached": False, "fallback": False})
    assert len(cache.stored) == 1  # no tool used, so the answer is cached


def test_plain_answer_costs_exactly_one_model_call(monkeypatch):
    # The model's first reply IS the answer and is streamed as it arrives -
    # there is no second "write it again" call.
    p, client, cache, costs = make_pipeline(monkeypatch)
    list(p.answer_stream("What is your return policy?"))
    assert len(client.calls) == 1 and client.parse_calls == []
    assert costs.labels == ["stream_answer"]


def test_every_streaming_call_asks_for_usage_so_cost_is_logged(monkeypatch):
    p, client, cache, costs = make_pipeline(monkeypatch, tool_calls=[tool_call()])
    list(p.answer_stream("hi"))
    assert client.calls and all(c["stream"] and c["stream_options"] == {"include_usage": True} for c in client.calls)
    assert costs.labels == ["agent_iteration", "stream_answer"]  # the tool turn, then the answer turn


def test_tool_use_emits_trail_and_product_card(monkeypatch):
    p, client, cache, costs = make_pipeline(monkeypatch, tool_calls=[tool_call()])
    events = list(p.answer_stream("Is the SummitCarry backpack in stock?"))

    steps = [data for name, data in events if name == "step" and data["id"] == "call_1"]
    assert [s["status"] for s in steps] == ["running", "done"]
    assert steps[0]["label"] == "Checking live stock" and steps[1]["label"] == "Checked live stock"
    assert steps[0]["detail"] == "TP-PCK-003"

    products = [data for name, data in events if name == "product"]
    assert len(products) == 1
    assert products[0]["sku"] == "TP-PCK-003" and products[0]["stock"] == 0
    assert reply_text(events) == "Hello world"   # the answer streams after the tool turn
    assert len(client.calls) == 2                # tool turn + answer turn, nothing extra
    assert cache.stored == []  # live stock must never be cached


def test_two_tool_requests_in_one_turn_are_both_run_in_order(monkeypatch):
    calls = [tool_call(call_id="call_1", arguments='{"sku": "TP-PCK-003"}'),
             tool_call(call_id="call_2", arguments='{"sku": "TP-POLE-006"}')]
    p, client, cache, costs = make_pipeline(monkeypatch, tool_calls=calls)
    events = list(p.answer_stream("hi"))
    assert [data["sku"] for name, data in events if name == "product"] == ["TP-PCK-003", "TP-POLE-006"]
    # the assistant turn and both tool results were added to the conversation for the next model call
    second_call_messages = client.calls[1]["messages"]
    assert [m["role"] for m in second_call_messages[-3:]] == ["assistant", "tool", "tool"]
    assert [t["id"] for t in second_call_messages[-3]["tool_calls"]] == ["call_1", "call_2"]


def test_unknown_sku_gives_no_product_card(monkeypatch):
    p, *_ = make_pipeline(monkeypatch, tool_calls=[tool_call(arguments='{"sku": "NOPE-1"}')])
    events = list(p.answer_stream("hi"))
    assert "product" not in names(events)


def test_out_of_scope_question_gets_the_fallback_message(monkeypatch):
    p, client, cache, costs = make_pipeline(monkeypatch, distances=(0.95, 0.9))
    events = list(p.answer_stream("What is the capital of France?"))
    assert reply_text(events) == p.FALLBACK_MESSAGE
    assert events[-1] == ("done", {"sources": [], "cached": False, "fallback": True})
    assert client.calls == []  # no model call was made


def test_cache_hit_is_served_without_calling_the_model(monkeypatch):
    p, client, cache, costs = make_pipeline(monkeypatch, cache_hit={"response": "saved answer", "full_context": ""})
    events = list(p.answer_stream("hi"))
    assert reply_text(events) == "saved answer"
    assert events[-1] == ("done", {"sources": [], "cached": True, "fallback": False})
    assert client.calls == []


def test_cached_answer_that_comes_back_as_bytes_is_decoded(monkeypatch):
    p, *_ = make_pipeline(monkeypatch, cache_hit={"response": b"saved answer", "full_context": b""})
    assert reply_text(list(p.answer_stream("hi"))) == "saved answer"


def test_runaway_agent_loop_ends_with_a_safe_message(monkeypatch):
    p, *_ = make_pipeline(monkeypatch, tool_calls=[tool_call()], always_tools=True)
    p.max_iterations = 2
    events = list(p.answer_stream("hi"))
    assert "wasn't able to fully work through" in reply_text(events)
    assert events[-1][1]["fallback"] is True


def test_an_empty_reply_is_never_cached(monkeypatch):
    p, client, cache, costs = make_pipeline(monkeypatch, stream_text=("  ",))
    list(p.answer_stream("hi"))
    assert cache.stored == []


def test_a_failure_inside_the_pipeline_propagates_to_the_caller(monkeypatch):
    # answer_stream does not swallow errors: src/api/streaming.py turns them into an `error` event
    p, *_ = make_pipeline(monkeypatch)

    def boom(text):
        raise RuntimeError("redis refused")

    monkeypatch.setattr(pl, "get_embedding", boom)
    try:
        list(p.answer_stream("hi"))
        raised = False
    except RuntimeError:
        raised = True
    assert raised


# ---------- the SOURCES: footer on the streamed answer ---------------------------

THREE_FILES = ("product_catalog.txt", "returns_policy.txt", "shipping_policy.txt")


def test_the_footer_picks_the_sources_and_never_reaches_the_screen(monkeypatch):
    p, client, cache, costs = make_pipeline(
        monkeypatch, sources=THREE_FILES,
        stream_text=("Returns take 30 days.", "\n\n", "SOUR", "CES: returns_policy.txt"))
    events = list(p.answer_stream("What is your return policy?"))

    assert reply_text(events) == "Returns take 30 days."
    assert events[-1] == ("done", {"sources": ["returns_policy.txt"], "cached": False, "fallback": False})
    assert [c[1] for c in cache.stored] == ["Returns take 30 days."]   # the cached answer is clean too


def test_without_a_footer_every_retrieved_file_is_shown(monkeypatch):
    p, *_ = make_pipeline(monkeypatch, sources=THREE_FILES, stream_text=("No footer here.",))
    events = list(p.answer_stream("hi"))
    assert reply_text(events) == "No footer here."
    assert events[-1][1]["sources"] == list(THREE_FILES)


def test_sources_none_shows_no_chips(monkeypatch):
    p, *_ = make_pipeline(monkeypatch, sources=THREE_FILES, stream_text=("I don't know.", "\nSOURCES: none"))
    events = list(p.answer_stream("hi"))
    assert reply_text(events) == "I don't know."
    assert events[-1][1]["sources"] == []


def test_a_file_the_model_made_up_is_ignored(monkeypatch):
    p, *_ = make_pipeline(monkeypatch, sources=THREE_FILES,
                          stream_text=("Answer.", "\nSOURCES: returns_policy.txt, imaginary.txt"))
    assert list(p.answer_stream("hi"))[-1][1]["sources"] == ["returns_policy.txt"]


def test_footer_works_after_a_tool_turn(monkeypatch):
    p, client, cache, costs = make_pipeline(
        monkeypatch, sources=THREE_FILES, tool_calls=[tool_call()],
        stream_text=("It is out of stock.", "\nSOURCES: product_catalog.txt"))
    events = list(p.answer_stream("hi"))
    assert reply_text(events) == "It is out of stock."
    assert events[-1][1]["sources"] == ["product_catalog.txt"]


def test_text_before_a_tool_call_cannot_swallow_the_answer(monkeypatch):
    # even a SOURCES: line in the tool turn must not hide the final turn: each turn is filtered separately
    p, *_ = make_pipeline(
        monkeypatch, sources=THREE_FILES, tool_calls=[tool_call()],
        tool_turn_text="Let me check.\nSOURCES: junk", stream_text=("It is out of stock.", "\nSOURCES: returns_policy.txt"))
    events = list(p.answer_stream("hi"))
    assert reply_text(events) == "Let me check.It is out of stock."
    assert events[-1][1]["sources"] == ["returns_policy.txt"]


def test_only_the_streamed_prompt_asks_for_the_footer(monkeypatch):
    p, client, *_ = make_pipeline(monkeypatch)
    list(p.answer_stream("hi"))
    assert "SOURCES:" in client.calls[0]["messages"][1]["content"]   # in the user message, right after the question

    p, client, *_ = make_pipeline(monkeypatch)
    p.answer("hi")
    assert "SOURCES:" not in client.calls[0]["messages"][1]["content"]   # /ask is unchanged


def test_the_prompt_no_longer_asks_for_inline_citations(monkeypatch):
    p, client, *_ = make_pipeline(monkeypatch)
    list(p.answer_stream("hi"))
    user_prompt = client.calls[0]["messages"][1]["content"]
    assert "Cite which source" not in user_prompt and "[Source: product_catalog.txt]" in user_prompt   # chunk labels stay


# ---------- answer: one finished dict (used by /ask and the evaluation) ---------

def test_answer_returns_structured_text_and_sources(monkeypatch):
    p, client, cache, costs = make_pipeline(monkeypatch)
    result = p.answer("What is your return policy?")

    assert result["answer"] == "Structured answer"
    assert result["sources"] == ["returns_policy.txt"]      # what the model said it relied on
    assert result["used_fallback"] is False and result["from_cache"] is False
    assert result["full_context"] == "chunk about packs"
    assert len(client.calls) == 1 and len(client.parse_calls) == 1
    # the loop's own last turn is not shown to anyone; the structured call writes the answer
    assert costs.labels == ["agent_iteration", "final_answer"]
    assert [c[1] for c in cache.stored] == ["Structured answer"]


def test_answer_with_a_tool_is_not_cached_and_keeps_the_tool_output_as_context(monkeypatch):
    p, client, cache, costs = make_pipeline(monkeypatch, tool_calls=[tool_call()])
    result = p.answer("Is the SummitCarry backpack in stock?")
    assert "SummitCarry" in result["full_context"]
    assert cache.stored == []


def test_answer_passes_the_custom_final_instruction_to_the_structured_call(monkeypatch):
    # src/evaluation/ab_test.py relies on this
    p, client, cache, costs = make_pipeline(monkeypatch, pipeline_kwargs={"final_answer_instruction": "BE BRIEF"})
    p.answer("hi")
    assert client.parse_calls[0]["messages"][-1] == {"role": "user", "content": "BE BRIEF"}


def test_answer_out_of_scope_and_cache_hit(monkeypatch):
    p, client, *_ = make_pipeline(monkeypatch, distances=(0.95,))
    result = p.answer("What is the capital of France?")
    assert result["answer"] == p.FALLBACK_MESSAGE and result["used_fallback"] is True and result["sources"] == []
    assert client.calls == []

    p, client, *_ = make_pipeline(monkeypatch, cache_hit={"response": "saved", "full_context": "ctx"})
    result = p.answer("hi")
    assert result["answer"] == "saved" and result["from_cache"] is True and client.calls == []


def test_answer_runaway_loop_reports_incomplete_work(monkeypatch):
    p, client, *_ = make_pipeline(monkeypatch, tool_calls=[tool_call()], always_tools=True)
    p.max_iterations = 2
    result = p.answer("hi")
    assert result["used_fallback"] is True and "wasn't able to fully work through" in result["answer"]
    assert client.parse_calls == []   # no structured call is made for an incomplete loop
