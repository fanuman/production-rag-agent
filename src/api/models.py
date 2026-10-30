from pydantic import BaseModel, Field, field_validator

class CostSummary(BaseModel):
    """What GET /cost returns: totals from logs/cost_log.jsonl (every model call the app has made)."""
    total_calls: int
    total_cost_usd: float
    cost_if_gpt4o_usd: float
    by_stage: dict[str, float]

class RagRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message cannot be blank or whitespace-only")
        return v

class RagResponse(BaseModel):
    reply: str
    sources: list[str]
    used_fallback: bool
    from_cache: bool = False