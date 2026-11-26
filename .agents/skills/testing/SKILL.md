---
name: testing
description: Design, implement, and run appropriate unit, integration, contract, and end-to-end tests for a code change or feature. Use when adding coverage, validating behavior, or investigating test gaps.
---

# Testing

## Objective
Build confidence in observable behavior with tests that are deterministic, meaningful, and aligned with the project's existing test stack.

## Workflow
1. Read repository instructions and inspect package manifests, test configuration, fixtures, and existing test conventions.
2. Identify behavior, contracts, edge cases, failure modes, and regression risks.
3. Choose the narrowest appropriate test level:
   - unit for isolated logic;
   - integration for module/database/service interactions;
   - contract for API or message compatibility;
   - end-to-end for critical user workflows.
4. Reuse existing frameworks, fixtures, factories, and test utilities.
5. Avoid tests that merely mirror implementation details.
6. Add tests for normal cases, boundaries, invalid input, authorization, and failure behavior as relevant.
7. Run targeted tests first, then relevant broader checks.
8. Inspect failures; do not change assertions simply to make tests pass.

## Safe execution
- Inspect scripts and test configuration before running commands.
- Ask before tests that write to shared databases, contact real external services, incur cost, delete data, or require production credentials.
- Prefer isolated test databases, mocks, fakes, and deterministic fixtures.
- Never print secrets or copy production data into fixtures.

## Constraints
- Do not claim coverage or passing status without actual output.
- Do not weaken security checks or skip failing tests without explicit justification.
- Do not introduce a new test framework unless the existing stack cannot reasonably meet the need.

## Output
- Test strategy and coverage rationale.
- Files created or changed.
- Commands executed and exact results.
- Known gaps and recommended additional tests.
