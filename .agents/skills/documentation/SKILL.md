---
name: documentation
description: Create or update accurate project documentation, including README files, setup instructions, architecture notes, API references, and operational runbooks. Use when documentation is requested or code changes make docs stale.
---

# Documentation

## Objective
Produce concise documentation that matches the implementation and can be followed by a developer who is new to the project.

## Workflow
1. Read repository instructions and inspect the actual implementation, manifests, scripts, routes, schemas, and configuration.
2. Identify the intended audience and documentation location.
3. Verify every command, path, environment variable, endpoint, and feature against source files.
4. Update only the relevant documentation:
   - purpose and scope;
   - prerequisites;
   - installation and configuration;
   - development, test, build, and deployment commands;
   - architecture and data flow;
   - API contracts and examples;
   - troubleshooting and operational notes.
5. Use placeholders for secrets; never include real credentials.
6. Keep examples minimal, valid, and consistent with the current code.
7. Review links, headings, code fences, and command accuracy.

## Constraints
- Never invent features, environment variables, endpoints, scripts, or outputs.
- Do not copy secrets, personal data, or production identifiers into documentation.
- Do not rewrite unrelated documentation.
- Ask before changing public API documentation in a way that changes a contract.

## Output
- Documentation files changed.
- Summary of additions and corrections.
- Source locations used to verify claims.
- Any commands/examples that still require user-specific values.
