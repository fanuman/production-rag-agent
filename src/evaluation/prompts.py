def extract_claims_prompt(answer: str) -> str:
    return f"""Break the following answer into a list of individual factual claims. Each claim should be a single, atomic statement.

When the answer describes a list or set as a group (e.g. "we ship to A, B, and C" or "the options are X, Y, and Z"), extract that as ONE claim describing the full set together - do not split a shared list into separate claims implying each item is exclusive or standalone.

Answer: {answer}"""


def verify_claim_prompt(claim: str, context: str) -> str:
    return f"""Context:
\"\"\"
{context}
\"\"\"

Claim: {claim}

Is this claim directly supported by the context above?"""


def answer_relevancy_prompt(question: str, answer: str) -> str:
    return f"""Question: {question}
Answer: {answer}

On a scale of 1-5, how well does this answer address the question?
1 = completely off-topic, 5 = directly and fully addresses the question.
Consider only whether it addresses the question, not whether it's factually correct."""


REFUSAL_PHRASES = ["i don't have information", "i don't know", "no document matches"]
