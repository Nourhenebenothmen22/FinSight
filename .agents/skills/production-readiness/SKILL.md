---
name: production-readiness
description: Assess whether an application is ready for production by reviewing reliability, security, configuration, observability, deployment, data management, testing, and operational recovery. Use before a release or deployment decision.
---

# Production Readiness

## Objective
Provide a release-readiness assessment based on repository evidence, not assumptions.

## Workflow
1. Define the application, deployment target, release scope, and critical user journeys. If unknown, state the limitation.
2. Read repository instructions and inspect source, manifests, CI/CD, containers, infrastructure, and deployment configuration.
3. Review:
   - build reproducibility and dependency management;
   - environment-specific configuration and secret handling;
   - authentication, authorization, and input validation;
   - database migrations, backups, restore, and data integrity;
   - health checks, graceful shutdown, retries, timeouts, and failure handling;
   - logs, metrics, tracing, alerting, and auditability;
   - capacity, resource limits, and performance evidence;
   - tests, CI gates, rollback, and release process;
   - accessibility and critical UX where relevant.
4. Verify checks that can safely run locally.
5. Classify each area as Pass, Needs attention, Fail, or Not assessed, with evidence.
6. List release blockers separately from follow-up improvements.
7. Recommend owners/actions and a safe go/no-go decision.

## Constraints
- Do not deploy, migrate production data, rotate credentials, or change infrastructure.
- Do not claim readiness without checking the target environment and operational requirements.
- Do not treat the existence of a CI workflow as proof that it passes.
- Do not expose secrets or sensitive operational details.
- Ask before running external, destructive, costly, or production-connected checks.

## Output
- Scope and assumptions.
- Readiness matrix with evidence and status.
- Release blockers and severity.
- Required actions before release.
- Rollback/monitoring considerations.
- Go / conditional go / no-go recommendation, with limitations.
