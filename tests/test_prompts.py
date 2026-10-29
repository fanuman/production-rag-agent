"""Tests for src/rag/prompts.py: the prompt text the model actually receives."""
from src.rag.prompts import build_answer_prompt, SOURCES_FOOTER_INSTRUCTION


def test_the_default_prompt_is_unchanged_and_has_no_footer_request():
    prompt = build_answer_prompt("hi", ["a chunk"], ["returns_policy.txt"])
    assert prompt.endswith("Question: hi\nAnswer:")   # /ask and the evaluation use exactly this
    assert "SOURCES:" not in prompt


def test_the_footer_request_sits_between_the_question_and_the_answer_prompt():
    prompt = build_answer_prompt("hi", ["a chunk"], ["returns_policy.txt"], sources_footer=True)
    assert prompt.endswith("Question: hi\n\n" + SOURCES_FOOTER_INSTRUCTION + "\n\nAnswer:")


def test_context_chunks_keep_their_source_labels():
    prompt = build_answer_prompt("hi", ["a chunk"], ["returns_policy.txt"], sources_footer=True)
    assert "[Source: returns_policy.txt]\na chunk" in prompt


def test_the_prompt_does_not_ask_for_inline_citations():
    assert "Cite which source" not in build_answer_prompt("hi", ["c"], ["a.txt"])
