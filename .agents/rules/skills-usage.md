---
trigger: always_on
---

# Mandatory Skill Usage Rules

## 1. Skill Discovery

Before starting any development task:

- Inspect project Skills in `.agents/skills/`.
- Inspect global Skills in `~/.gemini/config/skills/`.
- Identify all Skills relevant to the requested task.
- Read the complete `SKILL.md` of each relevant Skill before implementation.
- Do not assume a Skill's workflow without reading its instructions.

## 2. Available Project & Global Skills

The following Skills are installed:

- `code-architecture`
- `code-audit`
- `code-simplifier`
- `debugging`
- `documentation`
- `fintech-ui-ux-design`
- `git-workflow`
- `nextjs-senior-frontend`
- `performance-audit`
- `production-readiness`
- `security-audit`
- `testing`

Use them according to the task:

| Task | Relevant Skills |
|---|---|
| Architecture and project structure | `code-architecture` |
| Code quality and review | `code-audit` |
| Refactoring and simplification | `code-simplifier` |
| Troubleshooting | `debugging` |
| Technical documentation | `documentation` |
| UI/UX design, palette, buttons, charts, branding | `fintech-ui-ux-design` |
| Branches, commits and PRs | `git-workflow` |
| Next.js pages, components, SSE, frontend architecture | `nextjs-senior-frontend` |
| Performance optimization | `performance-audit` |
| Production readiness | `production-readiness` |
| Authentication, authorization and security | `security-audit` |
| Unit, integration and acceptance tests | `testing` |

These are recommendations, not an exhaustive mapping. Use additional relevant Skills if discovered.

## 3. Mandatory Development Workflow

For every FinSight feature:

1. Read the relevant requirements in the project specification.
2. Inspect the existing codebase and architecture.
3. Identify and read relevant Skills.
4. Present the implementation plan.
5. Wait for approval before implementation.
6. Implement only the requested feature.
7. Follow the requirements and applicable Skills.
8. Run relevant tests and quality checks.
9. Perform a code and security review where applicable.
10. Report the results and remaining issues.

## 4. Git Workflow

- Follow the `git-workflow` Skill.
- Use one feature branch per feature.
- Create feature branches from the latest `develop`.
- Never implement multiple independent features in one branch.
- Never commit, push, merge or open a PR without explicit user approval.
- Do not modify unrelated files.

## 5. Quality and Security

- Follow the `security-audit` Skill for security-sensitive changes.
- Follow the `testing` Skill for all feature implementations.
- Follow the `code-architecture` Skill when introducing architectural changes.
- Avoid unnecessary dependencies and duplicated code.
- Never claim that tests passed unless they were actually executed.
- Never ignore a relevant Skill without explaining why.

## 6. Final Report

At the end of each feature, report:

- Skills discovered and actually used.
- Files created or modified.
- Implementation summary.
- Tests executed and their results.
- Security considerations.
- Deviations from the requirements or Skills.
- Remaining issues.

Do not proceed to another feature without explicit user approval.
