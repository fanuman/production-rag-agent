"""Gathers raw facts for a topic from the product catalog. Deliberately
outputs plain factual notes, not customer-facing prose - keeping this
node's job narrow is what makes the two-agent split actually earn its
keep, rather than being one agent's logic split into two functions."""
from openai import OpenAI
from src.core.config import DEFAULT_MODEL
from src.core.embeddings import get_embedding
from src.core.vectorstore import get_collection
from src.agents.state import ContentState

_client = OpenAI()


def researcher_node(state: ContentState) -> ContentState:
    query_embedding = get_embedding(state["topic"])
    collection = get_collection()
    results = collection.query(query_embeddings=[query_embedding], n_results=5)
    chunks = results["documents"][0]
    sources = [m["source"] for m in results["metadatas"][0]]

    prompt = f"""Extract the key facts relevant to this topic from the context below.
Return plain factual bullet points only - no marketing language, no prose, just facts
a writer could later turn into customer-facing copy. If the catalog doesn't fully
support the topic, say so plainly as one of the bullets rather than omitting it.

Topic: {state['topic']}

Context:
{chr(10).join(chunks)}"""

    response = _client.chat.completions.create(
        model=DEFAULT_MODEL, messages=[{"role": "user", "content": prompt}]
    )
    return {**state, "research_notes": response.choices[0].message.content, "sources": list(set(sources))}