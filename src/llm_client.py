import time
import random
import os
from openai import (
    OpenAI, RateLimitError, APIConnectionError,
    APITimeoutError, InternalServerError,
    AuthenticationError, BadRequestError,
    OpenAIError, NotFoundError
)

# Approximate pricing per 1M tokens — check OpenAI's current pricing page
# before relying on this for real budget decisions
PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

class ProductionLLMClient:
    def __init__(self, model="gpt-4o-mini", max_retries=4, base_delay=1.0):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not found in environment. "
                "Check `.env` exists and load_dotenv() is called, "
                "or re-export it in this terminal session."
            )

        try:
            self.client = OpenAI(api_key=api_key)
        except OpenAIError as e:
            raise RuntimeError(f"Failed to initialize OpenAI client: {e}") from e

        self.model = model
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.total_cost = 0.0
        self.total_calls = 0
        self.total_retries = 0

    def _calculate_cost(self, usage):
        pricing = PRICING.get(self.model, {"input": 0, "output": 0})
        input_cost = (usage.prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (usage.completion_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def chat(self, messages, **kwargs):
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    **kwargs
                )
                self.total_cost += self._calculate_cost(response.usage)
                self.total_calls += 1
                return response

            except (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError) as e:
                self.total_retries += 1
                if attempt == self.max_retries - 1:
                    print(f"Failed after {self.max_retries} attempts: {e}")
                    raise
                wait_time = self.base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Transient error ({type(e).__name__}), retrying in {wait_time:.1f}s "
                      f"(attempt {attempt + 1}/{self.max_retries})")
                time.sleep(wait_time)

            except (AuthenticationError, BadRequestError, NotFoundError) as e:
                # Permanent — retrying is pointless, fail immediately
                print(f"Permanent error, not retrying: {e}")
                raise

    def report(self):
        print(f"Total calls: {self.total_calls} | Retries: {self.total_retries} | "
              f"Estimated cost: ${self.total_cost:.6f}")