from dotenv import load_dotenv
load_dotenv()

from src.evaluation.metrics import faithfulness_score, answer_relevancy_score, context_precision, context_recall
from src.rag.pipeline import RAGPipeline
from src.evaluation.golden_set import GOLDEN_SET
from src.evaluation.regression import check_regression


def run_eval():
    pipeline = RAGPipeline()

    faithfulness_scores = []
    relevancy_scores = []
    precision_scores = []
    recall_scores = []

    for case in GOLDEN_SET:
        query = case["query"]
        result = pipeline.answer(query)

        f_score, _ = faithfulness_score(result["answer"], result["full_context"])
        r_score = answer_relevancy_score(query, result["answer"])
        precision = context_precision(result["sources"], case["expected_sources"])
        recall = context_recall(query, result["full_context"])

        faithfulness_scores.append(f_score)
        relevancy_scores.append(r_score.score)
        precision_scores.append(precision)
        recall_scores.append(1.0 if recall.sufficient else 0.0)

        print(f"[faith {f_score:.2f} | relev {r_score.score}/5 | prec {precision:.2f} | recall {recall.sufficient}] {query}")
        print(f"   {result['answer'][:120]}...")
        if not recall.sufficient:
            print(f"   recall reasoning: {recall.reasoning}")
        print()

    avg_scores = {
        "faithfulness": sum(faithfulness_scores) / len(faithfulness_scores),
        "answer_relevancy": sum(relevancy_scores) / len(relevancy_scores) / 5,  # normalized to 0-1
        "context_precision": sum(precision_scores) / len(precision_scores),
        "context_recall": sum(recall_scores) / len(recall_scores),
    }

    print(f"Averages: {avg_scores}\n")

    regressions = check_regression(avg_scores)
    for r in regressions:
        print(r)


if __name__ == "__main__":
    run_eval()