# Infrastructure runbooks

How to deploy, rotate, and tear down the three-container stack (`app`, `chroma`, `redis`). The main
[README](../README.md) explains what the system is; this file is the step-by-step part.

| Where | What it defines |
|---|---|
| `Dockerfile` | The image CI builds and pushes to ECR (copies `src/`, `data/` and `frontend/`; no `--reload`) |
| `terraform/` | ECS/Fargate: cluster, IAM roles, security group, task definition, service, plus CloudWatch monitoring (`monitoring.tf`) |
| `k8s/` | The same three containers as Kubernetes Deployments + Services, for Minikube |
| `lambda/` | A scoped-down Lambda + API Gateway deployment of `/health` and `/chat` only |
| `../docker-compose.yml` | The local three-container stack |

Contents: [Deploy to ECS/Fargate](#deploy-to-ecsfargate-with-terraform-current-recommended-path) ·
[Rotate the OpenAI API key](#rotate-the-openai-api-key) · [Kubernetes on Minikube](#kubernetes-on-minikube) ·
[Legacy: manual EC2](#quick-redeploy-ec2--legacy-path-see-known-gaps) · [Cleanup checklist](#cleanup-checklist-end-of-roadmap)

## Deploy to ECS/Fargate with Terraform (current, recommended path)

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

Redeploys: the image in ECR is always current, because the CI/CD pipeline builds and pushes it on every push to `main`.
The deployment is destroyed between active use to avoid ongoing cost.

## Rotate the OpenAI API key

No code change is needed: `secrets.py` already fetches the key from Secrets Manager at app startup, so task
replacement already re-fetches fresh secrets.

1. Generate a new key on platform.openai.com
2. `aws secretsmanager put-secret-value --secret-id production-rag-agent/openai-api-key --secret-string '{"OPENAI_API_KEY":"sk-NEW-KEY"}' --region eu-north-1`
3. `aws ecs update-service --cluster production-rag-agent-tf-cluster --service <service-name> --force-new-deployment --region eu-north-1`
4. Confirm new tasks are healthy, *then* revoke the old key on platform.openai.com

During a rotation, `secrets.py` can silently fall back to the environment if Secrets Manager fails; see the related
gap in the [main README's Known gaps](../README.md#known-gaps).

## Kubernetes on Minikube

The same three-container shape (`app`, `chroma`, `redis`) as Compose and ECS, redefined as Deployments + Services
(`infra/k8s/`) and run locally on Minikube. A Kubernetes Secret supplies the OpenAI key in place of ECS's Secrets
Manager injection.

```
infra/k8s/*.yaml (app, chroma, redis - Deployment + Service each)
     --> Minikube (local single-node cluster)
     (same three-container shape as docker-compose.yml / ecs.tf, third
      environment's answer to service discovery: Kubernetes Service DNS
      names ("chroma", "redis") rather than Compose's built-in DNS or
      ECS's shared-network-interface "localhost")
```

The manifests are `k8s/redis.yaml`, `k8s/chroma.yaml` and `k8s/app.yaml` (`CHROMA_HOST`/`REDIS_HOST` are Service DNS
names; the `openai-secret` Secret is injected through `secretKeyRef`). No EKS cluster has been deployed; see Known gaps
in the [main README](../README.md#known-gaps) for why.

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
