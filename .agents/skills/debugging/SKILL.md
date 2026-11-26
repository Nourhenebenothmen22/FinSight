---
name: debugging
description: Diagnose bugs, exceptions, incorrect behavior, and failing tests using reproducible evidence and root-cause analysis. Use when investigating a defect before applying a fix.
---

# Debugging

## Objective
Find and explain the root cause before changing code; then implement the narrowest safe fix if requested.

## Workflow
1. Capture the expected behavior, actual behavior, reproduction steps, and relevant environment.
2. Read repository instructions and inspect Git status.
3. Reproduce the issue with the smallest safe command or test.
4. Read the complete relevant error, stack trace, logs, and surrounding code.
5. Trace data and control flow to identify the earliest incorrect assumption or state transition.
6. Form hypotheses and test them one at a time.
7. Distinguish root cause from symptoms and unrelated warnings.
8. If authorized to fix, make a minimal change and add a regression test where practical.
9. Re-run the reproduction and relevant regression suite.

## Constraints
- Do not guess based on the last stack-trace line alone.
- Do not suppress exceptions, weaken assertions, skip tests, or add arbitrary retries to hide the problem.
- Do not alter production data or run destructive repair commands.
- Do not expose secrets found in logs or environment files.
- Ask before changing external services, databases, infrastructure, or dependencies.

## Output
- Reproduction and environment.
- Root cause with file/line evidence.
- Why the failure occurs.
- Minimal fix (if authorized).
- Regression test and exact verification results.
- Unresolved hypotheses or limitations.
