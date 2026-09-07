def build_answer_prompt(query, chunks, sources):
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


FINAL_ANSWER_INSTRUCTION = (
    "Now provide your final answer. In sources_used, list only the "
    "source document filenames whose content you actually relied on "
    "to construct THIS answer - not every document you were given."
)
