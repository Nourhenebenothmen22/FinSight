---
name: code-architecture
description: Analyze or plan software architecture, module boundaries, dependency direction, data flow, scalability, and SOLID trade-offs in an existing project. Use for architecture reviews or design decisions. Read-only unless implementation is explicitly requested.
---

# Code Architecture

## Objective
Understand the architecture that exists, then recommend the simplest design that satisfies the stated requirements.

## Workflow
1. Read project instructions and inspect Git status.
2. Identify application entry points, runtime components, modules, persistence, integrations, and deployment topology.
3. Trace representative flows end to end: request/event, business logic, persistence, external services, and response.
4. Map dependencies and ownership:
   - responsibilities per module;
   - dependency direction;
   - interfaces and boundaries;
   - shared state and side effects;
   - synchronous/asynchronous communication.
5. Evaluate relevant SOLID principles, cohesion, coupling, separation of concerns, failure isolation, observability, and testability.
6. Assess scalability and operational complexity only against stated or evidenced requirements.
7. Compare options with explicit trade-offs; prefer incremental evolution over a rewrite.
8. Present a target design only when the current design has a demonstrated limitation.

## Constraints
- Do not impose a fashionable architecture (microservices, CQRS, event sourcing, clean architecture, etc.) without a concrete need.
- Do not infer scale, traffic, compliance, or availability requirements.
- Do not change files unless the user explicitly requests implementation.
- Preserve technology choices unless there is a reasoned case to change them.

## Output
- Current architecture summary.
- Component and data-flow description.
- Strengths and architectural risks with file references.
- Relevant SOLID/design-principle observations.
- Options and trade-offs.
- Recommended incremental plan, including migration risks and validation.
