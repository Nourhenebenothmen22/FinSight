---
name: performance-audit
description: Investigate likely performance bottlenecks in code, database access, network calls, memory use, concurrency, and frontend rendering. Use when asked to diagnose or improve performance.
---

# Performance Audit

## Objective
Identify bottlenecks using evidence and recommend measurable improvements without premature optimization.

## Workflow
1. Clarify the workload, latency/throughput target, environment, and observed symptom. If unknown, state that limitation.
2. Read repository instructions and inspect architecture and relevant execution paths.
3. Look for likely cost drivers:
   - algorithmic complexity and repeated work;
   - N+1 queries, missing indexes, unbounded scans;
   - chatty network calls and serial I/O;
   - large payloads and inefficient serialization;
   - memory retention, unnecessary copies, and leaks;
   - blocking operations and concurrency limits;
   - frontend re-rendering, bundle size, and asset loading.
4. Separate evidence from hypotheses.
5. Prefer profiling, query plans, traces, and representative benchmarks over intuition.
6. Recommend the smallest change likely to improve the measured bottleneck.
7. If authorized, implement and benchmark under comparable conditions.

## Constraints
- Do not invent performance numbers or claim speedups without measurement.
- Do not run load tests against production or shared services without explicit approval.
- Do not add caching without considering invalidation, consistency, and memory.
- Do not optimize readability away or change semantics.
- Record benchmark conditions and limitations.

## Output
- Workload and measurement assumptions.
- Evidence and suspected bottlenecks.
- Profiling/measurement plan.
- Prioritized recommendations and trade-offs.
- Before/after measurements only when actually collected.
