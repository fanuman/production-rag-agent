"""Reads every call ever recorded (logs/cost_log.jsonl) - not just the current
process's memory - so cost visibility survives across separate CLI/eval runs."""
import json
from pathlib import Path

LOG_PATH = Path("logs/cost_log.jsonl")


def print_report():
    if not LOG_PATH.exists():
        print("No cost log yet - run some queries first.")
        return

    total, hypothetical_total, by_label, count = 0.0, 0.0, {}, 0
    with open(LOG_PATH) as f:
        for line in f:
            entry = json.loads(line)
            total += entry["cost_usd"]
            hypothetical_total += entry.get("cost_if_gpt4o_usd", 0)
            by_label[entry["label"]] = by_label.get(entry["label"], 0) + entry["cost_usd"]
            count += 1

    print(f"Total calls: {count}")
    print(f"Actual cost (current model): ${total:.6f}")
    print(f"Cost if every call had run on gpt-4o instead: ${hypothetical_total:.6f}")
    if total > 0:
        print(f"Current setup is {hypothetical_total / total:.1f}x cheaper than always using gpt-4o")
    print("\nBy pipeline stage:")
    for label, cost in sorted(by_label.items(), key=lambda x: -x[1]):
        print(f"  {label}: ${cost:.6f}")


if __name__ == "__main__":
    print_report()