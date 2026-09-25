"""Per-model pricing, in USD per 1M tokens. Update if OpenAI changes pricing."""

PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int = 0) -> float:
    if model not in PRICING:
        print(f"[pricing] warning: no pricing entry for '{model}', using gpt-4o-mini rates")
        model = "gpt-4o-mini"
    rates = PRICING[model]
    return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates["output"]