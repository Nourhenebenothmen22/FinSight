# FinSight

**Multi-tenant SaaS platform for AI-powered financial analysis with source-backed citations.**

Upload an annual report (PDF) or enter a stock ticker, ask a natural-language question, and receive a structured, analyst-grade analysis where every material figure traces to a document page or external market source.

> ⚠️ **Disclaimer**: FinSight provides assistance with financial analysis and is **not investment advice**. Do not generate personalized buy/sell recommendations.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FinSight Monorepo                              │
├──────────────────┬────────────────────┬─────────────────────────────────────┤
│    Frontend      │      Backend       │           Infrastructure            │
│   (Next.js 14)   │    (FastAPI + ARQ) │          (Docker Compose)           │
│  Port: 3002      │   Port: 8000       │  • PostgreSQL 16  (5432)            │
│                  │                    │  • Qdrant         (6333/6334)       │
│  • Tailwind CSS  │  • SQLAlchemy 2.0  │  • Redis 7        (6379)            │
│  • Recharts      │  • Alembic         │  • Garage v2 S3   (3900 S3 / 3903)  │
│  • Vitest        │  • Pydantic v2     │  • Ollama (opt)   (11434)           │
│  • React 18      │  • JWT + Argon2id  │                                     │
└──────────────────┴────────────────────┴─────────────────────────────────────┘
```

### Multi-Agent Workflow (LangGraph)

```
START → budget_guard → supervisor → [RAG Filings, Market Data, News Sentiment, Quant/ML]
                                                ↓
                                         supervisor fan-in
                                                ↓
                                              writer → critic (loop up to plan limit)
                                                ↓
                                           human approval (interrupt)
                                                ↓
                                           PDF export → FINISH
```

---

## Quick Start

### Prerequisites

- Docker & Docker Compose v2+
- Git
- (Optional) Node.js 20+, Python 3.11+ for local development without containers

### 1. Configure Environment

```bash
# Copy environment template and fill in values
cp .env.example .env

# Generate required secrets (32+ bytes hex) and Garage S3 access key:
#   SECRET_KEY=$(openssl rand -hex 32)
#   GARAGE_RPC_SECRET=$(openssl rand -hex 32)
#   GARAGE_ADMIN_TOKEN=$(openssl rand -hex 32)
#   S3_ACCESS_KEY="GK$(openssl rand -hex 12)"
#   S3_SECRET_KEY=$(openssl rand -hex 32)
```

### 2. Start All Services & Apply Migrations

```bash
# Development (with hot reload)
docker compose up -d --build

# Apply PostgreSQL migrations
docker compose exec api alembic upgrade head

# Or with Ollama (local LLM fallback)
docker compose --profile ollama up -d --build
```

### 3. Verify

| Service | URL | Health Check |
|---|---|---|
| Frontend | http://localhost:3002 | Auto-loads health status |
| Backend API | http://localhost:8000 | `GET /health` (`200` healthy / `503` unhealthy) |
| API Docs | http://localhost:8000/docs | Swagger UI (dev only) |
| Garage S3 API | http://localhost:3900 | S3 API (checked via `garage-init` & API `/health`) |
| Garage Admin | http://localhost:3903/health | Returns `200 OK` when ready |
| Qdrant | http://localhost:6333/readyz | Readiness endpoint |

```bash
# Quick health checks
curl -f http://localhost:8000/health
curl -f http://localhost:8000/health/live
curl -f http://localhost:8000/health/ready
```

---

## Development

### Backend (FastAPI & ARQ Worker)

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Run API with hot reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run ARQ worker
arq app.worker.WorkerSettings

# Run tests
pytest -v

# Lint & format
ruff check . && ruff format --check .

# Type check
mypy app/

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

### Frontend (Next.js)

```bash
cd frontend

# Install dependencies
npm ci

# Run development server
npm run dev

# Run tests
npm run test        # headless
npm run test:ui     # with UI
npm run test:watch  # watch mode

# Lint & format
npm run lint
npm run format:check

# Type check
npm run typecheck

# Production build
npm run build
npm run start
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | JWT signing key (32+ chars, `openssl rand -hex 32`) |
| `POSTGRES_PASSWORD` | ✅ | PostgreSQL password |
| `GARAGE_RPC_SECRET` | ✅ | Garage RPC cluster secret (64 hex chars) |
| `GARAGE_ADMIN_TOKEN` | ✅ | Garage Admin API bearer token |
| `S3_ACCESS_KEY` | ✅ | Garage S3 access key (`GK` + 24 hex chars) |
| `S3_SECRET_KEY` | ✅ | Garage S3 secret key (64 hex chars) |
| `ADMIN_PASSWORD` | ✅ | Initial admin user password |
| `SMTP_HOST` / `SMTP_FROM` | ❌ | Optional SMTP host for verification/reset emails (logs in dev if unset) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | ❌ | Optional Google OAuth 2.0 credentials (F1+) |
| `RATE_LIMIT_PROFILE` / `TRUSTED_PROXY_CIDRS` | ❌ | `auto` (`relaxed_dev` in dev, forced `strict` in staging/prod; narrow proxy CIDRs required in prod) |
| `GROQ_API_KEY` | ❌ | Groq API key (F7+) |
| `GEMINI_API_KEY` | ❌ | Google Gemini API key (F7+) |
| `OPENROUTER_API_KEY` | ❌ | OpenRouter API key (F7+) |
| `STRIPE_SECRET_KEY` | ❌ | Stripe test key (F14+) |
| `LANGSMITH_API_KEY` | ❌ | LangSmith tracing (F19+) |

See [`.env.example`](./.env.example) for the complete list.

---

## Project Structure

```
FinSight/
├── .agents/
│   ├── rules/skills-usage.md         # Antigravity workflow rules
│   └── skills/                       # Project skills (code-audit, testing, security-audit, ...)
├── .github/workflows/ci.yml          # CI pipeline
├── .gitignore
├── .env.example
├── AGENTS.md                         # Project instructions & architecture rules
├── docker-compose.yml                # Local stack (api, worker, frontend, postgres, redis, qdrant, garage)
├── docker-compose.override.yml.example
├── README.md
├── docs/
│   ├── ARCHITECTURE.md
│   └── reference/
│       └── FinSight cahier des charges du SaaS d'analyse financière multi-agents.pdf
├── backend/
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       ├── 0001_f0_baseline.py
│   │       ├── 0002_f1_auth_tables.py
│   │       └── 0003_f2_tenants_rbac_and_rls.py
│   ├── app/
│   │   ├── main.py                   # FastAPI entry point + TenantContextMiddleware
│   │   ├── worker.py                 # ARQ worker (ping + auth/invitation email tasks)
│   │   ├── core/
│   │   │   ├── config.py             # Pydantic Settings
│   │   │   ├── security.py           # Argon2id, JWT, opaque tokens, OIDC JWKS
│   │   │   ├── database.py           # SQLAlchemy async engine, sessions & bind_tenant_rls
│   │   │   ├── redis.py              # Shared async Redis client
│   │   │   ├── queue.py              # ARQ task dispatcher
│   │   │   ├── rate_limit.py         # Hybrid Token Bucket + progressive login backoff (Redis Lua)
│   │   │   └── tenant_context.py     # Pure ASGI TenantContextMiddleware & X-Tenant-ID binding
│   │   ├── api/
│   │   │   ├── deps.py               # Auth, CSRF, TenantContext, get_tenant_db, require_org_roles, actor rate limits
│   │   │   └── routes/
│   │   │       ├── auth.py           # /api/v1/auth/* (register, login, refresh, verify, forgot, reset, google, me, sessions)
│   │   │       ├── orgs.py           # /api/v1/orgs/* & /api/v1/invitations/accept (workspaces, RBAC, invitations, audit logs)
│   │   │       └── health.py         # GET /health, /health/ready, /health/live
│   │   ├── models/
│   │   │   ├── base.py               # Base, UUIDMixin, TimestampMixin
│   │   │   ├── auth.py               # User, RefreshToken, AuthToken
│   │   │   └── tenant.py             # OrgRole, Organization, Membership, OrganizationInvitation, AuditLog
│   │   ├── schemas/
│   │   │   ├── auth.py               # Auth request/response models
│   │   │   ├── tenant.py             # Tenant, RBAC, invitation & audit log schemas
│   │   │   └── health.py             # HealthResponse, HealthStatus
│   │   └── services/
│   │       ├── auth.py               # Registration, login, token rotation, reset, OAuth (+ personal org provisioning)
│   │       ├── audit.py              # Tenant audit logging helper
│   │       ├── tenant.py             # Workspace CRUD, RBAC enforcement, invitations & audit queries
│   │       └── email.py              # SMTP / dev logging email sender
│   └── tests/
│       ├── conftest.py
│       ├── test_auth_endpoints.py
│       ├── test_auth_security.py
│       ├── test_core.py
│       ├── test_health.py
│       ├── test_rate_limit_redis.py
│       ├── test_rate_limiting.py
│       ├── test_tenant_rls_postgres.py
│       └── test_tenants_rbac.py
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.js
│   ├── tailwind.config.ts
│   ├── .eslintrc.json
│   ├── prettier.config.js
│   ├── vitest.config.ts
│   ├── Dockerfile
│   ├── public/
│   │   ├── icon.svg
│   │   └── manifest.json
│   ├── src/
│   │   ├── app/
│   │   │   ├── api/backend/[...path]/route.ts
│   │   │   ├── auth/google/callback/page.tsx
│   │   │   ├── forgot-password/page.tsx
│   │   │   ├── invitations/accept/page.tsx
│   │   │   ├── login/page.tsx
│   │   │   ├── profile/page.tsx
│   │   │   ├── register/page.tsx
│   │   │   ├── reset-password/page.tsx
│   │   │   ├── verify-email/page.tsx
│   │   │   ├── workspaces/page.tsx
│   │   │   ├── workspaces/[orgId]/page.tsx
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── auth/                 # AuthProvider, WorkspaceProvider, AuthCard, GoogleOAuthButton, PasswordInput, PasswordRulesList
│   │   │   ├── HealthStatus.tsx
│   │   │   ├── LegalDisclaimer.tsx
│   │   │   └── Navbar.tsx
│   │   └── lib/
│   │       ├── api.ts
│   │       ├── auth.ts
│   │       ├── orgs.ts
│   │       └── validations/          # auth.ts, orgs.ts
│   └── tests/
│       ├── setup.ts
│       ├── auth-pages.test.tsx
│       ├── auth-validation.test.ts
│       ├── health.test.tsx
│       ├── proxy.test.ts
│       └── workspaces.test.tsx
└── infra/
    ├── postgres/init.sql
    ├── qdrant/config.yaml
    ├── redis/redis.conf
    └── garage/
        ├── garage.toml
        └── init_buckets.py
```

---

## Roadmap (F0–F22)

| Phase | Feature | Status |
|---|---|---|
| **F0** | Foundation: monorepo, Docker (api, worker, frontend, Postgres, Redis, Qdrant, Garage), Alembic, health checks | ✅ **Ready** |
| **F1** | Auth: registration, login, Argon2id, rotating refresh tokens, Google OAuth (PKCE), email verification, password reset, rate limiting | ✅ **Implemented** |
| **F2** | Tenants/RBAC: organizations, memberships, PostgreSQL RLS, email invitations, audit logs | ✅ **Implemented** |
| F3 | Anonymous trial: 1 free analysis, registration gate, account linking | 🔄 Next |
| F4 | Documents/storage: presigned upload, validation, lifecycle | ⏳ |
| F5 | Multimodal ingestion: Docling, VLM charts, structured tables, Qdrant | ⏳ |
| F6 | RAG filings: hybrid dense+BM25, tenant filters, reranker, citations | ⏳ |
| F7 | LLM router: role-based routing, fallbacks, cost tracking | ⏳ |
| F8 | Market data: prices, ratios, history, Redis cache | ⏳ |
| F9 | News sentiment: RSS/API, deduplication, FinBERT, event timeline | ⏳ |
| F10 | Quant/ML: volatility, risk scoring, isolated Python sandbox | ⏳ |
| F11 | Supervisor graph: parallel fan-out/fan-in, checkpoints, SSE | ⏳ |
| F12 | Writer/Critic: structured reports, numeric cross-check, revision loop | ⏳ |
| F13 | Human approval/export: pause, resume, PDF generation, watermarking | ⏳ |
| F14 | Plans/billing: test-mode BillingProvider, webhooks, subscriptions | ⏳ |
| F15 | Quotas/entitlements: server-side enforcement | ⏳ |
| F16 | Dashboard/visualization: live progress, charts, history, comparison | ⏳ |
| F17 | Demo request: validated form, notifications | ⏳ |
| F18 | Admin back-office: users, orgs, subscriptions, audit | ⏳ |
| F19 | Observability/evals: LangSmith, RAGAS CI gates | ⏳ |
| F20 | Deployment/CI-CD: production Dockerfiles, HTTPS, backups | ⏳ |
| F21 | Evaluation suite: versioned datasets, regression gates | ⏳ |
| F22 | Guardrails: injection defenses, PII, tool allowlists, sandbox | ⏳ |

---

## Security

- **Authentication**: Short-lived JWT + refresh tokens, Argon2id password hashing (`argon2-cffi`)
- **Authorization**: Row-Level Security (RLS) on all tenant-owned tables (F2+)
- **Data Isolation**: Mandatory `tenant_id` filters on every Qdrant query (F6+)
- **Secrets**: Never in code — environment variables only, `.env` gitignored
- **Containers**: Non-root users (UID 1000)
- **Sandbox**: Isolated Python execution (no network, time/memory limits) (F10+)

---

## License

Proprietary — All rights reserved. (Local infrastructure dependencies retain their respective open-source licenses, including Deuxfleurs Garage under AGPLv3.)
