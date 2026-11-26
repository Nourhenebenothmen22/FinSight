---
name: code-simplifier
description: Simplify code after a feature or refactor by reducing unnecessary complexity, duplication, indirection, and awkward control flow while preserving behavior. Use when asked to simplify or clean up implementation.
---

# Code Simplifier

## Objective
Make the smallest behavior-preserving simplification that improves readability and maintainability.

## Workflow
1. Inspect repository instructions, Git status, relevant implementation, and tests.
2. Identify the exact behavior and public interfaces that must remain unchanged.
3. Find concrete simplification opportunities:
   - duplicate logic;
   - needless branches or state;
   - excessive nesting;
   - redundant wrappers or abstractions;
   - unclear names;
   - overly broad functions or modules;
   - unnecessary dependencies.
4. Propose a small plan and identify behavior risks.
5. Make focused changes only within the requested scope.
6. Run relevant tests, type checks, and lint/format commands discovered in the repository.
7. Review the diff for accidental behavior changes and unrelated edits.

## Constraints
- Do not simplify by removing validation, authorization, error handling, logging, or edge-case behavior.
- Do not change public APIs, data formats, or persistence semantics without authorization.
- Do not introduce abstractions merely to reduce line count.
- Do not reformat unrelated files.
- Ask before changing dependencies or performing broad refactors.

## Output
- What was simplified and why.
- Files changed.
- Behavior-preservation considerations.
- Exact verification commands and results.
- Remaining risks or checks not run.
