from pydantic import BaseModel
from typing import List
from openai import OpenAI

from src.core.config import DEFAULT_MODEL
from src.evaluation.prompts import (
    extract_claims_prompt, verify_claim_prompt, answer_relevancy_prompt, 
    context_recall_prompt, REFUSAL_PHRASES
)

_client = OpenAI()


class Claims(BaseModel):
    claims: List[str]

class ClaimVerdict(BaseModel):
    supported: bool
    reasoning: str

class RelevancyScore(BaseModel):
    score: int  # 1-5
    reasoning: str

class RecallVerdict(BaseModel):
    sufficient: bool
    reasoning: str


def extract_claims(answer: str) -> list[str]:
    response = _client.chat.completions.parse(
        model=DEFAULT_MODEL,
        messages=[{"role": "user", "content": extract_claims_prompt(answer)}],
        response_format=Claims
    )
    return response.choices[0].message.parsed.claims


def verify_claim(claim: str, context: str) -> ClaimVerdict:
    response = _client.chat.completions.parse(
        model=DEFAULT_MODEL,
        messages=[{"role": "user", "content": verify_claim_prompt(claim, context)}],
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
    response = _client.chat.completions.parse(
        model=DEFAULT_MODEL,
        messages=[{"role": "user", "content": answer_relevancy_prompt(question, answer)}],
        response_format=RelevancyScore
    )
    return response.choices[0].message.parsed


def context_precision(retrieved_sources: list[str], expected_sources: list[str]) -> float:
    """Deterministic - no LLM call. Of the sources actually retrieved, what
    fraction were genuinely relevant? Note: this checks source FILES, not
    chunk CONTENT - a mislabeled chunk inside a correct source file won't
    be caught here (see Day 26's tent-content bug in product_catalog.txt)."""
    if not retrieved_sources:
        return 0.0
    relevant = sum(1 for s in retrieved_sources if s in expected_sources)
    return relevant / len(retrieved_sources)

def context_recall(question: str, context: str) -> RecallVerdict:
    """LLM-judged - did retrieval find ENOUGH to answer, even with noise
    mixed in alongside it? Complements context_precision: precision checks
    whether retrieved SOURCES were relevant, recall checks whether the
    CONTENT was sufficient - catching a case precision alone can't see."""
    response = _client.chat.completions.parse(
        model=DEFAULT_MODEL,
        messages=[{"role": "user", "content": context_recall_prompt(question, context)}],
        response_format=RecallVerdict
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
