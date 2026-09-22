from dotenv import load_dotenv
load_dotenv()

from src.rag.pipeline import RAGPipeline
from src.rag.prompts import FINAL_ANSWER_INSTRUCTION
from src.evaluation.golden_set import GOLDEN_SET
from src.evaluation.metrics import faithfulness_score, answer_relevancy_score, context_precision, context_recall

VARIANT_B_INSTRUCTION = FINAL_ANSWER_INSTRUCTION + (
    "\n\nIf the retrieved context does not fully or directly answer the question, say so clearly "
    "rather than giving a partial answer that might read as complete."
)

VARIANTS = {
    "A (current)": None,
    "B (flag gaps explicitly)": VARIANT_B_INSTRUCTION,
}


def score_case(pipeline, case):
    query = case["query"]
    result = pipeline.answer(query)

    f_score, _ = faithfulness_score(result["answer"], result["full_context"])
    r_score = answer_relevancy_score(query, result["answer"])
    precision = context_precision(result["sources"], case["expected_sources"])
    recall = context_recall(query, result["full_context"])

    return {
        "faithfulness": f_score,
        "answer_relevancy": r_score.score / 5,
        "context_precision": precision,
        "context_recall": 1.0 if recall.sufficient else 0.0,
    }, result["answer"]


def run_ab_test():
    all_results = {}

    for label, instruction in VARIANTS.items():
        pipeline = RAGPipeline(final_answer_instruction=instruction, use_cache=False)
        case_scores = []

        print(f"\n=== {label} ===")
        for case in GOLDEN_SET:
            scores, answer = score_case(pipeline, case)
            case_scores.append(scores)
            print(f"[faith {scores['faithfulness']:.2f} | relev {scores['answer_relevancy']:.2f} | "
                  f"prec {scores['context_precision']:.2f} | recall {scores['context_recall']:.2f}] {case['query']}")
            print(f"   {answer[:150]}...")

        avg = {k: sum(s[k] for s in case_scores) / len(case_scores) for k in case_scores[0]}
        all_results[label] = avg

    print("\n=== Comparison ===")
    for label, avg in all_results.items():
        print(f"{label}: {avg}")

    return all_results


if __name__ == "__main__":
    run_ab_test()