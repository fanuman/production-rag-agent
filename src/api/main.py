from contextlib import asynccontextmanager


from dotenv import load_dotenv
load_dotenv()
from src.core.secrets import load_secret_into_env
load_secret_into_env()

from src.rag.pipeline import RAGPipeline
from src.api.streaming import sse_stream
from src.api.models import CostSummary, RagRequest, RagResponse
from src.cost.report import summarize

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request

import os
import logging
from pathlib import Path

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
logger = logging.getLogger(__name__)

rag_pipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag_pipeline
    rag_pipeline = RAGPipeline()
    yield

app = FastAPI(lifespan=lifespan)

limiter = Limiter(key_func=get_remote_address, storage_uri=f"redis://{REDIS_HOST}:6379/0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SlowAPIMiddleware)
# The UI is served by this app (same origin), so no CORS is needed by default.
# Only if you host the UI somewhere else: CORS_ORIGINS="https://my-ui.example.com,http://localhost:5173"
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/cost", response_model=CostSummary)
def cost():
    """Totals for every model call the app has made, read from logs/cost_log.jsonl
    (the same numbers as `python -m src.cost.report`)."""
    return CostSummary(**summarize())


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
    except Exception:
        logger.exception("/ask failed")
        raise HTTPException(status_code=502, detail="Upstream error. Please try again.")


@app.post("/ask/stream")
@limiter.limit("10/minute")
def ask_stream(request: Request, rag_request: RagRequest):
    return StreamingResponse(
        sse_stream(rag_pipeline.answer_stream(rag_request.message)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},  # stop proxies from buffering the stream
    )


# Serve the web UI from this same app. Must stay LAST: a mount at "/" matches every path,
# so every API route above has to be registered before it.
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"   # /app/frontend inside Docker
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
