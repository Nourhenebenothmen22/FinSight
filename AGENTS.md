# FinSight — Agent Project Instructions

> Authoritative product specification: `docs/reference/FinSight cahier des charges du SaaS d'analyse financière multi-agents.pdf`
> Full engineering guidelines: [`CLAUDE.md`](./CLAUDE.md) and [`.claude/rules/skills-usage.md`](./.claude/rules/skills-usage.md)

## 1. Product & Compliance Rules
- FinSight is a multi-tenant SaaS for financial analysis (annual reports PDF + market data + news + quant/ML + Writer/Critic loop).
- **Mandatory legal disclaimer**: Display clearly in the UI and every report that FinSight provides financial analysis assistance and is **not investment advice**. Never generate personalized buy/sell recommendations.
- **No fabricated figures**: Every material figure must cite a document page or external source + timestamp.

## 2. Architecture & Local Stack (F0+)
- Monorepo: `/frontend` (Next.js 14, Tailwind CSS, Recharts), `/backend` (FastAPI, SQLAlchemy async, Alembic), `/infra`.
- Services:
  - `api` / `backend` (FastAPI, port `8000`)
  - `worker` (ARQ background worker)
  - `postgres` (PostgreSQL 16, port `5432`)
  - `redis` (Redis 7, port `6379`)
  - `qdrant` (Qdrant vector store, ports `6333`/`6334` — primary vector engine; `pgvector` is not used)
  - `garage` (Deuxfleurs Garage v2 S3-compatible object storage, S3 port `3900`, Admin port `3903`)
  - `ollama` (optional profile, port `11434`)

## 3. Security & Multi-Tenancy
- Every tenant-owned record carries `org_id`/`tenant_id`; enforce PostgreSQL Row-Level Security (RLS) and mandatory Qdrant `tenant_id` filters.
- Never commit secrets or `.env`; keep secrets out of logs and error responses.
- Keep billing in test/sandbox mode (`BillingProvider` abstraction).

## 4. Development & Git Workflow
- Read relevant skills before work (bridged from `~/.claude/skills` via `.agents/skills.json`): `code-architecture`, `code-audit`, `debugging`, `documentation`, `git-workflow`, `performance-audit`, `production-readiness`, `security-audit`, `testing`.
- Follow dependency order (F0 -> F22). Do not start dependent features prematurely.
- Use one `feature/<name>` branch per feature from `develop`, and never commit, push, merge, or run destructive commands without explicit user approval.
- Run and report exact lint, typecheck, test, migration, and build checks after changes.
