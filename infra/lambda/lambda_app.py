# lambda_app.py
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from mangum import Mangum
from src.core.llm_client import ProductionLLMClient
from pydantic import BaseModel

llm_client = ProductionLLMClient()  # module level - built once per warm container

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/chat")
def chat(request: ChatRequest):
    try:
        response = llm_client.chat([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": request.message}
        ])
        return {"reply": response.choices[0].message.content}
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))

handler = Mangum(app)