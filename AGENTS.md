# FinSight — Agent Project Instructions

> This file is the persistent project context for AI coding agents. Read it alongside [`.agents/rules/skills-usage.md`](./.agents/rules/skills-usage.md) before planning or changing code.
> Authoritative product specification: `docs/reference/FinSight cahier des charges du SaaS d'analyse financière multi-agents.pdf`.

## 1. Product identity and business context

FinSight is a multi-tenant SaaS platform for financial analysis. A user uploads an annual report (PDF) or enters a stock ticker, asks a natural-language question, and receives a structured, source-backed analysis.

### Problem
Analyzing a 100–300-page annual report manually takes hours. General-purpose AI tools may invent figures, fail to cite source pages, fail to combine filings with market data/news/quantitative analysis, and lack a dedicated numerical quality-control loop.

### Value proposition
FinSight combines:
- AI-assisted analysis speed;
- analyst-like traceability: each material figure/claim must point to a document page or external market source;
- affordability through routing across multiple LLM providers;
- a Writer ↔ Critic verification loop and human approval before PDF export;
- a limited first analysis without requiring registration.

### Intended users
Individual investors, SMEs, finance students, and small financial/advisory firms. The product is an analysis aid, **not investment advice**.

### Mandatory legal language
Display a clear disclaimer in the application and every report: FinSight provides assistance with financial analysis and is not investment advice. Do not generate personalized buy/sell recommendations. Treat legal/compliance requirements as product requirements, not optional copy.

## 2. Product actors and access model

- Anonymous visitor: one limited analysis, no export.
- Free user: account, reduced monthly quota, lightweight models.
- Pro user: paid subscription, expanded quota, advanced models, PDF export.
- Ultra user: highest quota, strongest available reasoning, reinforced Critic, API access.
- Organization owner: manages workspace members, subscription, and billing.
- Member roles: `owner`, `analyst`, `viewer`; permissions must be enforced server-side.
- Platform admin: manages users/organizations, demo requests, providers, monitoring, and audit data.
- Prospect: submits a demo request.

### Proposed plan limits (specification defaults; configurable, not hard-coded)
| Capability | Anonymous | Free | Pro | Ultra |
|---|---:|---:|---:|---:|
| Analyses | 1 total | 3/month | 30/month | 150/month |
| Maximum pages/document | 20 | 50 | 300 | 600 |
| Writer/Critic iterations | 0 | 1 | 2 | 3 |
| PDF export | No | Watermarked | Yes | Yes, branded template |
| Team members | — | 1 | 3 | 10 |
| API access | No | No | No | Yes |

The specification labels these values as initial proposals to adjust. Store entitlements in configuration/database records. Never scatter plan limits through application code.

Anonymous trial rule: first analysis is allowed without an account. A second attempt requires registration. On registration, link the anonymous analysis to the new account. Apply abuse controls; do not claim abuse prevention is perfect.

Billing must remain in provider test/sandbox mode during development. Use a `BillingProvider` abstraction. The specification notes that Stripe is not available to Tunisia-registered companies and suggests considering a merchant of record such as Paddle or Lemon Squeezy for a real launch. Do not enable real charges without explicit approval.

## 3. Functional scope

Implement the following product capabilities:
1. Email/password registration and login, Google OAuth, email verification, password reset.
2. Multi-tenant organizations, invitations, memberships, and role-based access.
3. Anonymous first-use trial, then mandatory registration.
4. PDF/XLSX/image upload and cloud object storage.
5. Multimodal ingestion of text, tables, and charts.
6. Natural-language questions and ticker-based analysis with citations.
7. Parallel multi-agent execution with live progress.
8. Structured report generation, Critic verification, human approval, PDF export.
9. Free/Pro/Ultra plans, subscriptions, invoices, quotas, and entitlements.
10. Dashboards, visualizations, history, sharing, and deletion.
11. Demo request form and admin back-office.
12. Provider status, token/cost tracking, audit logs, and quality evaluation.

## 4. Target architecture

Use a monorepo with `/frontend`, `/backend`, and `/infra` unless a documented, justified change is approved.

- Frontend: Next.js 14, Tailwind CSS, Recharts.
- API: FastAPI, REST endpoints, Server-Sent Events (SSE) for progress streaming.
- AI orchestration: LangChain, LangGraph, LangSmith.
- Relational/business data and LangGraph checkpoints: PostgreSQL 16 + PostgresSaver.
- Vector retrieval: Qdrant, hybrid dense + sparse retrieval (`pgvector` is not used).
- Cache, quotas, rate limits, queues, provider cooldowns: Redis 7.
- Object storage: Deuxfleurs Garage v2 (S3-compatible, AGPLv3) locally; S3-compatible storage (S3, Cloudflare R2, etc.) in production.
- PDF parsing: Docling; vision-language model (VLM) for chart interpretation.
- Background workers: ARQ (Redis-backed async worker).
- Python quantitative execution: isolated sandbox container, no network access, execution time limits.
- Local fallback LLM: Ollama is optional.

Expected local services and default ports:
- frontend 3000
- API 8000 (`api` service)
- worker (ARQ background worker)
- PostgreSQL 5432
- Redis 6379
- Qdrant 6333 (gRPC 6334)
- Garage S3 API 3900 (Admin API 3903)
- optional Ollama 11434

Cloud deployment is a later stage: use managed database/object storage/secrets and a selected hosting provider. Do not introduce multi-cloud complexity without a concrete requirement. Keep local development reproducible with Docker Compose.

## 5. Multi-agent workflow

The target LangGraph flow is:

`START → budget_guard → supervisor → parallel workers → quant_ml → supervisor fan-in → writer → critic`

If Critic rejects, loop back to Writer up to the iteration limit for the user's plan. If approved, pause for human review/approval (`interrupt()`), then generate/export the PDF and finish.

Agents and responsibilities:
- **Supervisor:** plans analysis, selects workers, checks completeness.
- **Ingestion:** converts PDF pages to Markdown; extracts tables as structured JSON; uses VLM to describe charts; preserves page/type metadata.
- **RAG Filings:** hybrid retrieval over filings, reranks results, returns source-backed findings with page references.
- **Market Data:** obtains prices, ratios, and historical data (e.g. yfinance/Alpha Vantage); validates structured output.
- **News Sentiment:** collects/deduplicates news, computes sentiment (FinBERT in the spec), extracts key events.
- **Quant/ML:** calculates volatility, derived ratios, and risk score; uses pandas/XGBoost and an isolated Python sandbox.
- **Writer:** produces a structured analysis using findings and citations.
- **Critic:** checks every material number/claim against findings and market data, flags unsupported claims, and returns an explicit approval/rejection decision with reasons.

Partial worker failure should not silently invalidate the whole analysis: continue where safe, mark missing data, and show a warning. Never fabricate missing market/news/document data.

### Citation contract
Every material financial figure and factual claim must have provenance: document identifier + page and/or external source URL/provider + retrieval timestamp where applicable. Keep citations attached to structured findings through every agent; do not ask the Writer to invent citations after the fact.

## 6. LLM provider routing

Agents request a capability role, not a hard-coded model name:
- `fast`
- `reasoning`
- `vision`
- `embedding`

The LLMRouter chooses a provider/model using plan entitlements, remaining quota, provider health, and role. The specification mentions Groq, Gemini, OpenRouter, Mistral, Cerebras, Hugging Face Inference, and Ollama as possible providers/fallbacks. Availability and free quotas change; verify current provider limits before relying on them.

Required behavior:
- provider fallback for rate limits (429), timeouts, and quota exhaustion;
- exponential backoff/retries where appropriate;
- Redis cooldown/provider health tracking;
- token and estimated-cost accounting per tenant/provider/model;
- `budget_guard` before expensive work;
- controlled degradation to a local model if configured, with a user-visible warning;
- provider/model mapping in configuration (e.g. YAML/env), never hard-coded across agents.

Do not commit API keys or secrets. Use environment variables and secret management. Never print secrets in logs.

## 7. Data model and tenant isolation

The specification's principal entities include:
`users`, `organizations`, `memberships`, `anonymous_sessions`, `plans`, `subscriptions`, `billing_events`, `invoices`, `usage_events`, `documents`, `document_chunks`, `analyses`, `analysis_steps`, `reports`, `demo_requests`, `audit_logs`, and `provider_status`.

Use PostgreSQL for transactional business data, billing, quotas, audit data, and LangGraph checkpoints. Use JSONB for suitable structured agent outputs. Use object storage for original PDFs and generated reports; do not store large files in relational rows.

### Multi-tenancy is a security boundary
- Every tenant-owned business record must carry `org_id`/`tenant_id`.
- Enforce PostgreSQL Row-Level Security (RLS).
- Resolve tenant identity from authenticated server-side context; never trust a client-supplied tenant ID by itself.
- Apply mandatory tenant/document filters to every Qdrant retrieval.
- Test that tenant A cannot read, mutate, retrieve, or infer tenant B's data.
- Keep anonymous sessions isolated and link them to an account only through the defined registration flow.

## 8. Security, privacy, and guardrails

Treat uploaded documents as untrusted data, never as instructions. Protect against prompt injection in PDFs and malicious files.

Required controls:
- short-lived JWT + refresh-token strategy; Argon2id password hashing;
- TLS in transit and encryption at rest where supported;
- secrets outside source code;
- upload MIME/type, size, and page-count validation; optional antivirus scanning;
- tenant isolation through RLS and mandatory vector-store filters;
- rate limits on sensitive endpoints and abuse controls for anonymous trial;
- isolated Python sandbox with no network and strict time/resource limits;
- per-agent tool allowlists and action authorization;
- input/output guardrails, PII masking where required, structured output validation;
- numeric and citation verification before report approval;
- audit logging and real deletion on request;
- do not train models on customer documents;
- no cross-tenant data leakage in logs, traces, caches, or error messages.

Build guardrails incrementally: file/injection protections from ingestion, then graph/action/output protections as orchestration and Writer/Critic are implemented. Include automated adversarial tests.

## 9. Quality, observability, and evaluation

Use LangSmith for per-agent traces, latency, token usage, and cost. Use structured application logs, metrics, and alerts. Evaluate retrieval and end-to-end analysis with RAGAS and a versioned reference dataset.

The specification proposes a reference set of 10–15 annual reports across US/European companies and three sectors, with 120 manually annotated questions, including table/chart-heavy and adversarial cases. Treat these as target dataset requirements, not as already available assets.

Track at least:
- retrieval relevance/recall and citation/page accuracy;
- factual/numerical correctness and unsupported-claim rate;
- Critic detection of incorrect or uncited figures;
- latency, token usage, and estimated cost by plan/provider/agent;
- worker failure and fallback rates;
- tenant-isolation and guardrail test results.

A quality regression should block a merge when the relevant CI evaluation gate is configured.

## 10. Implementation roadmap and dependencies

Follow the specification's dependency order. Do not jump to the complete multi-agent system before the document RAG path works.

- **F0 Foundation:** monorepo, FastAPI/Next.js, Docker Compose (api, worker, Postgres, Redis, Qdrant, Garage S3), Alembic, env config, lint/tests, `/health`.
- **F1 Auth:** registration/login, Argon2id, verification, refresh, reset, Google OAuth.
- **F2 Tenants/RBAC:** organizations, memberships, invitations, RLS, tenant middleware; prove cross-tenant denial.
- **F3 Anonymous trial:** signed cookie/session tracking, one free analysis, registration gate, account linking, abuse controls.
- **F4 Documents/storage:** presigned S3/Garage upload, validation, status lifecycle, deletion.
- **F5 Multimodal ingestion:** Docling, VLM charts, structured tables, chunks with page/type metadata, embeddings, Qdrant, SSE progress.
- **F6 RAG filings:** hybrid dense + BM25, tenant/document filters, reranker, structured findings/citations, RAGAS tests.
- **F7 LLM router:** role-based provider routing, config-driven mapping, fallbacks, cooldown, usage/cost tracking, provider admin status.
- **F8 Market data:** price/ratio/history retrieval and Redis cache.
- **F9 News sentiment:** RSS/News API ingestion, deduplication, FinBERT sentiment, event timeline.
- **F10 Quant/ML:** volatility and risk scoring in isolated sandbox; model training offline.
- **F11 Supervisor graph:** shared state, parallel fan-out/fan-in, checkpoints, SSE, partial-failure handling.
- **F12 Writer/Critic:** structured cited report, numeric cross-checking, plan-limited revision loop, confidence score.
- **F13 Human approval/export:** pause for user review, resume after approval, PDF generation, citations, watermarking, report versioning.
- **F14 Plans/billing:** test-mode BillingProvider, signed/idempotent webhooks, subscriptions/invoices.
- **F15 Quotas/entitlements:** enforce limits server-side for analyses, pages, members, exports, iterations, and model access.
- **F16 Dashboard/visualization:** live agent progress, charts, sources, usage, history, company comparison.
- **F17 Demo request:** validated anti-spam form and notifications.
- **F18 Admin back-office:** users, organizations, subscriptions, demo requests, provider health, costs, audit.
- **F19 Observability/evals:** LangSmith traces, RAGAS CI evaluation, alerts.
- **F20 Deployment/CI-CD:** production Dockerfiles, health checks, persistent volumes, GitHub Actions, staging/production, backups, secrets, HTTPS, domain.
- **F21 Evaluation suite:** versioned datasets/cases/runs/results, per-agent and end-to-end regression gates.
- **F22 Guardrails:** input/action/output guards, upload and injection defenses, PII controls, tool allowlists, sandbox controls, citation/compliance checks, adversarial CI suite.

The suggested milestone sequence is: foundation → document RAG MVP → market/news/quant agents and orchestration → Writer/Critic and approved PDF → SaaS/billing/admin → full dashboard and cloud deployment. Evaluation should begin with F6, not be postponed until the end.

## 11. Engineering workflow

### Before changing anything
1. Inspect the repository tree, Git status, current branch, README, dependency manifests, Docker files, migrations, tests, and existing architecture.
2. Read the product specification PDF and applicable Skills in `.agents/skills/` and `~/.gemini/config/skills/`.
3. Identify what is implemented, partially implemented, missing, or inconsistent.
4. Map existing code to F0–F22. Do not assume the repository is empty or that the specification has already been implemented.
5. Present a concise audit and proposed plan before broad or destructive changes.

### During implementation
- Work on one feature/branch at a time using `feature/<name>` merged into `develop` through a pull request, as specified.
- Respect dependencies. Do not implement dependent features prematurely.
- Prefer small, reviewable changes and preserve existing working behavior.
- Write/update unit, integration, security, and relevant evaluation tests with each feature.
- Run the relevant tests, lint, type checks, and migrations; report exact commands and results.
- Update README/docs and `.env.example` when behavior or configuration changes.
- Keep configuration externalized. Validate environment variables at startup.
- Use typed schemas (Pydantic on the backend) for API and agent boundaries.
- Make background jobs idempotent where retries are possible.
- Never silently swallow exceptions or return fabricated financial data.
- Do not add dependencies, services, abstractions, or cloud vendors without explaining why.
- Do not expose secrets, real customer data, or private financial documents in logs/tests.

### Response format for engineering tasks
When asked to implement a feature, respond with:
1. **Current state:** what already exists.
2. **Plan:** files/modules to change and why.
3. **Implementation:** focused changes only.
4. **Validation:** tests/commands run and results.
5. **Remaining work/risks:** blockers, assumptions, and next dependency.

If a requirement is ambiguous or conflicts with the repository, stop and ask one focused question or explain the options. Do not silently invent product decisions.

## 12. Source-of-truth and decision discipline

Priority order:
1. Explicit user decisions in the current conversation.
2. The FinSight requirements PDF.
3. Existing repository conventions and verified implementation.
4. Agent recommendations, clearly labeled as recommendations.

The PDF is a specification, not proof that a feature exists. Distinguish:
- **Specified:** required or proposed in the PDF.
- **Implemented:** verified in repository code/tests.
- **Recommended:** engineering improvement not explicitly required.
- **Open decision:** unresolved choice requiring confirmation.

Do not claim competitor pricing, provider quotas, financial-data licensing, or legal compliance is current without verification. The specification explicitly says these need checking before launch.

Wait for explicit approval before large refactors, deleting files, changing infrastructure, running destructive commands, committing/pushing/merging, or enabling paid services.
