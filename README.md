# Production RAG Agent

An agent-powered RAG chatbot, built incrementally over 4 weeks and deployed on AWS with CI/CD,
a web frontend, logging/monitoring, and evaluation metrics.

This repo isn't rewritten each week — it grows. Each Saturday's project builds directly on top of
the last, and the git tags below let you see it evolve from a basic chatbot into a deployed,
agent-powered production system. Check the tag history rather than just the latest commit to see
that progression.

## Status

**Week 1 complete** — containerized CLI/API chatbot with production-grade error handling and
cost tracking. See [Milestones](#milestones) below for what's next.

## Tech stack

**Implemented so far:**
- Python 3.13
- FastAPI + uvicorn
- OpenAI API (`gpt-4o-mini`)
- Docker

**Planned (upcoming weeks):**
- LangChain, vector DB (Chroma locally → Pinecone/pgvector)
- JS frontend
- AWS (Lambda/EC2, API Gateway, CloudWatch, Secrets Manager)
- GitHub Actions (CI/CD)
- LangGraph (multi-agent orchestration)

## Architecture

The project is built around one shared core with two thin, independent entrypoints — a design
choice made specifically to avoid duplicating retry/error-handling/cost-tracking logic between a
terminal tool and an HTTP service.

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
```

**`llm_client.py`** — `ProductionLLMClient`: wraps the OpenAI API with exponential backoff retry
for transient errors (rate limits, timeouts, server errors), fail-fast handling for permanent
errors (invalid requests, bad model names) and configuration errors (missing API key), and
per-call cost tracking based on real token usage.

**`cli.py`** — a terminal chat loop using the shared client directly. Maintains conversation
history across turns, prints a cost summary on exit.

**`api/main.py`** + **`api/models.py`** — a FastAPI service exposing the same client over HTTP:
- `GET /health` — liveness check
- `POST /chat` — send a message, get a reply (Pydantic-validated request/response)
- `GET /cost` — running totals for calls, retries, and estimated spend

Both entrypoints depend on the same core and share no duplicated logic — a bug fix or feature
added to `llm_client.py` benefits both automatically.

## Project structure

```
production-rag-agent/
├── src/
│   ├── llm_client.py       # shared core: retries, error handling, cost tracking
│   ├── cli.py              # terminal entrypoint
│   └── api/
│       ├── main.py          # FastAPI app and endpoints
│       └── models.py        # Pydantic request/response schemas
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

**3a. Run the CLI locally**
```bash
python -m src.cli
```

**3b. Run the API locally**
```bash
uvicorn src.api.main:app --reload
```
Then visit `http://localhost:8000/docs` for interactive API docs, or:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 2+2?"}'
```

**4. Run in Docker**

Build once:
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
| `v0.2-week2-rag` | 2 | RAG over local documents | ⬜ Upcoming |
| `v0.3-week3-frontend` | 3 | Web frontend + evaluation metrics | ⬜ Upcoming |
| `v1.0-capstone` | 4 | Agent-powered, deployed on AWS, CI/CD, monitored | ⬜ Upcoming |

## Live demo

_(added once deployed — Week 4)_