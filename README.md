# Production RAG Agent — TrailPeak Outdoors Assistant

An agent-powered RAG chatbot, built incrementally over 4 weeks and deployed on AWS with CI/CD,
IAM-managed secrets, and monitoring.

This repo wasn't rewritten each week — it grew. Each Saturday's project built directly on the
last: a containerized chatbot (Week 1) became a real RAG pipeline over a governance corpus (Week
2), then pivoted domains and gained function calling (Week 3), then became a genuine multi-step
agent deployed to real cloud infrastructure with a full CI/CD pipeline (Week 4). The git tags below
trace that progression; check tag history, not just the latest commit, to see it.

## Status: v1.0 — capstone complete

The assistant answers questions for **TrailPeak Outdoors**, a fictional outdoor gear retailer.
Product details and store policies come from RAG over real documents; current price and stock come
from live function-calling tools; multi-step requests (checking several products, then totaling
their cost) are handled by a genuine ReAct agent loop, not a single tool call. The app runs on EC2
behind Docker, built and pushed automatically by GitHub Actions to ECR on every push, with its
OpenAI API key supplied entirely by AWS Secrets Manager via an EC2 instance role — no access key or
`.env` secret exists on the deployed server at all.

## Tech stack

- Python 3.13, FastAPI + uvicorn
- OpenAI API (`gpt-4o-mini`, `text-embedding-3-small`) — chat, structured output, function
  calling, streaming
- Docker, deployed on EC2
- Chroma (vector store)
- AWS: IAM (users + roles), EC2, S3, Secrets Manager, CloudWatch (logs + alarms), ECR
- GitHub Actions (CI/CD: test → build → push to ECR)
- A hand-built RAG evaluation harness (faithfulness + answer relevancy, LLM-as-judge)
- A separate, scoped-down AWS Lambda + API Gateway deployment (Mangum), demonstrating a second
  deployment model for `/health` + `/chat` only — see Known gaps below for why the full pipeline
  isn't deployed this way

## Architecture

```
                    cli.py                  api/main.py (/chat, /ask, /ask/stream)
                 (terminal chat)              (FastAPI service)
                        \                          /
                         \                        /
                    core/llm_client.py (used by /chat only)
                    core/secrets.py -- Secrets Manager fetch, .env fallback for local dev
                    rag/pipeline.py -- RAGPipeline
                               |                    \
                               |                     \
                   core/embeddings.py,          tools/inventory_tool.py (CheckAvailability)
                   core/vectorstore.py          tools/calculator_tool.py (CalculateTotal)
                               |                (both self-register with the pipeline)
                         Docker image
                    (built by GitHub Actions,
                     pushed to ECR, pulled and
                     run on EC2)

  data/*.txt --ingest.py--> chroma_db/ <-- RAGPipeline.retrieve()
  (rebuilt from source        (persisted        (runtime, per-request)
   on every CI run, not        in the image)
   committed as a binary)

  evaluation/run_eval.py --> RAGPipeline.answer() --> evaluation/metrics.py
```

**`rag/pipeline.py`** — `RAGPipeline` runs a genuine ReAct loop (Day 16's pattern): the model can
call `CheckAvailability` and `CalculateTotal` in sequence, with each step's input depending on the
real output of the step before it (e.g., totaling two products' prices only after actually looking
both up) — not a single round of tool calling. A `max_iterations` cap fails safely, reporting
incompleteness honestly rather than guessing from partial steps if the loop can't converge.

**`core/secrets.py`** — fetches `OPENAI_API_KEY` from AWS Secrets Manager at startup via `boto3`,
authenticating through whatever identity is already available (an EC2 instance role in
production, `numan-dev`'s local AWS credentials in dev) — no access key is ever placed on a
server. Falls back to `.env` (with a logged warning, not a silent swallow) if Secrets Manager is
unreachable, so local development without AWS credentials configured still works.

**`ingest.py`** — rebuilds the Chroma index from `data/*.txt` on every run (deletes and recreates
the collection first, guaranteeing a clean rebuild rather than accumulating stale or colliding
chunk IDs). Chunk IDs are content-derived hashes (filename + position), not a raw incrementing
counter — fixes a real bug found this project where adding a new source document could silently
shift and collide with existing chunk IDs. Run automatically as a CI step before every image build,
so the deployed index is always provably derived from the current source documents, never a stale
or manually-copied artifact.

**`.github/workflows/`** — a two-job pipeline: `test` (fast import-checks targeting real bugs
found this project — missing `src.` prefixes, missing `global` declarations) gates
`build-and-push` (rebuilds the vector index from source, builds the Docker image, pushes to ECR
tagged by both commit SHA and `latest`).

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
│   │   ├── llm_client.py
│   │   └── secrets.py
│   ├── tools/
│   │   ├── inventory_tool.py
│   │   ├── calculator_tool.py
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
├── infra/
│   ├── Dockerfile
│   └── lambda/
│       └── lambda_app.py
├── data/                    # original source documents - committed, not gitignored
├── chroma_db/               # persisted index - gitignored, rebuilt from source every time
├── .github/workflows/
├── requirements.txt
└── .env                     # local dev fallback only - not committed
```

## Setup and run

**1. Install dependencies**
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Local config** — create `.env` in the repo root with `OPENAI_API_KEY=sk-...`. This is used
directly for local development; in production, Secrets Manager takes over automatically.

**3. Run ingestion** (one-time, or whenever `data/*.txt` changes)
```bash
python -m src.ingest
```

**4a. Run locally**
```bash
uvicorn src.api.main:app --reload
```
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message": "How much would the StormShield jacket and TrekLight poles cost together?"}'
```

**4b. Run via Docker**
```bash
docker build -f infra/Dockerfile -t production-rag-agent .
docker run --env-file .env -p 8000:8000 production-rag-agent
```

**5. Deploy to EC2** (see `docs/` in commit history for the full walkthrough) — launch a `t3.micro`
with the `production-rag-agent-ec2-role` instance profile attached (grants Secrets Manager read +
ECR pull, nothing more), then on the instance:
```bash
aws ecr get-login-password --region eu-north-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.eu-north-1.amazonaws.com
docker pull <account-id>.dkr.ecr.eu-north-1.amazonaws.com/production-rag-agent:latest
docker run -p 8000:8000 -d <account-id>.dkr.ecr.eu-north-1.amazonaws.com/production-rag-agent:latest
```
No `--env-file` needed here — the instance role supplies the OpenAI key via Secrets Manager
directly.

**6. Run the eval harness** (offline, deliberately not on the live request path)
```bash
python -m src.evaluation.run_eval
```

## Known gaps

- **The full RAG pipeline isn't deployed via Lambda.** `infra/lambda/lambda_app.py` demonstrates
  serverless deployment for a scoped-down `/health` + `/chat` subset only — Lambda's package size
  limits and lack of persistent local disk make the locally-persisted Chroma index a poor fit
  without further work (S3-backed loading, EFS, or a managed vector store like Pinecone).
- **EC2 has no CloudWatch monitoring wired up** the way the Lambda deployment does (Day 20's
  alarm + structured logging were built against the Lambda function specifically, not the EC2
  service) — a reasonable next step, not done here.
- **A narrow retrieval edge case**: some natural phrasings of meta-questions ("what does your
  company sell") don't score well enough against `about_us.txt` to beat the relevance threshold,
  and confirmed that raising the threshold isn't a safe fix (a known-irrelevant query scored
  better than a second genuine meta-question in testing) — the real fix is more naturally-phrased
  content in `about_us.txt`, not a threshold change. Tracked in `ai-learning-journal`'s known
  issues list.
- **The streaming endpoint's source list is less precise** than the non-streaming one, for reasons
  explained in-line in `rag/pipeline.py` (a validated structured-output pass and true token
  streaming are in real tension).
- **The frontend (`frontend/index.html`) is intentionally minimal** — functional, not polished.
  A dedicated visual-design pass is planned as separate, future work outside this roadmap.

## Milestones

| Tag | Week | What it added | Status |
|-----|------|---------------|--------|
| `v0.1-week1-chatbot` | 1 | Containerized CLI/API chatbot, production error handling, cost tracking | ✅ |
| `v0.2-week2-rag` | 2 | RAG over a real multi-document corpus, source attribution | ✅ |
| `v0.3-week3-frontend` | 3 | SSE streaming frontend, function calling + RAG, eval harness | ✅ |
| `v1.0-capstone` | 4 | Genuine multi-step agent, deployed on EC2 + ECR + CI/CD, Secrets Manager, IAM roles | ✅ |

## Live demo

Deployed on a `t3.micro` EC2 instance — terminated between active use to avoid ongoing cost (see
`ai-learning-journal`'s cleanup checklist). Redeploy via the steps in section 5 above; the image is
always current in ECR via the CI/CD pipeline.


## Quick redeploy (after terminating the EC2 instance)

The instance is deliberately terminated between active use to avoid ongoing cost. Spinning it back
up takes about 5 minutes:

**1. Launch a new instance**
- EC2 Console → Launch instance
- Name: `production-rag-agent-server`
- AMI: **Ubuntu Server** (24.04 or newer LTS)
- Instance type: **t3.micro**
- Key pair: **`prod-rag-pair`** (should still be listed — key pairs survive termination)
- Security group: select the **existing** group from before, if it's still listed, rather than
  rebuilding rules from scratch
- **Advanced details → IAM instance profile**: select **`production-rag-agent-ec2-role`** —
  this is the step that's easy to forget, and without it the app can't reach Secrets Manager

**2. Update the security group for your current IP**
Your IP likely changed since last time. Before connecting:
```bash
curl ifconfig.me
```
EC2 → Security Groups → the group attached to this instance → Edit inbound rules → update both
the SSH (22) and Custom TCP (8000) rules to **"My IP"** (auto-detects the current one).

**3. SSH in and install what's needed** (a fresh instance has nothing pre-installed)
```bash
ssh -i prod-rag-pair.pem ubuntu@<new-public-ip>
sudo apt update
sudo apt install -y docker.io awscli
sudo usermod -aG docker $USER
exit
ssh -i prod-rag-pair.pem ubuntu@<new-public-ip>   # reconnect for the group change to apply
```

**4. Confirm the instance role is actually attached before pulling anything**
```bash
aws sts get-caller-identity
```
Should show `assumed-role/production-rag-agent-ec2-role/...` — if it shows an error instead, the
IAM instance profile wasn't attached at launch; fix via EC2 → instance → Actions → Security →
Modify IAM role.

**5. Pull and run the latest image** (CI/CD keeps this current on every push to `main`)
```bash
aws ecr get-login-password --region eu-north-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.eu-north-1.amazonaws.com
docker pull <account-id>.dkr.ecr.eu-north-1.amazonaws.com/production-rag-agent:latest
docker run -p 8000:8000 -d <account-id>.dkr.ecr.eu-north-1.amazonaws.com/production-rag-agent:latest
```
No `--env-file` needed — the instance role supplies the OpenAI key via Secrets Manager directly.

**6. Verify it's actually working, not just running**
```bash
curl http://<new-public-ip>:8000/health
curl -X POST http://<new-public-ip>:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message": "Is the SummitCarry backpack in stock, and what does it cost?"}'
```
Expect `$249.00, out of stock` — the known-good result used to verify every deployment this
project.

**7. If testing the frontend against this live instance**
Update `API_BASE` in `frontend/index.html` from `http://localhost:8000` to
`http://<new-public-ip>:8000`, then reopen the file in a browser.

**8. When done — terminate again, not just stop**