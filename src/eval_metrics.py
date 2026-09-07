# eval_metrics.py
from pydantic import BaseModel
from typing import List
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
openai_client = OpenAI()


class Claims(BaseModel):
    claims: List[str]

class ClaimVerdict(BaseModel):
    supported: bool
    reasoning: str

class RelevancyScore(BaseModel):
    score: int  # 1-5
    reasoning: str


REFUSAL_PHRASES = ["i don't have information", "i don't know", "no document matches"]

def extract_claims(answer: str) -> list[str]:
    prompt = f"""Break the following answer into a list of individual factual claims. Each claim should be a single, atomic statement.

    When the answer describes a list or set as a group (e.g. "we ship to A, B, and C" or "the options are X, Y, and Z"), extract that as ONE claim describing the full set together - do not split a shared list into separate claims implying each item is exclusive or standalone.


Answer: {answer}"""
    response = openai_client.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format=Claims
    )
    return response.choices[0].message.parsed.claims


def verify_claim(claim: str, context: str) -> ClaimVerdict:
    prompt = f"""Context:
\"\"\"
{context}
\"\"\"

Claim: {claim}

Is this claim directly supported by the context above?"""
    response = openai_client.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format=ClaimVerdict
    )
    return response.choices[0].message.parsed


def faithfulness_score(answer: str, context: str):
    if any(phrase in answer.lower() for phrase in REFUSAL_PHRASES):
        return 1.0, []  # a refusal makes no claims - nothing to verify
    
    claims = extract_claims(answer)
    if not claims:
        return 1.0, []  # no claims made -> nothing to be unfaithful about
    verdicts = [verify_claim(c, context) for c in claims]
    supported = sum(1 for v in verdicts if v.supported)
    return supported / len(claims), verdicts


def answer_relevancy_score(question: str, answer: str) -> RelevancyScore:
    prompt = f"""Question: {question}
Answer: {answer}

On a scale of 1-5, how well does this answer address the question?
1 = completely off-topic, 5 = directly and fully addresses the question.
Consider only whether it addresses the question, not whether it's factually correct."""
    response = openai_client.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format=RelevancyScore
    )
    return response.choices[0].message.parsed


if __name__ == "__main__":
    # Sanity-check against a hardcoded pair before trusting it against a real pipeline
    test_context = "Acme Corp's remote work policy allows employees to work from abroad for up to 45 days per year."
    test_answer = "You can work abroad for up to 45 days, and Acme also offers unlimited sick leave."

    score, verdicts = faithfulness_score(test_answer, test_context)
    print(f"Faithfulness: {score:.2f}")
    for v in verdicts:
        print(f"  {'✓' if v.supported else '✗'} {v.reasoning}")