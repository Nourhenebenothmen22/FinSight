---
name: git-workflow
description: Help with safe Git workflows, change inspection, branch hygiene, commit preparation, Conventional Commits, and pull-request readiness. Use when asked to inspect or prepare Git changes.
---

# Git Workflow

## Objective
Keep version-control operations reviewable and safe; never discard user work.

## Workflow
1. Inspect `git status --short --branch`, current branch, remotes, and recent commit conventions.
2. Review staged and unstaged diffs separately.
3. Identify generated files, secrets, unrelated changes, and accidental artifacts.
4. Suggest a focused staging plan; do not stage files unless asked.
5. Prepare a commit message consistent with the repository's conventions. Use Conventional Commits when requested or already adopted.
6. Before committing, review the exact staged diff and ask for approval if the user has not explicitly requested the commit.
7. For pull requests, summarize intent, implementation, tests, risks, and migration notes.

## Constraints
- Never run `reset --hard`, `clean -fd`, force-push, rebase that rewrites shared history, or delete branches without explicit authorization.
- Never discard, overwrite, or silently stage user changes.
- Never commit secrets, `.env` files, private keys, generated build output, or unrelated files.
- Do not assume the remote or default branch.
- Do not push or create a PR unless explicitly requested.

## Output
- Current repository/branch state.
- Diff summary.
- Recommended staging scope.
- Proposed commit message or PR summary.
- Commands executed and their results.
