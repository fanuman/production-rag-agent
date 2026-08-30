from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str
    total_cost: float

class ChatMetaData(BaseModel):
    total_calls: int
    total_retries: int
    total_cost: float

class RagRequest(BaseModel):
    message: str

class RagResponse(BaseModel):
    reply: str
    sources: list[str]
    used_fallback: bool