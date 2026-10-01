from pydantic import BaseModel, Field, field_validator

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message cannot be blank or whitespace-only")
        return v

class ChatResponse(BaseModel):
    reply: str
    total_cost: float

class ChatMetaData(BaseModel):
    total_calls: int
    total_retries: int
    total_cost: float

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