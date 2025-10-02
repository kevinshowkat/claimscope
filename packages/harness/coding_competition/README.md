# Claimscope Coding Competition Suite

This in-house benchmark targets comparative coding claims. Each task describes a
small but non-trivial algorithmic challenge plus a deterministic test harness.

- Dataset: `tasks.json` (prompt + unit-test snippets).
- Evaluation: run each prompt with the same system/user instruction and require
  models to emit Python solutions that satisfy the tests.
- Metrics: per-task pass/fail, aggregate pass@1, token telemetry (optional).

See `apps/api/worker/coding_competition.py` for the execution harness.
