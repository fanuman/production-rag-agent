# src/rag/pipeline.py
import json
from openai import OpenAI
from pydantic import BaseModel
from typing import List

from src.core.config import DEFAULT_MODEL, RELEVANCE_THRESHOLD, RETRIEVAL_K
from src.core.embeddings import get_embedding
from src.core.vectorstore import get_collection
from src.tools.inventory_tool import TOOL_SCHEMA as AVAILABILITY_SCHEMA, TOOL_FUNCTION as AVAILABILITY_FUNCTION
from src.tools.calculator_tool import TOOL_SCHEMA as CALC_SCHEMA, TOOL_FUNCTION as CALC_FUNCTION
from src.rag.prompts import build_answer_prompt, FINAL_ANSWER_INSTRUCTION


class FinalAnswer(BaseModel):
    answer: str
    sources_used: List[str]


class RAGPipeline:
    def __init__(self, model=DEFAULT_MODEL, relevance_threshold=RELEVANCE_THRESHOLD, k=RETRIEVAL_K, max_iterations=6):
        self.client = OpenAI()
        self.collection = get_collection()
        self.model = model
        self.relevance_threshold = relevance_threshold
        self.k = k
        self.max_iterations = max_iterations
        self.tools = [AVAILABILITY_SCHEMA, CALC_SCHEMA]
        self.available_functions = {**AVAILABILITY_FUNCTION, **CALC_FUNCTION}
        self.FALLBACK_MESSAGE =  (
            "Hi! I'm the TrailPeak Outdoors assistant. I can help with product details, "
            "current price and stock, shipping/returns/warranty questions, or comparing "
            "items and calculating totals. What are you looking for?"
        )

    def retrieve(self, query, k=None):
        k = k or self.k
        query_embedding = get_embedding(query)
        results = self.collection.query(query_embeddings=[query_embedding], n_results=k)
        return results["documents"][0], [m["source"] for m in results["metadatas"][0]], results["distances"][0]

    def _is_out_of_scope(self, distances):
        return all(d >= self.relevance_threshold for d in distances)

    def _run_agent_loop(self, messages):
        """ReAct loop (Day 16): keep letting the model act and observe
        until it stops requesting tools, or hit max_iterations as a
        safety guard against a runaway/non-progressing loop. Only turns
        that involved a real tool call get appended - a final "no more
        tools needed" turn is discarded, since the follow-up structured
        answer call re-derives the response fresh anyway."""
        tool_context_parts = []
        for _ in range(self.max_iterations):
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, tools=self.tools
            )
            response_message = response.choices[0].message

            if not response_message.tool_calls:
                return messages, tool_context_parts, False

            messages.append(response_message)
            for tool_call in response_message.tool_calls:
                args = json.loads(tool_call.function.arguments)
                result = self.available_functions[tool_call.function.name](**args)
                tool_context_parts.append(result)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

        return messages, tool_context_parts, True  # hit the cap without a final answer

    def answer(self, query, k=None):
        chunks, sources, distances = self.retrieve(query, k=k)

        if self._is_out_of_scope(distances):
            return {
                "answer": self.FALLBACK_MESSAGE,
                "sources": [],
                "used_fallback": True,
                "full_context": "\n\n".join(chunks),
            }

        messages = [{"role": "user", "content": build_answer_prompt(query, chunks, sources)}]
        messages, tool_context_parts, hit_cap = self._run_agent_loop(messages)

        full_context = "\n\n".join(chunks)
        if tool_context_parts:
            full_context += "\n\n" + "\n\n".join(tool_context_parts)

        if hit_cap:
            # Safe failure, same principle as Day 16 - report incompleteness
            # honestly rather than guess at an answer built from partial steps
            return {"answer": "I wasn't able to fully work through this request - it may need to be broken into simpler questions.",
                    "sources": list(set(sources)), "used_fallback": True, "full_context": full_context}

        messages.append({"role": "user", "content": FINAL_ANSWER_INSTRUCTION})
        final = self.client.chat.completions.parse(model=self.model, messages=messages, response_format=FinalAnswer)
        parsed = final.choices[0].message.parsed

        return {"answer": parsed.answer, "sources": parsed.sources_used,
                "used_fallback": False, "full_context": full_context}

    def answer_stream(self, query, k=None):
        chunks, sources, distances = self.retrieve(query, k=k)

        if self._is_out_of_scope(distances):
            yield f"event: sources\ndata: {json.dumps([])}\n\n"
            yield f"data: {self.FALLBACK_MESSAGE}\n\n"
            yield "data: [DONE]\n\n"
            return

        yield f"event: sources\ndata: {json.dumps(list(set(sources)))}\n\n"

        messages = [{"role": "user", "content": build_answer_prompt(query, chunks, sources)}]
        messages, _, hit_cap = self._run_agent_loop(messages)

        if hit_cap:
            yield "data: I wasn't able to fully work through this request - it may need to be broken into simpler questions.\n\n"
            yield "data: [DONE]\n\n"
            return

        stream = self.client.chat.completions.create(model=self.model, messages=messages, stream=True)
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield f"data: {delta}\n\n"
        yield "data: [DONE]\n\n"