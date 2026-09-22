# Production RAG Agent — TrailPeak Outdoors Assistant

An agent-powered RAG chatbot, built incrementally over 5+ weeks and deployed on AWS with CI/CD,
IAM-managed secrets, semantic caching, rate limiting, infrastructure defined as code, LLM tracing,
and automated regression/A-B evaluation.

This repo wasn't rewritten each week — it grew. Each Saturday's project built directly on the
last: a containerized chatbot (Week 1) became a real RAG pipeline over a governance corpus (Week
2), then pivoted domains and gained function calling (Week 3), then became a genuine multi-step
agent deployed to real cloud infrastructure with a full CI/CD pipeline (Week 4), then gained
multi-container local dev, Redis-backed caching and rate limiting, and a Terraform-defined
ECS/Fargate deployment replacing hand-clicked console setup (Week 5), then gained LangSmith
tracing, context precision/recall metrics, and an automated regression + A/B testing harness
(Week 6, in progress). The git tags below trace that progression; check tag history, not just the
latest commit, to see it.

## Status: v1.1 — Week 5 infrastructure complete, Week 6 observability + evaluation underway

The assistant answers questions for **TrailPeak Outdoors**, a fictional outdoor gear retailer.
Product details and store policies come from RAG over real documents; current price and stock come
from live function-calling tools; multi-step requests (checking several products, then totaling
their cost) are handled by a genuine ReAct agent loop, not a single tool call. Repeated or
paraphrased questions can be served from a Redis-backed semantic cache instead of re-running the
full pipeline, and every expensive endpoint is rate-limited. Every request through the
non-streaming path is traced end-to-end in LangSmith — retrieval, agent iterations, tool calls,
and cache hits/misses, all visible as one structured trace rather than raw logs. A golden-set
evaluation harness scores every response on faithfulness, answer relevancy, context precision, and
context recall, with automated regression detection against a saved baseline and an A/B test
runner for comparing prompt variants. The app is defined as three containers — `app`, `chroma`,
`redis` — run together via Docker Compose locally and deployed to ECS/Fargate through Terraform,
with the OpenAI API key supplied entirely by AWS Secrets Manager via an IAM task role — no access
key or `.env` secret exists on the deployed infrastructure at all.

## Tech stack

- Python 3.13, FastAPI + uvicorn
- OpenAI API (`gpt-4o-mini`, `text-embedding-3-small`) — chat, structured output, function
  calling, streaming
- Docker, Docker Compose (local multi-container dev: app + Chroma server + Redis)
- Chroma (vector store), run as its own networked server, not embedded in the app
- Redis (`redis-stack-server`, RediSearch) — semantic response caching, keyed by embedding
  distance rather than exact query match
- `slowapi` — Redis-backed rate limiting, correct across multiple app instances, not just a
  single process
- LangSmith (`langsmith`, `@traceable`) — per-request tracing of retrieval, the agent loop, and
  tool calls, used standalone (not via LangChain, since the pipeline is hand-built on raw OpenAI
  SDK calls)
- AWS: IAM (users + roles), EC2, S3, Secrets Manager, CloudWatch (logs + alarms), ECR, ECS/Fargate
- Terraform — the primary infrastructure definition for ECS/Fargate: cluster, IAM roles, security
  group, task definition, service, all as reviewable code rather than console clicks
- GitHub Actions (CI/CD: test → build → push to ECR)
- Locust — load testing, used to verify rate limiting and caching under real concurrent traffic
- A hand-built RAG evaluation harness — faithfulness, answer relevancy, context precision, context
  recall (LLM-as-judge where needed), run against a fixed golden set, with baseline-based
  regression detection and an A/B test runner for comparing prompt variants
- A separate, scoped-down AWS Lambda + API Gateway deployment (Mangum), demonstrating a second
  deployment model for `/health` + `/chat` only — see Known gaps below for why the full pipeline
  isn't deployed this way

## Architecture

```
                    cli.py                  api/main.py (/chat, /ask, /ask/stream)
                 (terminal chat)              (FastAPI, rate-limited via slowapi)
                        \                          /
                         \                        /
                    core/llm_client.py (used by /chat only)
                    core/secrets.py -- Secrets Manager fetch, .env fallback for local dev
                    rag/pipeline.py -- RAGPipeline (use_cache flag)
                               |         |          \
                               |         |           \
                   core/embeddings.py  core/       tools/inventory_tool.py (CheckAvailability)
                   core/vectorstore.py semantic_   tools/calculator_tool.py (CalculateTotal)
                        |              cache.py    (both self-register with the pipeline)
                        |              (Redis,
                        |               tool-using/failed
                        |               answers never cached)
                        |
                  Chroma (own container,          Redis (own container,
                  networked, not embedded)         RediSearch + rate-limit counters)

  answer(), retrieve(), and _run_agent_loop() are @traceable -->  LangSmith
  (non-streaming path only; nested calls form one request tree per query)

  Three containers - app, chroma, redis - defined once in docker-compose.yml (local dev)
  and once in infra/terraform/ecs.tf (ECS/Fargate). Same shape, two environments.

  data/*.txt --ingest.py--> chroma_db/ <-- RAGPipeline.retrieve()
  (run manually, post-deploy,        (a fresh collection reference is
   against whichever Chroma           fetched on every call - not
   is currently live)                 cached at startup)

  golden_set.py --> run_eval.py --> RAGPipeline.answer() (use_cache=True)
                                  --> metrics.py (faithfulness, relevancy,
                                                   context precision/recall)
                                  --> regression.py (vs. saved baseline)

  golden_set.py --> ab_test.py --> two RAGPipeline instances (use_cache=False,
                                    different final_answer_instruction)
                                 --> metrics.py --> side-by-side comparison
```

**`rag/pipeline.py`** — `RAGPipeline` runs a genuine ReAct loop (Day 16's pattern): the model can
call `CheckAvailability` and `CalculateTotal` in sequence, with each step's input depending on the
real output of the step before it (e.g., totaling two products' prices only after actually looking
both up) — not a single round of tool calling. A `max_iterations` cap fails safely, reporting
incompleteness honestly rather than guessing from partial steps if the loop can't converge.
`answer()`, `retrieve()`, and `_run_agent_loop()` are decorated `@traceable`, so every
non-streaming request produces one nested LangSmith trace matching the real call structure with
no manual wiring. A `use_cache` constructor flag (default `True`) lets evaluation code bypass the
semantic cache entirely — without it, a cache hit silently reuses a *previous* pipeline
configuration's answer, which broke the A/B test's independence between variants before the flag
was added (see Known gaps for the residual scoring implication).

**`evaluation/`** — `golden_set.py` holds a fixed set of test questions with expected sources, the
shared baseline both regression testing and A/B testing compare against. `metrics.py` scores
faithfulness and answer relevancy (LLM-as-judge, structured output) plus context precision
(deterministic — checks retrieved source *files* against expected ones) and context recall
(LLM-judged — did retrieval find *enough*, tolerant of irrelevant content mixed in). `regression.py`
saves a baseline and flags any future run where a metric drops by more than a threshold.
`ab_test.py` runs the golden set through two differently-configured pipelines and compares real
scores rather than eyeballing sample answers.

**`core/semantic_cache.py`** — `SemanticCache` checks whether an incoming query is close enough
(cosine distance over its embedding) to a previously answered query to reuse that answer instead
of re-running retrieval and generation. Deliberately never caches an answer that used a tool
(live price/stock data would go stale) or a fallback/incomplete answer (a cached failure would
become a *recurring* failure for the cache's TTL). `REDIS_HOST` is read from the environment,
defaulting to Compose's `"redis"` DNS name locally; ECS's task definition overrides it to
`"localhost"`, since containers within one Fargate task share a network interface rather than
getting individual service DNS names the way Compose provides.

**`retrieve()` fetches its Chroma collection fresh on every call**, not once at pipeline
construction — a deliberate fix, not an oversight. Caching the collection reference at startup
could be worked around on Docker Compose (restart the `app` container alone, `chroma`'s data
survives), but has no equivalent on ECS: any task replacement is a wholly new task with an empty
Chroma, so the old restart-based workaround would loop the same failure indefinitely there.

**`core/secrets.py`** — fetches `OPENAI_API_KEY` from AWS Secrets Manager at startup via `boto3`,
authenticating through whatever identity is already available (an IAM role in production,
`numan-dev`'s local AWS credentials in dev) — no access key is ever placed on a server. Falls back
to `.env` (with a logged warning, not a silent swallow) if Secrets Manager is unreachable, so
local development without AWS credentials configured still works.

**`ingest.py`** — deletes and recreates the Chroma collection from `data/*.txt` on every run,
guaranteeing a clean rebuild rather than accumulating stale or colliding chunk IDs. Chunk IDs are
content-derived hashes (filename + position), not a raw incrementing counter. Run manually,
post-deployment, against whichever Chroma instance is currently live — no longer a CI step (see
Known gaps for why that changed).

**`.github/workflows/`** — a two-job pipeline: `test` (fast import-checks) gates `build-and-push`
(builds the Docker image, pushes to ECR tagged by both commit SHA and `latest`).

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
│   │   ├── secrets.py
│   │   └── semantic_cache.py
│   ├── tools/
│   │   ├── inventory_tool.py
│   │   ├── calculator_tool.py
│   │   └── inventory.json
│   ├── rag/
│   │   ├── prompts.py
│   │   └── pipeline.py       # answer/retrieve/_run_agent_loop are @traceable; use_cache flag
│   ├── evaluation/
│   │   ├── prompts.py
│   │   ├── metrics.py         # faithfulness, relevancy, context precision/recall
│   │   ├── golden_set.py      # fixed test questions + expected sources
│   │   ├── regression.py      # baseline save/compare
│   │   ├── ab_test.py         # compare two pipeline configurations
│   │   ├── baseline_scores.json  # gitignored - generated locally, not committed
│   │   └── run_eval.py
│   └── api/
│       ├── main.py
│       └── models.py
├── frontend/
│   └── index.html
├── infra/
│   ├── Dockerfile
│   ├── lambda/
│   │   └── lambda_app.py
│   └── terraform/
│       ├── providers.tf
│       ├── data.tf
│       ├── iam.tf
│       ├── variables.tf
│       ├── ecs.tf
│       └── terraform.tfvars    # gitignored - personal IP, not committed
├── data/                    # original source documents - committed, not gitignored
├── chroma_db/               # persisted index - gitignored, rebuilt from source every time
├── docker-compose.yml
├── locustfile.py
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

**2b. Optional: enable LangSmith tracing** — add to `.env`:
```
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=production-rag-agent
```
Traces appear at smith.langchain.com under the `production-rag-agent` project. Only the
non-streaming `/ask` path is traced (see Known gaps). Without these variables set, the app runs
identically — `@traceable` is a no-op if tracing isn't configured.

**3. Run locally via Docker Compose** (recommended — matches the deployed three-container shape)
```bash
docker compose up --build
```
Then, in a separate terminal, ingest into the running stack:
```bash
CHROMA_HOST=localhost CHROMA_PORT=8001 python -m src.ingest
```
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"message": "How much would the StormShield jacket and TrekLight poles cost together?"}'
```

**4. Run without Compose** (Chroma/Redis run separately, or point at a remote instance)
```bash
uvicorn src.api.main:app --reload
```

**5. Deploy to ECS/Fargate via Terraform (current, recommended deployment path)**

```bash
cd infra/terraform
echo 'my_ip = "YOUR_IP/32"' > terraform.tfvars   # curl ifconfig.me for the value
terraform init
terraform plan    # read this before applying - it's cheap insurance
terraform apply
```

Registers a three-container task (`app`, `chroma`, `redis`), a cluster, IAM roles, a security
group, and a CloudWatch log group. Get the running task's public IP:
```bash
aws ecs list-tasks --cluster production-rag-agent-tf-cluster --query 'taskArns[0]' --output text
aws ecs describe-tasks --cluster production-rag-agent-tf-cluster --tasks <task-arn> --query 'tasks[0].attachments[0].details' --output table
aws ec2 describe-network-interfaces --network-interface-ids <eni-id> --query 'NetworkInterfaces[0].Association.PublicIp' --output text
```
Then ingest once against the fresh (empty) Chroma:
```bash
CHROMA_HOST=<task-ip> CHROMA_PORT=8001 python -m src.ingest
```
**Every task replacement means a brand-new, empty Chroma** — ingestion is a required step after
every `terraform apply` that touches the task definition, or after
`aws ecs update-service --force-new-deployment`, not a one-time setup step.

**When done:** `terraform destroy` — tears down every resource Terraform created, in the correct
dependency order, in one command. No manual cleanup checklist needed for anything defined here.

**Alternate path — manual EC2 deployment (kept for reference, not actively maintained)**

The original Month 1 deployment model, predating Redis/Compose. See "Quick redeploy (EC2)" below
for the full walkthrough. Would need updating to match the current three-container setup if used
going forward — the current, actively-maintained deployment path is Terraform/ECS above.

**6. Load test** (against a local Compose stack, not live AWS infrastructure)
```bash
locust -f locustfile.py --host=http://localhost:8000
```
Opens a web UI at `localhost:8089`.

**7. Run the evaluation harness** (offline, deliberately not on the live request path). Both
commands below need Chroma/Redis reachable — via Compose (`CHROMA_HOST=localhost
CHROMA_PORT=8001 REDIS_HOST=localhost`) or another live instance.

```bash
python -m src.evaluation.run_eval
```
Scores the golden set on faithfulness, answer relevancy, context precision, and context recall.
First run saves a baseline (`baseline_scores.json`, gitignored); later runs flag any metric that
drops by more than `REGRESSION_THRESHOLD` (currently an uncalibrated initial guess — see Known
gaps).

```bash
python -m src.evaluation.ab_test
```
Compares two `final_answer_instruction` variants on the same golden set, with `use_cache=False`
on both — required, since a cache hit would silently return one variant's old answer to the
other's test, invalidating the comparison.

## Known gaps

- **Chroma has no persistent storage in the ECS deployment.** Task replacement (a redeploy, a
  forced restart) always starts with an empty Chroma, requiring manual re-ingestion every time. A
  real fix — EFS-backed storage, or a managed vector store — is future work, not done here.
- **Two mislabeled content bugs found via LangSmith trace inspection, not yet fixed:**
  `product_catalog.txt`'s SummitCarry Backpack entry contains a chunk of tent-specific content
  (DAC poles, rainfly, "tent body" in the included-items list) — almost certainly a copy-paste
  error. Similarly, a "REFUND TIMING" section in the returns/warranty policy content actually
  describes warranty proof-of-purchase requirements, not refund processing time. **Confirmed that
  context precision and context recall, as currently designed, cannot detect either bug** —
  precision only checks retrieved source *files* (both bugs sit inside correctly-named files), and
  recall is deliberately tolerant of irrelevant content as long as sufficient correct content is
  present alongside it. Both need a dedicated data-quality pass; a future "does each chunk's
  content match its claimed topic" check would be a different kind of metric than either.
- **A real content gap found via `context_recall`**: no tent in the catalog is actually rated for
  winter camping — the only tent (AlpinePeak) is explicitly 3-season only. Not a bug; a genuine
  product-catalog limitation worth a business decision (add a winter-rated SKU, or make the
  limitation explicit in the assistant's answer).
- **`REGRESSION_THRESHOLD` (0.1) is an initial guess, not calibrated** against actual measured
  run-to-run LLM-judge variance. A live example was found during Day 27's A/B testing: the same
  question, essentially the same answer text, scored `faithfulness` 0.33 in one run and 1.00 in
  another purely from judge inconsistency — exactly the kind of noise the threshold needs to
  tolerate without either missing real regressions or crying wolf constantly.
- **`context_precision` depends on `parsed.sources_used`**, which is the model's own self-reported
  list of sources from the final structured-output call, not an independently verified ground
  truth — some precision variance between otherwise-similar runs may come from this self-report
  shifting slightly rather than retrieval itself changing.
- **`SemanticCache` never captures `sources`** — every cached response permanently returns
  `sources: []`, even though the original (non-cached) answer had real sources. This also means
  any cached answer scores `context_precision: 0.0` by construction (empty source list), unrelated
  to real retrieval quality — evaluation code must run with `use_cache=False` to get meaningful
  precision scores. A known, minor gap in `SemanticCache.store()`'s signature, not fixed yet.
- **Only the non-streaming path is traced.** `answer_stream()` uses `yield`; tracing a generator
  correctly needs more care than the current `@traceable` setup provides, so `/ask/stream`
  requests currently produce no LangSmith trace at all.
- **The full RAG pipeline isn't deployed via Lambda.** `infra/lambda/lambda_app.py` demonstrates
  serverless deployment for a scoped-down `/health` + `/chat` subset only — Lambda's package size
  limits and lack of persistent local disk make the locally-persisted Chroma index a poor fit
  without further work.
- **The EC2 deployment path predates Redis/Compose and is not actively maintained** — the current,
  actively-used deployment model is the Terraform/ECS path above.
- **`terraform.tfvars` (the real IP value) is per-person and gitignored** — anyone else running
  this Terraform config needs to supply their own before `apply` will work.
- **A narrow retrieval edge case**: some natural phrasings of meta-questions ("what does your
  company sell") don't score well enough against `about_us.txt` to beat the relevance threshold,
  and raising the threshold isn't a safe fix (a known-irrelevant query scored better than a second
  genuine meta-question in testing) — the real fix is more naturally-phrased content in
  `about_us.txt`, not a threshold change.
- **The semantic cache is deliberately conservative** — real testing found that paraphrased
  questions can score *farther apart* in embedding distance than genuinely different questions on
  adjacent topics, so the threshold favors missing some real cache hits over ever risking a wrong
  cached answer.
- **The streaming endpoint's source list is less precise** than the non-streaming one — a
  validated structured-output pass and true token streaming are in real tension.
- **The frontend (`frontend/index.html`) points at a hardcoded `API_BASE`** — update it manually
  to match wherever the app is currently deployed.

## Milestones

| Tag | Week | What it added | Status |
|-----|------|---------------|--------|
| `v0.1-week1-chatbot` | 1 | Containerized CLI/API chatbot, production error handling, cost tracking | ✅ |
| `v0.2-week2-rag` | 2 | RAG over a real multi-document corpus, source attribution | ✅ |
| `v0.3-week3-frontend` | 3 | SSE streaming frontend, function calling + RAG, eval harness | ✅ |
| `v1.0-capstone` | 4 | Genuine multi-step agent, deployed on EC2 + ECR + CI/CD, Secrets Manager, IAM roles | ✅ |
| `v1.1-week5-infra` | 5 | Docker Compose, ECS/Fargate via Terraform, semantic caching (Redis), rate limiting, load testing | ✅ |
| _(Week 6, in progress)_ | 6 | LangSmith tracing, context precision/recall, regression + A/B testing harness, fine-tuning fundamentals, managed model serving, cost optimization | 🔄 |

## Live demo

Deployed on ECS/Fargate via Terraform — destroyed between active use to avoid ongoing cost
(`terraform destroy`). Redeploy via the steps in section 5 above; the image is always current in
ECR via the CI/CD pipeline.

## Quick redeploy (EC2 — legacy path, see Known gaps)

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
**Note:** this runs `app` alone, without `chroma`/`redis` as separate containers — the legacy
embedded-mode assumptions no longer match `vectorstore.py`/`semantic_cache.py`'s current networked
design. This path needs updating before it will actually work as-is.

**6. When done — terminate again, not just stop**

## Cleanup checklist (end of roadmap)

- [x] ~~ECS service/cluster (Day 22, console-created)~~ - deleted same-day, 0 clusters confirmed
- [x] ~~Terraform-managed ECS resources (Week 5 project)~~ - `terraform destroy` run, confirmed
      0 running tasks, service INACTIVE
- [ ] Lambda function `production-rag-chat` + its API Gateway HTTP API (Day 18)