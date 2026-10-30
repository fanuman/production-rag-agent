"""Tests for src/cost/report.py's summarize() (what GET /cost returns) and for the API's routes."""
import json

from src.cost import report


def write_log(path, entries):
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))


def entry(label, cost, gpt4o=None):
    return {"label": label, "cost_usd": cost, "cost_if_gpt4o_usd": gpt4o if gpt4o is not None else cost * 10}


def test_summary_adds_up_every_call_and_groups_by_stage(tmp_path, monkeypatch):
    log = tmp_path / "cost_log.jsonl"
    write_log(log, [entry("stream_answer", 0.25), entry("agent_iteration", 0.5), entry("stream_answer", 0.25)])
    monkeypatch.setattr(report, "LOG_PATH", log)

    summary = report.summarize()

    assert summary["total_calls"] == 3
    assert summary["total_cost_usd"] == 1.0
    assert summary["cost_if_gpt4o_usd"] == 10.0
    assert summary["by_stage"] == {"stream_answer": 0.5, "agent_iteration": 0.5}


def test_no_log_yet_gives_zeros_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "LOG_PATH", tmp_path / "missing.jsonl")
    assert report.summarize() == {"total_calls": 0, "total_cost_usd": 0.0, "cost_if_gpt4o_usd": 0.0, "by_stage": {}}


def test_an_old_log_line_without_the_gpt4o_field_still_counts(tmp_path, monkeypatch):
    log = tmp_path / "cost_log.jsonl"
    log.write_text(json.dumps({"label": "final_answer", "cost_usd": 0.1}) + "\n")
    monkeypatch.setattr(report, "LOG_PATH", log)
    assert report.summarize()["total_cost_usd"] == 0.1


def test_the_api_has_cost_but_no_open_chat_route():
    from src.api.main import app
    paths = {route.path for route in app.routes}
    assert "/cost" in paths
    assert "/chat" not in paths
