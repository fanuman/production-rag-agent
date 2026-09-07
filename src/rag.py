# src/rag.py
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI, pydantic_function_tool
import chromadb
import json as json_module
from src.inventory_tool import CheckAvailability, check_availability

from pydantic import BaseModel
from typing import List

import json

class FinalAnswer(BaseModel):
    answer: str
    sources_used: List[str]  # only sources whose content actually informed this specific answer


openai_client = OpenAI()
chroma_client = chromadb.PersistentClient(path="./chroma_db")

collection = chroma_client.get_or_create_collection(
    name="trailpeak_docs",
    configuration={"hnsw": {"space": "cosine"}}
)

tools = [pydantic_function_tool(CheckAvailability)]
available_functions = {"CheckAvailability": check_availability}

def get_embedding(text, model="text-embedding-3-small"):
    response = openai_client.embeddings.create(input=text, model=model)
    return response.data[0].embedding

def retrieve(query, k=5):
    query_embedding = get_embedding(query)
    results = collection.query(query_embeddings=[query_embedding], n_results=k)
    chunks = results["documents"][0]
    sources = [meta["source"] for meta in results["metadatas"][0]]
    distances = results["distances"][0]
    return chunks, sources, distances

def build_prompt(query, chunks, sources):
    context = "\n\n".join(
        f"[Source: {source}]\n{chunk}"
        for chunk, source in zip(chunks, sources)
    )
    return f"""Answer the question using the context below for product details and policies. Cite which source document(s) you used in your answer.

    You may reason across multiple pieces of context to reach a conclusion — for example, if the context lists which countries are supported, you can correctly conclude "no" for a country not on that list, without the specific country needing to be named directly.

    If the user asks about current price, stock, or availability, use the CheckAvailability tool with the product's SKU (found in the context) rather than guessing — the context does not contain live pricing or stock data.

    Only say "I don't have information about that" if the context genuinely doesn't contain enough information to answer, even after reasoning through it — not simply because the exact words of the question don't appear verbatim in the context.

    Context:
    \"\"\"
    {context}
    \"\"\"

    Question: {query}
    Answer:"""


def generate_answer(query, k=5):
    chunks, sources, distances = retrieve(query, k=k)

    if all(distance >= 0.68 for distance in distances):
        return {
            "answer": "I don't have information about that.",
            "sources": [],
            "used_fallback": True,
            "full_context": "\n\n".join(chunks),
        }

    prompt = build_prompt(query, chunks, sources)
    messages = [{"role": "user", "content": prompt}]

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini", messages=messages, tools=tools
    )
    response_message = response.choices[0].message

    # Track tool results separately so eval can check the answer against
    # everything it actually saw - retrieved chunks AND tool output, not
    # just retrieval alone. Without this, a correct, tool-grounded answer
    # (like a real price/stock lookup) looks "unfaithful" to an eval script
    # that only knows about the RAG half of the pipeline.
    tool_context_parts = []

    if response_message.tool_calls:
        messages.append(response_message)
        for tool_call in response_message.tool_calls:
            args = json_module.loads(tool_call.function.arguments)
            result = available_functions[tool_call.function.name](**args)
            tool_context_parts.append(result)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

    messages.append({
        "role": "user",
        "content": "Now provide your final answer. In sources_used, list only the "
                    "source document filenames whose content you actually relied on "
                    "to construct THIS answer - not every document you were given."
    })

    final = openai_client.chat.completions.parse(
        model="gpt-4o-mini",
        messages=messages,
        response_format=FinalAnswer
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


def stream_answer(query, k=5):
    chunks, sources, distances = retrieve(query, k=k)
    unique_sources = list(set(sources))

    if all(distance >= 0.68 for distance in distances):
        yield f"event: sources\ndata: {json.dumps([])}\n\n"
        yield "data: I don't have information about that.\n\n"
        yield "data: [DONE]\n\n"
        return

    yield f"event: sources\ndata: {json.dumps(unique_sources)}\n\n"

    prompt = build_prompt(query, chunks, sources)
    messages = [{"role": "user", "content": prompt}]

    # Step 1: decide (and execute) any tool call, non-streamed - tool call
    # arguments arrive as one complete JSON blob anyway, nothing meaningful
    # to show the user token-by-token during this decision step
    decision = openai_client.chat.completions.create(
        model="gpt-4o-mini", messages=messages, tools=tools
    )
    decision_message = decision.choices[0].message

    if decision_message.tool_calls:
        messages.append(decision_message)
        for tool_call in decision_message.tool_calls:
            args = json.loads(tool_call.function.arguments)
            result = available_functions[tool_call.function.name](**args)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

    # Step 2: always a FRESH streamed call for the real answer - even when
    # no tool was needed. This costs one extra call in that case (rather
    # than reusing decision_message's own content), but guarantees genuine
    # live token generation instead of an artificially-chunked pre-written
    # blob. Negligible cost given how cheap these calls have been all along.
    stream = openai_client.chat.completions.create(
        model="gpt-4o-mini", messages=messages, stream=True
    )
    for chunk in stream:
        if chunk.choices:
            delta = chunk.choices[0].delta.content
            if delta:
                yield f"data: {delta}\n\n"

    yield "data: [DONE]\n\n"


if __name__ == "__main__":
    # print("\n---\n")
    # print(generate_answer("Is the SummitCarry backpack in stock, and what does it cost?"))
    # print("\n---\n")
    # print(generate_answer("What's your return policy on hiking boots?"))
    # print("\n---\n")
    print(generate_answer("Do you ship to Germany?"))
    # print(generate_answer("What's the weather like today?"))