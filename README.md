# Production RAG Agent — TrailPeak Outdoors Assistant

An agent-powered RAG chatbot, built incrementally over 4 weeks and deployed on AWS with CI/CD,
logging/monitoring, and evaluation metrics.

This repo isn't rewritten each week — it grows. Each Saturday's project builds directly on top of
the last, and the git tags below let you see it evolve from a basic chatbot into a deployed,
agent-powered production system. Check the tag history rather than just the latest commit to see
that progression.

As of Week 3, this project answers questions for **TrailPeak Outdoors**, a fictional outdoor gear
retailer — product details and store policies come from RAG over real documents, while current
price and stock come from a live function-calling tool. Weeks 1–2 used a different corpus (AI
governance/security documents); the underlying engineering carried over unchanged, only the
subject matter and the documents changed.

## Status

**Week 3 complete** — real-time SSE streaming frontend, a live function-calling tool combined
with RAG retrieval, and a hand-built evaluation harness (faithfulness + answer relevancy) run
against the live pipeline. See [Milestones](#milestones) below for what's next.

## Tech stack

**Implemented so far:**
- Python 3.13
- FastAPI + uvicorn
- OpenAI API (`gpt-4o-mini`, `text-embedding-3-small`) — chat, structured output, function
  calling, and streaming
- Docker
- Chroma (vector store)
- `langchain-text-splitters` (recursive chunking)
- Server-Sent Events (SSE) for real-time token streaming to the browser
- A hand-built RAG evaluation harness (faithfulness + answer relevancy, LLM-as-judge)

**Planned (upcoming weeks):**
- AWS (Lambda/EC2, API Gateway, CloudWatch, Secrets Manager)
- GitHub Actions (CI/CD)
- LangGraph (multi-agent orchestration)
- Hybrid search / re-ranking
- Retry/cost-tracking protection extended to RAG calls (currently only `/chat` has it — a known,
  flagged gap; see [Known gaps](#known-gaps) below)

## Architecture

The project is built around a shared core, a set of pluggable tools, and a `RAGPipeline` class
that ties retrieval, tool use, and generation together — with three thin entrypoints (CLI, HTTP,
streaming HTTP) on top.

```
        cli.py              api/main.py (/chat, /ask, /ask/stream)
     (terminal chat)          (FastAPI service)
            \                       /
             \                     /
              core/llm_client.py (used by /chat only)
              rag/pipeline.py -- RAGPipeline (used by /ask, /ask/stream)
                     |                    \
                     |                     \
         core/embeddings.py          tools/inventory_tool.py
         core/vectorstore.py          (CheckAvailability - live
                     |                  price/stock, self-registers
                     |                  with the pipeline)
               Docker image
           (runs any entrypoint)

  data/*.txt --ingest.py--> chroma_db/ <-- RAGPipeline.retrieve()
  (offline, one-time)      (persisted index)   (runtime, per-request)

  evaluation/run_eval.py --> RAGPipeline.answer() --> evaluation/metrics.py
  (offline, golden dataset)                            (faithfulness + relevancy scoring)
```

**`core/`** — shared infrastructure with no domain logic: `config.py` (model names, relevance
threshold, retrieval k — one source of truth instead of scattered hardcoded values),
`embeddings.py` and `vectorstore.py` (single implementations, previously duplicated between
ingestion and the RAG pipeline), and `llm_client.py` (`ProductionLLMClient` — exponential backoff
retries, fail-fast on permanent/config errors, per-call cost tracking; currently used only by the
plain `/chat` endpoint, not yet by RAG — see Known gaps).

**`tools/`** — function-calling tools the RAG pipeline can invoke. `inventory_tool.py` defines
`CheckAvailability` (live price/stock lookup by SKU) and self-registers its schema and handler, so
the pipeline aggregates available tools rather than hand-assembling them — a new tool file
following the same pattern is picked up automatically.

**`rag/`** — `pipeline.py` holds the `RAGPipeline` class: `retrieve()` (semantic search),
`.answer()` (structured, self-audited final answer with real source attribution — the model
reports which retrieved sources it actually used, not just which were retrieved), and
`.answer_stream()` (the same retrieval and tool-decision logic, but streamed token-by-token via
SSE). `prompts.py` holds the answer-generation prompt, which explicitly allows the model to reason
across multiple retrieved chunks to reach a conclusion (e.g., inferring "no" from an explicit
supported-list, rather than requiring the exact answer to appear verbatim) and explicitly directs
price/stock questions to the `CheckAvailability` tool instead of the retrieved text.

**`evaluation/`** — a hand-built RAG eval harness, not a third-party library, so every scoring
mechanism is fully understood rather than treated as a black box. `metrics.py` implements
**faithfulness** (does the answer only make claims supported by what the pipeline actually saw —
retrieved chunks *and* tool output) and **answer relevancy** (does the answer address the
question, independent of correctness), both via LLM-as-judge with structured output. `run_eval.py`
runs a golden dataset through `RAGPipeline` and reports both scores per question.

**`ingest.py`** — offline, one-time pipeline: reads source `.txt` documents, chunks them (800
chars, 150 overlap), embeds each chunk, and stores them in a persisted Chroma collection tagged by
source filename. Run manually whenever source documents change.

**`api/main.py`** + **`api/models.py`** — the FastAPI service:
- `GET /health` — liveness check
- `POST /chat` — plain chatbot, no document grounding (Week 1)
- `POST /ask` — RAG + tool-calling Q&A, with self-audited source attribution
- `POST /ask/stream` — the same pipeline, streamed via SSE. Sends a named `sources` event first,
  then streams answer tokens, then a `[DONE]` signal
- `GET /cost` — running totals for calls, retries, and estimated spend (currently `/chat` only —
  see Known gaps)

**`frontend/index.html`** — a real browser chat UI using `fetch()` + a manual `ReadableStream`
reader (not the browser's built-in `EventSource`, which can't send a POST body). Parses the named
SSE `sources` event separately from the token stream, displays citations under each answer, and
disables input while a response is streaming.

## Project structure

```
production-rag-agent/
├── src/
│   ├── cli.py
│   ├── ingest.py
│   ├── core/
│   │   ├── config.py
│   │   ├── embeddings.py
│   │   ├── vectorstore.py
│   │   └── llm_client.py
│   ├── tools/
│   │   ├── inventory_tool.py
│   │   └── inventory.json
│   ├── rag/
│   │   ├── prompts.py
│   │   └── pipeline.py
│   ├── evaluation/
│   │   ├── prompts.py
│   │   ├── metrics.py
│   │   └── run_eval.py
│   └── api/
│       ├── main.py
│       └── models.py
├── frontend/
│   └── index.html
├── data/                    # source .txt documents (not committed — see Setup)
├── chroma_db/               # persisted vector index (not committed, shipped in the image)
├── infra/
│   └── Dockerfile
├── requirements.txt
└── .env                     # not committed — see Setup
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

**3. Source documents**

Place these in `data/` (not committed to git) — a product catalog and three store policies:
`product_catalog.txt`, `shipping_policy.txt`, `returns_policy.txt`, `warranty_policy.txt`.
Live inventory data (price/stock, not embedded — used by the `CheckAvailability` tool) lives at
`src/tools/inventory.json`.

**4. Run ingestion** (one-time, or whenever source documents change)
```bash
python -m src.ingest
```
Builds `chroma_db/` locally. Costs a fraction of a cent in embedding calls for this corpus size.

**5a. Run the CLI locally**
```bash
python -m src.cli
```

**5b. Run the API locally**
```bash
uvicorn src.api.main:app --reload
```
Interactive docs at `http://localhost:8000/docs`, or:
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message": "Is the SummitCarry backpack in stock, and what does it cost?"}'
```

**5c. Run the frontend**

Open `frontend/index.html` directly in a browser while the API is running locally — it talks to
`http://localhost:8000/ask/stream`.

**6. Run the eval harness**
```bash
python -m src.evaluation.run_eval
```
Runs the golden dataset through the live pipeline and prints faithfulness + relevancy scores per
question — an offline check, deliberately kept off the live request path (running eval inline on
every user request would roughly double latency and cost for a number the user never asked for).

**7. Run in Docker**
```bash
docker build -f infra/Dockerfile -t production-rag-agent .
docker run --env-file .env -p 8000:8000 production-rag-agent
```
Run as a CLI instead of the default API:
```bash
docker run --env-file .env -it production-rag-agent python -m src.cli
```

## Known gaps

Flagged deliberately rather than fixed silently — real trade-offs made under time constraints,
worth closing before Week 4's capstone:

- **RAG calls have no retry protection.** `ProductionLLMClient`'s exponential backoff only wraps
  `/chat`. `RAGPipeline` makes its own unwrapped `OpenAI()` calls — a transient network error
  during `/ask` currently fails outright instead of retrying.
- **`/cost` doesn't include RAG or tool-calling spend** — only tracks `/chat` usage, for the same
  reason as above.
- **The streaming endpoint's source list is less precise than the non-streaming one.** `/ask` uses
  a second, self-audited LLM call to report only the sources actually used in the answer; `/ask/stream`
  uses the simpler retrieved-sources list (streaming and a validated structured-output call are in
  real tension — see commit history for the full reasoning), so it can occasionally include a
  retrieved-but-unused source.

## Milestones

| Tag | Week | What it adds | Status |
|-----|------|---------------|--------|
| `v0.1-week1-chatbot` | 1 | Containerized CLI/API chatbot, production error handling, cost tracking | ✅ Done |
| `v0.2-week2-rag` | 2 | RAG over a real multi-document corpus, source attribution | ✅ Done |
| `v0.3-week3-frontend` | 3 | SSE streaming frontend, function calling + RAG, eval harness | ✅ Done |
| `v1.0-capstone` | 4 | Agent-powered, deployed on AWS, CI/CD, monitored | ⬜ Upcoming |

## Live demo

_(added once deployed — Week 4)_