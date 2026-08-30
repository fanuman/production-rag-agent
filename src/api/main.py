from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from src.llm_client import ProductionLLMClient
from src.rag import generate_answer
from src.api.models import ChatRequest, ChatResponse, ChatMetaData, RagRequest, RagResponse

from fastapi import FastAPI, HTTPException


llm_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm_client
    llm_client = ProductionLLMClient()
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        response = llm_client.chat([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": request.message}
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
def ask(request: RagRequest):
    try:
        result = generate_answer(request.message)
        return RagResponse(
            reply=result["answer"],
            sources=result["sources"],
            used_fallback=result["used_fallback"]
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))