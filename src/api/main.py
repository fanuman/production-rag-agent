from contextlib import asynccontextmanager


from dotenv import load_dotenv
load_dotenv()
from src.core.secrets import load_secret_into_env
load_secret_into_env()

from src.core.llm_client import ProductionLLMClient
from src.rag.pipeline import RAGPipeline
from src.api.models import ChatRequest, ChatResponse, ChatMetaData, RagRequest, RagResponse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request


llm_client = None
rag_pipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm_client, rag_pipeline
    llm_client = ProductionLLMClient()
    rag_pipeline = RAGPipeline()
    yield

app = FastAPI(lifespan=lifespan)

limiter = Limiter(key_func=get_remote_address, storage_uri="redis://redis:6379/0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
def chat(request: Request, chat_request: ChatRequest):
    try:
        response = llm_client.chat([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": chat_request.message}
        ])
        return ChatResponse(
            reply=response.choices[0].message.content,
            total_cost=llm_client.total_cost
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


@app.get("/cost", response_model=ChatMetaData)
def cost():
    return ChatMetaData(
        total_calls=llm_client.total_calls,
        total_retries=llm_client.total_retries,
        total_cost=llm_client.total_cost
    )


@app.post("/ask", response_model=RagResponse)
@limiter.limit("10/minute")
def ask(request: Request, rag_request: RagRequest):
    try:
        result = rag_pipeline.answer(rag_request.message)
        return RagResponse(
            reply=result["answer"],
            sources=result["sources"],
            used_fallback=result["used_fallback"],
            from_cache=result["from_cache"],
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


@app.post("/ask/stream")
@limiter.limit("10/minute")
def ask_stream(request: Request, rag_request: RagRequest):
    return StreamingResponse(rag_pipeline.answer_stream(rag_request.message), media_type="text/event-stream")
