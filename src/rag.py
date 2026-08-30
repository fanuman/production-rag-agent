# src/rag.py
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
import chromadb

openai_client = OpenAI()
chroma_client = chromadb.PersistentClient(path="./chroma_db")

collection = chroma_client.get_or_create_collection(
    name="ai_governance_docs",
    configuration={"hnsw": {"space": "cosine"}}
)

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
    return f"""Answer the question using ONLY the context below. Cite which source document(s) you used in your answer. If the answer isn't in the context, say "I don't have information about that."

Context:
\"\"\"
{context}
\"\"\"

Question: {query}
Answer:"""

def generate_answer(query, k=5):
    chunks, sources, distances = retrieve(query, k=k)

    for source, distance in zip(sources, distances):
        print(f"{distance:.4f} - {source}")

    if all(distance >= 0.5 for distance in distances):
        print(">>> THRESHOLD FALLBACK FIRED — no LLM call made")
        return "I don't have information about that."

    prompt = build_prompt(query, chunks, sources)
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return {
        "answer": response.choices[0].message.content,
        "sources": list(set(sources)),
        "used_fallback": False
    }


if __name__ == "__main__":
    print(generate_answer("What is prompt injection and how do you prevent it?")["answer"])
    print("\n---\n")
    print(generate_answer("What are the core functions of the AI RMF?")["answer"])
    print("\n---\n")
    print(generate_answer("What's the best programming language for beginners?")["answer"])
    print("\n---\n")
    print(generate_answer("What does GDPR say about AI risk management?")["answer"])