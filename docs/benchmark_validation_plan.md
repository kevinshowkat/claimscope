# Benchmark Validation Plan

This playbook captures the near-term replication work for open benchmarks cited in `docs/claimscope_marketing_claims.csv`. Each entry lists the scope, harness owner, blockers, and the precise lines in the marketing claims table that reference the benchmark so analysts can trace provenance.

## SWE-bench Verified
- **Claim rows:** `docs/claimscope_marketing_claims.csv:2`, `:3`, `:7`, `:10`, `:18`, `:20`
- **Dataset:** `princeton-nlp/SWE-bench_Verified` (Hugging Face); 500 GitHub repos with scripted patches.
- **Harness approach:** reuse existing SWE-bench Lite docker image but pin commit `74a5e21`. Drive via `python -m swebench.benchmark.run` with a patched config that disables parallel patch application.
- **Plumbing tasks:**
  - [x] Add `packages/harness/swebench` with fixtures for smoke tests and document external bundle requirements.
  - [x] Implement `apps/api/worker/coding_swebench.py` and integrate worker routing so `task` strings containing `SWE-bench` dispatch to the harness.
  - [x] Wrap the upstream harness in `packages/harness/swebench/cli.py` so predictions+Docker environments execute end-to-end when provided.
  - [ ] Distribute production predictions bundles (LLM outputs) or build automation to fetch them from claims.
- **Blockers:** needs 120 GB disk for repo snapshots; confirm cache strategy before CI integration.
- **Notes:** Set `SWEBENCH_CLI_ENTRYPOINT` and `SWEBENCH_DATASET_ROOT` to point at the production bundle; use `SWEBENCH_FIXTURE_ONLY=1` to force fixture-backed smoke runs.

## GPQA Diamond
- **Claim row:** `docs/claimscope_marketing_claims.csv:11`
- **Dataset:** `openai/grade-school-math` style but use `openai/GPQA` from the GPQA paper release.
- **Harness approach:** deterministic multiple-choice scorer. Parse questions, use LLM to select option, compare to answer key.
- **Plumbing tasks:**
  1. Create `packages/harness/gpqa` with JSON manifest and evaluation script using the open-source key.
  2. Add `apps/api/worker/reasoning_gpqa.py` runner that enforces `temperature=0`, `top_p=0` and records accuracy plus calibration entropy.
- **Blockers:** dataset license requires citation; add to trace manifest.

## Aider Polyglot
- **Claim rows:** `docs/claimscope_marketing_claims.csv:18`, `:21`
- **Dataset:** `aider/aider-polyglot-benchmark` (GitHub tasks with expected diffs).
- **Harness approach:** run each task in isolated repo using aider CLI automation; compute pass@1 on diff validation.
- **Plumbing tasks:**
  1. Vendor aider harness wrapper in `packages/harness/aider_polyglot` with pinned commit and offline fixtures.
  2. Implement `apps/api/worker/coding_aider.py` to orchestrate repos, enforce max tool calls, and capture token/tool metrics for claims about efficiency.
- **Blockers:** aide CLI requires python3.11 and git; ensure docker image ships both.

## MMMU
- **Claim rows:** `docs/claimscope_marketing_claims.csv:10`, `:30`
- **Status:** already covered by `apps/api/worker/vision_mmmu.py`; verify dataset digest `MMMU_DATASET_DIGEST` stays aligned with upstream release.
- **Plumbing tasks:** add recency alert so marketing claims pull the correct MMMU variant when new version releases.

## HumanEval
- **Claim row:** `docs/claimscope_marketing_claims.csv:33`
- **Status:** supported by `apps/api/worker/coding_humaneval.py` (25-sample subset). Need to expose full-pass evaluation toggle for marketing claims referencing complete HumanEval.
- **Plumbing tasks:** surface `settings.samples` in claim ingestion; allow 164-problem full run with deterministic seed.

## MathVista
- **Claim row:** `docs/claimscope_marketing_claims.csv:34`
- **Dataset:** `lxuechen/mathvista` (Hugging Face) with official evaluation script.
- **Harness approach:** offline rendering of problems with required figures; use VQA scoring script to compute overall accuracy.
- **Plumbing tasks:**
  1. Add `packages/harness/mathvista` with dataset downloader and scoring notebook converted to CLI.
  2. Implement `apps/api/worker/vision_mathvista.py` to stream prompts, collect answers, and run scoring.
- **Blockers:** dataset bundles large image assets (~22 GB); ensure caching strategy in infra.

## LongFact and FactScore
- **Claim row:** `docs/claimscope_marketing_claims.csv:26`
- **Dataset:** `longfact/LongFact` and `openai/FactScore` (Hugging Face JSONL).
- **Harness approach:** pair QA prompts with gold fact tables; compute factual error rate. Use deterministic judge configs for reproducibility.
- **Plumbing tasks:**
  1. Create `packages/harness/factuality` combining both datasets with shared scoring utilities.
  2. Add `apps/api/worker/factuality_longfact.py` to route claims requesting hallucination reduction; emit baseline diffs when referencing percent-error drops.
- **Blockers:** judge models require closed weights; default to open-source alternatives (e.g., `gpt-4o-mini` analog) or human-labeled subsets for validation.

---

**Next Actions**
1. Socialize disk/network budget requirements with infra (SWE-bench + MathVista heavy downloads).
2. Prioritize SWE-bench Verified harness implementation; it unlocks six marketing claims immediately.
3. Draft trace manifest updates once each harness skeleton lands to ensure provenance is logged.
