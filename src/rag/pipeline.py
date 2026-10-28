# src/rag/pipeline.py
import json
import logging
from openai import OpenAI
from pydantic import BaseModel
from typing import List

from src.core.config import DEFAULT_MODEL, RELEVANCE_THRESHOLD, RETRIEVAL_K
from src.core.embeddings import get_embedding
from src.core.vectorstore import get_collection
from src.tools.inventory_tool import TOOL_SCHEMA as AVAILABILITY_SCHEMA, TOOL_FUNCTION as AVAILABILITY_FUNCTION, get_product
from src.tools.calculator_tool import TOOL_SCHEMA as CALC_SCHEMA, TOOL_FUNCTION as CALC_FUNCTION
from src.rag.prompts import build_answer_prompt, FINAL_ANSWER_INSTRUCTION, SYSTEM_PROMPT
from src.core.semantic_cache import SemanticCache
from src.cost.tracker import cost_tracker

from langsmith import traceable

logger = logging.getLogger(__name__)

# tool name -> (label while running, label when finished), for the trail the UI shows
TOOL_LABELS = {
    "CheckAvailability": ("Checking live stock", "Checked live stock"),
    "CalculateTotal": ("Adding the prices", "Added the prices"),
}


def sse(event, data):
    """One Server-Sent Event. The payload is JSON, so a newline inside a token
    can never break the event framing."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _tool_step(event, status):
    running, finished = TOOL_LABELS.get(event["name"], (event["name"], event["name"]))
    if event["name"] == "CheckAvailability":
        detail = event["args"].get("sku", "")
    else:
        detail = event.get("result", "") if status == "done" else ""
    return {"id": event["id"], "label": running if status == "running" else finished,
            "detail": detail, "status": status}


class FinalAnswer(BaseModel):
    answer: str
    sources_used: List[str]


class RAGPipeline:
    def __init__(self, model=DEFAULT_MODEL, relevance_threshold=RELEVANCE_THRESHOLD, k=RETRIEVAL_K, max_iterations=6, final_answer_instruction=None, use_cache=True):
        self.client = OpenAI()
        self.model = model
        self.relevance_threshold = relevance_threshold
        self.k = k
        self.max_iterations = max_iterations
        self.tools = [AVAILABILITY_SCHEMA, CALC_SCHEMA]
        self.available_functions = {**AVAILABILITY_FUNCTION, **CALC_FUNCTION}
        self.cache = SemanticCache()
        self.use_cache = use_cache
        self.final_answer_instruction = final_answer_instruction or FINAL_ANSWER_INSTRUCTION
        self.FALLBACK_MESSAGE =  (
            "Hi! I'm the TrailPeak Outdoors assistant. I can help with product details, "
            "current price and stock, shipping/returns/warranty questions, or comparing "
            "items and calculating totals. What are you looking for?"
        )

    @traceable(name="retrieve")
    def retrieve(self, query_embedding, k=None):
        k = k or self.k
        collection = get_collection()  # fetched fresh, every single call
        results = collection.query(query_embeddings=[query_embedding], n_results=k)
        return results["documents"][0], [m["source"] for m in results["metadatas"][0]], results["distances"][0]

    def _is_out_of_scope(self, distances):
        return all(d >= self.relevance_threshold for d in distances)

    def _agent_events(self, messages):
        """ReAct loop (Day 16) as a generator: keep letting the model act and
        observe until it stops requesting tools, or hit max_iterations as a
        safety guard against a runaway/non-progressing loop. Only turns
        that involved a real tool call get appended - a final "no more
        tools needed" turn is discarded, since the follow-up structured
        answer call re-derives the response fresh anyway.

        Yields a tool_start / tool_done event around every tool call so a
        caller can show progress live, then one last "finished" event."""
        tool_context_parts = []
        for _ in range(self.max_iterations):
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, tools=self.tools
            )
            cost_tracker.record(
                model=self.model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                label="agent_iteration",
            )
            response_message = response.choices[0].message

            if not response_message.tool_calls:
                yield {"type": "finished", "tool_context_parts": tool_context_parts, "hit_cap": False}
                return

            messages.append(response_message)
            for tool_call in response_message.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                yield {"type": "tool_start", "id": tool_call.id, "name": name, "args": args}
                result = self.available_functions[name](**args)
                tool_context_parts.append(result)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
                yield {"type": "tool_done", "id": tool_call.id, "name": name, "args": args, "result": result}

        # hit the cap without a final answer
        yield {"type": "finished", "tool_context_parts": tool_context_parts, "hit_cap": True}

    @traceable(name="agent_loop")
    def _run_agent_loop(self, messages):
        """Non-streaming callers only want the end state, so run the generator
        to its final event and return the same triple as before."""
        for event in self._agent_events(messages):
            if event["type"] == "finished":
                return messages, event["tool_context_parts"], event["hit_cap"]

    @traceable(name="rag_answer")
    def answer(self, query, k=None):
        query_embedding = get_embedding(query)

        # Check if the response is already cached in Redis
        cached = self.cache.check(query_embedding=query_embedding) if self.use_cache else None
        if cached:
            return {
                "answer": cached["response"],
                "sources": [],
                "used_fallback": False,
                "full_context": cached["full_context"],
                "from_cache": True
            }

        chunks, sources, distances = self.retrieve(query_embedding, k=k)

        if self._is_out_of_scope(distances):
            return {
                "answer": self.FALLBACK_MESSAGE,
                "sources": [],
                "used_fallback": True,
                "full_context": "\n\n".join(chunks),
                "from_cache": False
            }

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_answer_prompt(query, chunks, sources)}
        ]
        messages, tool_context_parts, hit_cap = self._run_agent_loop(messages)

        full_context = "\n\n".join(chunks)
        if tool_context_parts:
            full_context += "\n\n" + "\n\n".join(tool_context_parts)

        if hit_cap:
            # Safe failure, same principle as Day 16 - report incompleteness
            # honestly rather than guess at an answer built from partial steps
            return {"answer": "I wasn't able to fully work through this request - it may need to be broken into simpler questions.",
                    "sources": list(set(sources)), "used_fallback": True, "full_context": full_context, "from_cache": False}

        messages.append({"role": "user", "content": self.final_answer_instruction})
        final = self.client.chat.completions.parse(model=self.model, messages=messages, response_format=FinalAnswer)
        cost_tracker.record(
            model=self.model,
            input_tokens=final.usage.prompt_tokens,
            output_tokens=final.usage.completion_tokens,
            label="final_answer",
        )
        parsed = final.choices[0].message.parsed

        if not tool_context_parts and not hit_cap and self.use_cache:
            self.cache.store(query, parsed.answer, query_embedding, full_context)

        return {"answer": parsed.answer, "sources": parsed.sources_used,
                "used_fallback": False, "full_context": full_context, "from_cache": False}

    def answer_stream(self, query, k=None):
        """Yields Server-Sent Events with JSON payloads:
          step    - one line of the trail the UI shows: {id, label, detail, status}
          product - a live inventory result, drawn as a card: {sku, name, price, stock, sizes}
          token   - a piece of the answer text: {t}
          done    - last event on success: {sources, cached, fallback}
          error   - something failed, the stream ends: {message}
        """
        try:
            yield from self._stream_events(query, k)
        except Exception:
            logger.exception("answer_stream failed")
            yield sse("error", {"message": "Something went wrong while answering. Please try again."})

    def _stream_events(self, query, k=None):
        yield sse("step", {"id": "search", "label": "Searching store documents", "detail": "", "status": "running"})
        query_embedding = get_embedding(query)

        cached = self.cache.check(query_embedding=query_embedding) if self.use_cache else None
        if cached:
            text = cached["response"]
            if isinstance(text, bytes):
                text = text.decode()
            yield sse("step", {"id": "search", "label": "Found a saved answer", "detail": "", "status": "done"})
            yield sse("token", {"t": text})
            yield sse("done", {"sources": [], "cached": True, "fallback": False})
            return

        chunks, sources, distances = self.retrieve(query_embedding, k=k)

        if self._is_out_of_scope(distances):
            yield sse("step", {"id": "search", "label": "Searched store documents", "detail": "no close match", "status": "done"})
            yield sse("token", {"t": self.FALLBACK_MESSAGE})
            yield sse("done", {"sources": [], "cached": False, "fallback": True})
            return

        unique_sources = list(dict.fromkeys(sources))
        yield sse("step", {"id": "search", "label": "Searched store documents", "detail": ", ".join(unique_sources), "status": "done"})

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_answer_prompt(query, chunks, sources)}
        ]

        tool_context_parts, hit_cap = [], False
        for event in self._agent_events(messages):
            if event["type"] == "tool_start":
                yield sse("step", _tool_step(event, "running"))
            elif event["type"] == "tool_done":
                yield sse("step", _tool_step(event, "done"))
                if event["name"] == "CheckAvailability":
                    product = get_product(event["args"].get("sku", ""))
                    if product:
                        yield sse("product", product)
            else:  # "finished"
                tool_context_parts, hit_cap = event["tool_context_parts"], event["hit_cap"]

        full_context = "\n\n".join(chunks)
        if tool_context_parts:
            full_context += "\n\n" + "\n\n".join(tool_context_parts)

        if hit_cap:
            yield sse("token", {"t": "I wasn't able to fully work through this request - it may need to be broken into simpler questions."})
            yield sse("done", {"sources": unique_sources, "cached": False, "fallback": True})
            return

        full_reply = ""
        stream = self.client.chat.completions.create(
            model=self.model, messages=messages, stream=True,
            stream_options={"include_usage": True},  # without this, chunk.usage is always empty and no cost is logged
        )
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_reply += delta
                    yield sse("token", {"t": delta})
            if chunk.usage:
                cost_tracker.record(
                    model=self.model,
                    input_tokens=chunk.usage.prompt_tokens,
                    output_tokens=chunk.usage.completion_tokens,
                    label="stream_answer",
                )

        if not tool_context_parts and self.use_cache:
            self.cache.store(query, full_reply, query_embedding, full_context)

        yield sse("done", {"sources": unique_sources, "cached": False, "fallback": False})
