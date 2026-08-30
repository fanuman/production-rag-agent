# Production RAG Agent

An agent-powered RAG chatbot, built incrementally over 4 weeks and deployed on AWS with CI/CD,
a web frontend, logging/monitoring, and evaluation metrics.

This repo isn't rewritten each week — it grows. Each Saturday's project builds directly on top of
the last, and the git tags below let you see it evolve from a basic chatbot into a deployed,
agent-powered production system. Check the tag history rather than just the latest commit to see
that progression.

## Status

**Week 2 complete** — RAG over a real multi-document corpus (NIST AI RMF, NIST Generative AI
Profile, OWASP Top 10 for LLM Applications), with multi-document source attribution, served
alongside Week 1's chatbot. See [Milestones](#milestones) below for what's next.

## Tech stack

**Implemented so far:**
- Python 3.13
- FastAPI + uvicorn
- OpenAI API (`gpt-4o-mini`, `text-embedding-3-small`)
- Docker
- Chroma (vector store)
- `pypdf` (PDF text extraction)
- `langchain-text-splitters` (recursive chunking)

**Planned (upcoming weeks):**
- JS frontend
- AWS (Lambda/EC2, API Gateway, CloudWatch, Secrets Manager)
- GitHub Actions (CI/CD)
- LangGraph (multi-agent orchestration)
- Hybrid search / re-ranking

## Architecture

The project is built around one shared core with three thin, independent entrypoints — a design
choice made specifically to avoid duplicating retry/error-handling/cost-tracking logic between a
terminal tool, an HTTP service, and the RAG pipeline.

```
                cli.py              api/main.py
             (terminal chat)      (FastAPI service)
                    \                   /
                     \                 /
                      llm_client.py
                  (ProductionLLMClient)
                  retries, error handling,
                     cost tracking
                            |
                      Docker image
                  (runs either entrypoint)

  data/*.pdf --ingest.py--> chroma_db/ <--rag.py--> api/main.py (/ask)
  (offline, one-time)      (persisted index)      (runtime, per-request)
```

**`llm_client.py`** — `ProductionLLMClient`: wraps the OpenAI API with exponential backoff retry
for transient errors (rate limits, timeouts, server errors), fail-fast handling for permanent
errors (invalid requests, bad model names) and configuration errors (missing API key), and
per-call cost tracking based on real token usage.

**`cli.py`** — a terminal chat loop using the shared client directly. Maintains conversation
history across turns, prints a cost summary on exit.

**`ingest.py`** — offline, one-time pipeline: extracts text from source PDFs (`pypdf`), chunks it
with a recursive splitter (800 chars, 150 overlap), embeds each chunk (`text-embedding-3-small`),
and stores it in a persisted Chroma collection tagged with its source document. Run manually
whenever the source documents change — not run at request time or at Docker build time.

**`rag.py`** — the retrieval + generation pipeline: embeds the incoming question, retrieves the
top-k most similar chunks across all ingested documents, and generates a grounded answer that
cites which source document(s) it drew from. Falls back to "I don't have information about that"
either cheaply (via an empirically-tuned distance threshold, skipping the LLM call entirely when
retrieval clearly fails) or via the model itself refusing when retrieved content is topically
close but doesn't actually answer the question.

**`api/main.py`** + **`api/models.py`** — a FastAPI service exposing everything over HTTP:
- `GET /health` — liveness check
- `POST /chat` — plain chatbot, no document grounding (Week 1)
- `POST /ask` — document-grounded Q&A over the ingested PDF corpus, with source attribution
- `GET /cost` — running totals for calls, retries, and estimated spend

All entrypoints depend on the same core and share no duplicated logic.

## Project structure

```
production-rag-agent/
├── src/
│   ├── llm_client.py       # shared core: retries, error handling, cost tracking
│   ├── cli.py              # terminal entrypoint
│   ├── ingest.py           # offline: PDF -> chunks -> embeddings -> Chroma
│   ├── rag.py              # runtime: retrieve/build_prompt/generate_answer
│   └── api/
│       ├── main.py          # FastAPI app and endpoints
│       └── models.py        # Pydantic request/response schemas
├── data/                    # source PDFs (not committed - see Setup below)
├── chroma_db/               # persisted vector index (not committed, but shipped in the image)
├── infra/
│   └── Dockerfile
├── requirements.txt
└── .env                     # not committed — see Setup below
```

## Setup and run

**1. Install dependencies**
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Configure your API key**

Create a `.env` file in the repo root:
```
OPENAI_API_KEY=sk-your-key-here
```

**3. Download the source documents**

Place these three PDFs in a `data/` folder at the repo root (not committed to git):
- [NIST AI Risk Management Framework (AI RMF 1.0)](https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf)
- [NIST Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)
- [OWASP Top 10 for LLM Applications 2025](https://owasp.org/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf)

**4. Run ingestion** (one-time, or whenever source documents change)
```bash
python -m src.ingest
```
This builds `chroma_db/` locally. Costs a fraction of a cent in embedding calls for this corpus.

**5a. Run the CLI locally**
```bash
python -m src.cli
```

**5b. Run the API locally**
```bash
uvicorn src.api.main:app --reload
```
Then visit `http://localhost:8000/docs` for interactive API docs, or:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 2+2?"}'

curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message": "What is prompt injection and how do you prevent it?"}'
```

**6. Run in Docker**

Build once (bakes in the already-built `chroma_db/`, not the raw PDFs):
```bash
docker build -f infra/Dockerfile -t production-rag-agent .
```

Run as an API (default):
```bash
docker run --env-file .env -p 8000:8000 production-rag-agent
```

Run as a CLI instead (overrides the default command):
```bash
docker run --env-file .env -it production-rag-agent python -m src.cli
```

## Milestones

| Tag | Week | What it adds | Status |
|-----|------|---------------|--------|
| `v0.1-week1-chatbot` | 1 | Containerized CLI/API chatbot, production error handling, cost tracking | ✅ Done |
| `v0.2-week2-rag` | 2 | RAG over a real multi-document corpus, source attribution | ✅ Done |
| `v0.3-week3-frontend` | 3 | Web frontend + evaluation metrics | ⬜ Upcoming |
| `v1.0-capstone` | 4 | Agent-powered, deployed on AWS, CI/CD, monitored | ⬜ Upcoming |

## Live demo

_(added once deployed — Week 4)_