"""Per-request cost tracking. Every OpenAI call in the pipeline reports its
usage here; pricing.py is the single source of truth for dollar amounts."""
import json
import time
from pathlib import Path
from src.cost.pricing import estimate_cost

LOG_PATH = Path("logs/cost_log.jsonl")


class CostTracker:
    def __init__(self):
        self.records = []

    def record(self, model: str, input_tokens: int, output_tokens: int, label: str) -> float:
        cost = estimate_cost(model, input_tokens, output_tokens)
        hypothetical_gpt4o_cost = estimate_cost("gpt-4o", input_tokens, output_tokens)
        entry = {
            "timestamp": time.time(),
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "cost_if_gpt4o_usd": hypothetical_gpt4o_cost,
            "label": label,
        }
        self.records.append(entry)
        LOG_PATH.parent.mkdir(exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return cost


cost_tracker = CostTracker()