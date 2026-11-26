# FinSight Architecture Documentation

> **Version**: 0.3.0 (F2 Tenants & RBAC)
> **Last Updated**: 2026-11-26
> **Status**: F0 Foundation, F1 Auth & F2 Tenants/RBAC/RLS complete — ready for F3 Anonymous Trial

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Monorepo Structure](#monorepo-structure)
3. [Technology Stack](#technology-stack)
4. [Infrastructure](#infrastructure)
5. [Backend Architecture](#backend-architecture)
6. [Frontend Architecture](#frontend-architecture)
7. [Data Flow](#data-flow)
8. [Security Model](#security-model)
9. [Deployment](#deployment)
10. [Development Workflow](#development-workflow)

---

## System Overview

FinSight is a **multi-tenant SaaS platform** for financial analysis. Users upload annual reports (PDF) or enter stock tickers, ask natural-language questions, and receive structured, source-backed analyses.

### Core Principles

- **Tenant Isolation**: Every data record carries `org_id`; enforced via PostgreSQL RLS and Qdrant filters
- **Citation Contract**: Every material figure must have provenance (document + page, or external source + timestamp)
- **Provider Abstraction**: LLM routing by capability role (`fast`, `reasoning`, `vision`, `embedding`), not hard-coded models
- **Verification Loop**: Writer ↔ Critic with human approval gate before PDF export
- **Test-Mode Billing**: All payments in sandbox; `BillingProvider` abstraction for Stripe/Paddle/Lemon Squeezy

### High-Level Architecture

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                                    FinSight                                    │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  ┌──────────────┐    HTTPS/WSS    ┌──────────────┐    REST + SSE   ┌────────┐  │
│  │   Browser    │◄───────────────►│   Frontend   │◄───────────────►│  API   │  │
│  │  (React/Next)│                 │  (Next.js)   │                 │(FastAPI│  │
│  └──────────────┘                 └──────────────┘                 └───┬────┘  │
│                                                                        │       │
│                              ┌─────────────────────────────────────────┘       │
│                              ▼                                                 │
│                    ┌──────────────────────┐                                    │
│                    │    Infrastructure    │                                    │
│                    │   (Docker Compose)   │                                    │
│                    ├──────────────────────┤                                    │
│                    │  PostgreSQL 16       │ Relational data, RLS, checkpoints  │
│                    │  Qdrant              │ Vector search (hybrid dense+sparse)│
│                    │  Redis 7             │ Cache, quotas, ARQ queues          │
│                    │  Garage v2 (S3)      │ PDF storage, report artifacts      │
│                    │  Worker (ARQ)        │ Async jobs & LangGraph execution   │
│                    │  Ollama (optional)   │ Local LLM fallback                 │
│                    └──────────────────────┘                                    │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## Monorepo Structure

```
FinSight/
├── .agents/                    # Antigravity rules and project skills
│   ├── rules/skills-usage.md
│   └── skills/
├── .github/workflows/          # CI/CD pipelines
├── AGENTS.md                   # Project rules and technical guidelines
├── backend/                    # FastAPI + ARQ worker application
│   ├── app/
│   │   ├── api/                # API routes & dependencies (REST, TenantContext, RBAC)
│   │   ├── core/               # Config, security, database (RLS), middleware, Redis, queue
│   │   ├── models/             # SQLAlchemy ORM models & shared Base (auth, tenant)
│   │   ├── schemas/            # Pydantic request/response models
│   │   ├── services/           # Business services (auth, tenant, audit, email)
│   │   ├── main.py             # FastAPI entry point
│   │   └── worker.py           # ARQ background worker entry point
│   ├── alembic/                # Database migrations (0001..0003)
│   ├── tests/                  # Pytest unit & PostgreSQL RLS integration suite
│   ├── pyproject.toml          # Python dependencies & tool config
│   └── Dockerfile              # Multi-stage build (development, production)
├── frontend/                   # Next.js application
│   ├── public/                 # Static assets (icon.svg, manifest.json)
│   ├── src/
│   │   ├── app/                # App Router pages/layouts + /api/backend proxy route
│   │   ├── components/         # React components
│   │   └── lib/                # Utilities, typed API client
│   ├── tests/                  # Vitest suite
│   ├── package.json
│   └── Dockerfile
├── infra/                      # Infrastructure configs
│   ├── postgres/init.sql
│   ├── qdrant/config.yaml
│   ├── redis/redis.conf
│   └── garage/
│       ├── garage.toml
│       └── init_buckets.py
├── docker-compose.yml          # Local development stack
├── docker-compose.override.yml.example
├── .env.example                # Environment template
├── README.md
└── docs/
    ├── ARCHITECTURE.md         # This file
    └── reference/              # Product specification PDF
```

---

## Technology Stack

### Backend

| Component | Technology | Version | Purpose |
|---|---|---|---|
| Framework | FastAPI | 0.109+ | Async REST API, OpenAPI docs |
| Worker | ARQ | 0.26+ | Redis-backed async background jobs |
| ORM | SQLAlchemy | 2.0+ | Async database access (`asyncpg`) |
| Migrations | Alembic | 1.13+ | Schema versioning |
| Validation | Pydantic | 2.6+ | Settings, request/response models |
| Auth | python-jose + argon2-cffi | 3.3+ / 23.1+ | JWT, Argon2id hashing |
| Vector DB | qdrant-client | 1.9+ | Hybrid dense+sparse search |
| Cache/Queue | redis-py | 5.0+ | Redis async client |
| Object Storage | minio-py (S3 SDK) | 7.2+ | S3-compatible client (Garage / S3 / R2) |
| HTTP Client | httpx | 0.27+ | Async HTTP requests |
| Observability | structlog, OpenTelemetry | 24.1+ / 1.22+ | Structured logging, tracing |
| Testing | pytest, pytest-asyncio, aiosqlite | 7.4+ / 0.23+ | Unit/integration tests |
| Linting | ruff | 0.2+ | Fast Python linter/formatter |
| Type Check | mypy | 1.8+ | Static type checking |

### Frontend

| Component | Technology | Version | Purpose |
|---|---|---|---|
| Framework | Next.js | 14.2 (App Router) | React framework, SSR/SSG |
| Language | TypeScript | 5.4 | Type-safe React |
| Styling | Tailwind CSS | 3.4 | Utility-first CSS + CSS variables |
| Charts | Recharts | 2.12 | Composable charting |
| Validation | Zod | 3.23 | Schema validation |
| HTTP Client | Fetch wrapper / Axios | — | Typed API requests |
| Testing | Vitest + @testing-library/react | 1.5 / 14.2 | Component & unit tests |
| Linting | ESLint (`eslint-config-next`) | 8.57 / 14.2 | Next.js & React linting |
| Formatting | Prettier | 3.2 | Code formatter |
| Type Check | tsc | 5.4 | TypeScript compiler |

### Infrastructure

| Service | Image | Port(s) | Purpose |
|---|---|---|---|
| PostgreSQL | `postgres:16-alpine` | 5432 | Relational DB, RLS, LangGraph checkpoints |
| Qdrant | `qdrant/qdrant:v1.9.0` | 6333, 6334 | Vector search (HTTP + gRPC) |
| Redis | `redis:7-alpine` | 6379 | Cache, ARQ queues, rate limits |
| Garage | `dxflrs/garage:v2.6.0` | 3900, 3903 | S3-compatible object storage (AGPLv3) + Admin API |
| Ollama (opt) | `ollama/ollama:0.1.47` | 11434 | Local LLM inference |

> **Object Storage Note**: FinSight uses **Deuxfleurs Garage v2** locally (AGPLv3, Rust, lightweight single-node S3 API with SigV4 presigned URLs, CORS, and multipart upload). Note that Garage does not implement S3 object versioning; FinSight handles report versioning in PostgreSQL (`reports.version` + distinct object keys) in F13.

---

## Infrastructure

### Docker Compose Services

```yaml
services:
  postgres:      # Primary database
  qdrant:        # Vector search engine
  redis:         # Cache & message broker
  garage:        # S3-compatible object storage (AGPLv3)
  garage-init:   # Idempotent bucket & permission setup
  api:           # FastAPI (dev: hot reload, prod: 4 workers)
  worker:        # ARQ background worker
  frontend:      # Next.js (dev: hot reload, prod: standalone)
  ollama:        # Optional local LLM (profile: ollama)
```

### Volumes (Persisted Data)

| Volume | Service | Content |
|---|---|---|
| `postgres_data` | postgres | `/var/lib/postgresql/data` |
| `qdrant_data` | qdrant | `/qdrant/storage` |
| `redis_data` | redis | `/data` |
| `garage_meta` | garage | `/var/lib/garage/meta` |
| `garage_data` | garage | `/var/lib/garage/data` |
| `ollama_data` | ollama | `/root/.ollama` |

### Configuration Files

- `infra/postgres/init.sql` — Extensions (`uuid-ossp`, `pgcrypto`, `btree_gin`, `citext`)
- `infra/qdrant/config.yaml` — Storage, WAL, optimizer, single-node config
- `infra/redis/redis.conf` — Memory policy (`allkeys-lru`), RDB + AOF persistence, slow log
- `infra/garage/garage.toml` — Garage v2 S3/Admin/RPC configuration (`us-east-1`, `sqlite`)
- `infra/garage/init_buckets.py` — Idempotent provisioning of `finsight-documents` and `finsight-reports`

---

## Backend Architecture

### Configuration (`core/config.py`)

- **Pydantic Settings** resolving root `.env` (`Path(__file__).resolve().parents[3] / ".env"`) and local `.env`
- All sensitive keys/passwords typed as `SecretStr`
- Production/staging validator rejecting weak or `CHANGE_ME` secrets
- `APP_ENV` values: `development` | `test` | `staging` | `production`

### Security (`core/security.py`, `core/rate_limit.py`, `api/deps.py`)

- **Argon2id** via `argon2.PasswordHasher` (`time_cost=3`, `memory_cost=65536`, `parallelism=4`, `hash_len=32`, `salt_len=16`) + constant-time dummy verification on unknown/OAuth-only logins
- **JWT + Rotating Refresh Tokens**: Short-lived access JWTs (`jti`, `sub`, `type="access"`) + SHA-256 persisted `RefreshToken` rows (`family_id`) with automatic reuse detection and `HttpOnly` cookie / CSRF origin checks
- **Opaque Action Tokens**: Single-use SHA-256 hashed `AuthToken` records for email verification and password reset, dispatched asynchronously via ARQ (`worker.py`) + `services/email.py`
- **Google OAuth 2.0 / OIDC**: Authorization Code + `S256` PKCE + Redis single-use `state` binding + Google JWKS signature verification + pre-hijacking prevention on unverified emails
- **Rate Limiting**: Atomic Redis Lua window counters in `core/rate_limit.py` with trusted-proxy IP resolution

### Database & Multi-Tenant RLS (`core/database.py`, `core/tenant_context.py`, `models/`)

- Single unified `Base(DeclarativeBase)` defined in `app/models/base.py` and re-exported by `app/core/database.py`
- F1 tables (`models/auth.py`): `users`, `refresh_tokens`, `auth_tokens`
- F2 tables (`models/tenant.py`): `organizations`, `memberships`, `organization_invitations`, `audit_logs`
- Strict Row-Level Security (`ENABLE` + `FORCE ROW LEVEL SECURITY`) on all F2 tenant tables enforced via non-superuser role `finsight_app` (`NOBYPASSRLS`) and transaction-local `app.current_tenant_id` (`bind_tenant_rls()` invoked by `get_tenant_db()` / `require_org_roles()`)
- Pure ASGI `TenantContextMiddleware` binds optional validated `X-Tenant-ID` context and request correlation metadata without altering authorization (membership + role are resolved server-side per request)
- Async SQLAlchemy 2.0 + `asyncpg` with `connect_args={"ssl": ...}` when `POSTGRES_SSL_MODE != "disable"`
- `close_db()`, `close_redis()`, and `close_arq_pool()` dispose clients cleanly on shutdown

### Endpoints (`api/routes/`)

| Endpoint Group | Purpose | Notes |
|---|---|---|
| `GET /health`, `/health/ready`, `/health/live` | Dependency health & probes | `200` if all healthy (`database`, `redis`, `qdrant`, `storage`), `503` otherwise |
| `/api/v1/auth/*` | Registration, verification, login, refresh, logout, forgot/reset, profile, sessions, Google OAuth | Versioned REST routes with rate limiting, `HttpOnly` refresh cookies, and auto personal workspace provisioning |
| `/api/v1/orgs/*`, `/api/v1/invitations/accept` | Workspaces CRUD, membership RBAC (`owner`/`analyst`/`viewer`), email invitations, audit logs | Server-side membership/role resolution + per-transaction PostgreSQL `SET LOCAL ROLE` + RLS enforcement |

### Alembic Migrations

- `alembic.ini` + `alembic/env.py` (async online/offline runner, `%`-escaped URL, `app.models.base.Base.metadata`)
- `alembic/versions/0001_f0_baseline.py` baseline revision
- `alembic/versions/0002_f1_auth_tables.py` F1 `users`, `refresh_tokens`, and `auth_tokens` schema + partial OAuth unique index
- `alembic/versions/0003_f2_tenants_rbac_and_rls.py` F2 `organizations`, `memberships`, `organization_invitations`, `audit_logs`, personal workspace backfill, `finsight_app` role, and strict `FORCE ROW LEVEL SECURITY` policies

---

## Frontend Architecture

- **Next.js 14.2 App Router** with `output: 'standalone'`
- **Runtime Backend Proxy**: `/api/backend/[...path]` App Router route handler forwards requests dynamically at runtime (including `cookie`, `set-cookie`, `origin`, `x-tenant-id`, and `x-forwarded-for`) using `BACKEND_INTERNAL_URL || NEXT_PUBLIC_API_URL || 'http://localhost:8000'`
- **Auth & Workspace State (`AuthProvider.tsx`, `WorkspaceProvider.tsx`, `lib/api.ts`, `lib/auth.ts`, `lib/orgs.ts`)**: Holds access token strictly in React memory with single-flight `401` silent refresh lock via `HttpOnly` cookie, persists active workspace UUID selection with server-side revalidation and automatic `X-Tenant-ID` header injection, and provides Zod-validated UI across `/register`, `/login`, `/verify-email`, `/forgot-password`, `/reset-password`, `/auth/google/callback`, `/profile`, `/workspaces`, `/workspaces/[orgId]`, and `/invitations/accept`
- **Health visualization**: `HealthStatus.tsx` with `role="status"` accessibility badge + per-dependency breakdown
- **Compliance**: Shared `LegalDisclaimer.tsx` rendered across home and auth/profile views
- **Tests**: Vitest + React Testing Library (`tests/`), type-checked via `tsconfig.json`

---

## Data Flow

### Health Check Request Flow

```
Browser
   │  fetch('/api/backend/health')
   ▼
Next.js Route Proxy (frontend container: `/api/backend/*`)
   │  → http://api:8000/*
   ▼
FastAPI (api container:8000)
   │  1. PostgreSQL: SELECT 1
   │  2. Redis: PING
   │  3. Qdrant: GET /readyz
   │  4. Garage S3: bucket_exists(finsight-documents, finsight-reports)
   ▼
200 OK (all healthy) or 503 Service Unavailable (any unhealthy)
```

---

## Security Model

- **Authentication (F1+)**: Short-lived JWT access tokens + rotating refresh tokens; Argon2id hashing
- **Authorization (F2+)**: PostgreSQL Row-Level Security on `org_id` + server-side RBAC (`owner`, `analyst`, `viewer`)
- **Vector Isolation (F6+)**: Mandatory `tenant_id` filter on every Qdrant query
- **Object Isolation (F4+)**: Tenant-prefixed keys in `finsight-documents` / `finsight-reports`
- **Secrets**: Outside source code (`.env` gitignored, `SecretStr` in Pydantic Settings, no secret/traceback exposure in HTTP health errors)

---

## Development Workflow

### Git Strategy

- **Main branches**: `main` (production), `develop` (integration)
- **Feature branches**: `feature/<short-name>` from `develop`
- **Conventional Commits**: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`

### Local Verification Commands

```bash
# Backend
cd backend
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy app/
.venv/bin/pytest -v
.venv/bin/alembic history

# Frontend
cd frontend
npm run lint
npm run format:check
npm run typecheck
npm run test
npm run build

# Full Stack
docker compose up -d --build
curl -f http://localhost:8000/health
curl -f http://localhost:3000
```

---

## Appendix: F0 Foundation Checklist

- [x] Monorepo structure (`backend/`, `frontend/`, `infra/`)
- [x] Docker Compose with `api`, `worker`, `frontend`, `postgres`, `redis`, `qdrant`, `garage`, `garage-init` (+ optional `ollama`)
- [x] `.env.example` aligned with Garage S3 and local services
- [x] Backend: FastAPI app, `structlog`, CORS, exception handler, ARQ `worker.py`
- [x] Backend: Unified `Base`, async SQLAlchemy + `asyncpg` SSL support, Alembic `0001_f0_baseline`
- [x] Backend: `HealthResponse` returning HTTP `200` (healthy) / `503` (unhealthy) without exception leaks
- [x] Backend: Ruff, MyPy, Pytest passing cleanly
- [x] Frontend: Next.js 14.2, Tailwind tokens complete, ESLint + Prettier + TypeScript + Vitest + `next build` passing
- [x] Frontend: Mandatory legal disclaimer displayed
- [x] CI/CD: `.github/workflows/ci.yml` configured with dependency caching, builds, integration test, and pinned security scanners
