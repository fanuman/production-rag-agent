from dotenv import load_dotenv
load_dotenv()

from src.evaluation.metrics import faithfulness_score, answer_relevancy_score
from src.rag.pipeline import RAGPipeline

golden_dataset = [
    "Is the SummitCarry backpack in stock, and what does it cost?",
    "What's your return policy on hiking boots?",
    "Do you ship to Germany?",
    "What's the warranty on the AlpinePeak tent?",
    "Can I return a water filter I already opened?",
]


def run_eval():
    pipeline = RAGPipeline()
    for q in golden_dataset:
        result = pipeline.answer(q)
        f_score, _ = faithfulness_score(result["answer"], result["full_context"])
        r_score = answer_relevancy_score(q, result["answer"])
        print(f"[{f_score:.2f} | {r_score.score}/5] {q}")
        print(f"   {result['answer'][:120]}...\n")


if __name__ == "__main__":
    run_eval()
