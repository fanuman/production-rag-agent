import json
import os

BASELINE_PATH = "src/evaluation/baseline_scores.json"
REGRESSION_THRESHOLD = 0.1  # calibrate this against real run-to-run variance before trusting it

def check_regression(current_scores: dict) -> list[str]:
    if not os.path.exists(BASELINE_PATH):
        save_as_baseline(current_scores)
        return ["No baseline existed - saved current scores as the new baseline."]

    with open(BASELINE_PATH) as f:
        baseline = json.load(f)

    regressions = []
    for metric, current_value in current_scores.items():
        baseline_value = baseline.get(metric, 0)
        if current_value < baseline_value - REGRESSION_THRESHOLD:
            regressions.append(f"{metric}: {baseline_value:.2f} -> {current_value:.2f} (regression)")
    return regressions


def save_as_baseline(current_scores: dict):
    with open(BASELINE_PATH, "w") as f:
        json.dump(current_scores, f, indent=2)