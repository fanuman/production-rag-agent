"""Tests for src/api/streaming.py: how (name, data) pairs look on the wire."""
import json

from src.api.streaming import sse, sse_stream


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


def test_sse_keeps_newlines_inside_one_event():
    raw = sse("token", {"t": "- one\n- two\n\nthree"})
    assert raw.count("\n\n") == 1 and raw.endswith("\n\n")  # exactly one event terminator
    assert parse([raw]) == [("token", {"t": "- one\n- two\n\nthree"})]


def test_sse_stream_wraps_each_event():
    out = list(sse_stream(iter([("step", {"id": "search"}), ("token", {"t": "hi"})])))
    assert parse(out) == [("step", {"id": "search"}), ("token", {"t": "hi"})]


def test_a_failure_becomes_an_error_event_without_leaking_details():
    def broken():
        yield "step", {"id": "search"}
        raise RuntimeError("secret internal detail: redis at 10.0.0.5 refused")

    events = parse(list(sse_stream(broken())))
    assert events[0][0] == "step"                       # what was sent before the failure still arrives
    assert events[-1][0] == "error"
    assert "secret" not in events[-1][1]["message"]
