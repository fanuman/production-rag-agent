import json
from openai import OpenAI
from pydantic import BaseModel
from typing import List

from src.core.config import DEFAULT_MODEL, RELEVANCE_THRESHOLD, RETRIEVAL_K
from src.core.embeddings import get_embedding
from src.core.vectorstore import get_collection
from src.tools.inventory_tool import TOOL_SCHEMA, TOOL_FUNCTION
from src.rag.prompts import build_answer_prompt, FINAL_ANSWER_INSTRUCTION


class FinalAnswer(BaseModel):
    answer: str
    sources_used: List[str]  # only sources whose content actually informed this specific answer


class RAGPipeline:
    def __init__(self, model=DEFAULT_MODEL, relevance_threshold=RELEVANCE_THRESHOLD, k=RETRIEVAL_K):
        self.client = OpenAI()
        self.collection = get_collection()
        self.model = model
        self.relevance_threshold = relevance_threshold
        self.k = k
        self.tools = [TOOL_SCHEMA]
        self.available_functions = TOOL_FUNCTION

    def retrieve(self, query, k=None):
        k = k or self.k
        query_embedding = get_embedding(query)
        results = self.collection.query(query_embeddings=[query_embedding], n_results=k)
        chunks = results["documents"][0]
        sources = [meta["source"] for meta in results["metadatas"][0]]
        distances = results["distances"][0]
        return chunks, sources, distances

    def _is_out_of_scope(self, distances):
        return all(d >= self.relevance_threshold for d in distances)

    def _run_tool_decision(self, messages):
        """Shared by answer() and answer_stream(): ask whether a tool is
        needed, execute it if so, and append the result to messages.
        Returns (messages, tool_context_parts) - the latter used by
        answer() to build full_context for eval, ignored by answer_stream()."""
        response = self.client.chat.completions.create(
            model=self.model, messages=messages, tools=self.tools
        )
        response_message = response.choices[0].message
        tool_context_parts = []

        if response_message.tool_calls:
            messages.append(response_message)
            for tool_call in response_message.tool_calls:
                args = json.loads(tool_call.function.arguments)
                result = self.available_functions[tool_call.function.name](**args)
                tool_context_parts.append(result)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

        return messages, tool_context_parts

    def answer(self, query, k=None):
        chunks, sources, distances = self.retrieve(query, k=k)

        if self._is_out_of_scope(distances):
            return {
                "answer": "I don't have information about that.",
                "sources": [],
                "used_fallback": True,
                "full_context": "\n\n".join(chunks),
            }

        messages = [{"role": "user", "content": build_answer_prompt(query, chunks, sources)}]
        messages, tool_context_parts = self._run_tool_decision(messages)

        messages.append({"role": "user", "content": FINAL_ANSWER_INSTRUCTION})
        final = self.client.chat.completions.parse(
            model=self.model, messages=messages, response_format=FinalAnswer
        )
        parsed = final.choices[0].message.parsed

        full_context = "\n\n".join(chunks)
        if tool_context_parts:
            full_context += "\n\n" + "\n\n".join(tool_context_parts)

        return {
            "answer": parsed.answer,
            "sources": parsed.sources_used,
            "used_fallback": False,
            "full_context": full_context,
        }

    def answer_stream(self, query, k=None):
        chunks, sources, distances = self.retrieve(query, k=k)

        if self._is_out_of_scope(distances):
            yield f"event: sources\ndata: {json.dumps([])}\n\n"
            yield "data: I don't have information about that.\n\n"
            yield "data: [DONE]\n\n"
            return

        yield f"event: sources\ndata: {json.dumps(list(set(sources)))}\n\n"

        messages = [{"role": "user", "content": build_answer_prompt(query, chunks, sources)}]
        messages, _ = self._run_tool_decision(messages)  # tool context not tracked here - deliberate

        stream = self.client.chat.completions.create(model=self.model, messages=messages, stream=True)
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield f"data: {delta}\n\n"
        yield "data: [DONE]\n\n"
