# Trace Manifest Logging

Each successful harness run now records a reproducibility manifest in the `traces` table. Entries capture:

- `harness_cmd` — command string or label for the harness execution path.
- `harness_commit_sha` — SHA-256 digest of the harness code for the run.
- `dataset_id` / `dataset_hash` — logical dataset identifier plus digest of the pinned assets (tasks, fixtures, static apps).
- `params` — JSON payload describing runtime parameters (budget, subset size, etc.).
- `seeds` — deterministic seeds used for sampling or task ordering.
- `tokens_prompt` / `tokens_output` — budget usage for LLM suites (0 for offline harnesses).
- `latency_breakdown` — p50/p95 summary and raw samples when available.

## Inspecting Traces Locally

```bash
# connect to Postgres inside docker-compose
psql postgres://postgres:postgres@localhost:5432/claimscope -c "SELECT run_id, harness_cmd, dataset_id, harness_commit_sha FROM traces ORDER BY created_at DESC LIMIT 5;"
```

Artifacts remain attached via the existing `artifacts` table, so downstream jobs can pair manifests with produced files like `agent_trace.json` or `playwright_trace.zip`.
