"""Reads every call ever recorded (logs/cost_log.jsonl) - not just the current
process's memory - so cost visibility survives across separate CLI/eval runs."""
import json
from pathlib import Path

LOG_PATH = Path("logs/cost_log.jsonl")


def summarize():
    """Add up every recorded call. Returns zeros when there is no log yet.
    Used by both the terminal report below and the API's GET /cost, so they always agree."""
    total, hypothetical_total, by_label, count = 0.0, 0.0, {}, 0
    if LOG_PATH.exists():
        with open(LOG_PATH) as f:
            for line in f:
                entry = json.loads(line)
                total += entry["cost_usd"]
                hypothetical_total += entry.get("cost_if_gpt4o_usd", 0)
                by_label[entry["label"]] = by_label.get(entry["label"], 0) + entry["cost_usd"]
                count += 1
    return {
        "total_calls": count,
        "total_cost_usd": total,
        "cost_if_gpt4o_usd": hypothetical_total,
        "by_stage": by_label,
    }


def print_report():
    if not LOG_PATH.exists():
        print("No cost log yet - run some queries first.")
        return

    summary = summarize()
    total, hypothetical_total = summary["total_cost_usd"], summary["cost_if_gpt4o_usd"]

    print(f"Total calls: {summary['total_calls']}")
    print(f"Actual cost (current model): ${total:.6f}")
    print(f"Cost if every call had run on gpt-4o instead: ${hypothetical_total:.6f}")
    if total > 0:
        print(f"Current setup is {hypothetical_total / total:.1f}x cheaper than always using gpt-4o")
    print("\nBy pipeline stage:")
    for label, cost in sorted(summary["by_stage"].items(), key=lambda x: -x[1]):
        print(f"  {label}: ${cost:.6f}")


if __name__ == "__main__":
    print_report()