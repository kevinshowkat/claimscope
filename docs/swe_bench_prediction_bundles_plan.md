# SWE-bench Prediction Bundle Action Plan

## Objectives
- Produce reproducible, provenance-rich prediction bundles (JSONL) for the SWE-bench Verified split that Claimscope can evaluate locally and in CI.
- Establish scalable collection, validation, and publishing workflows that can ingest vendor artifacts or self-generated predictions.
- Keep bundles fresh as new marketing claims are published while maintaining strict quality controls and auditability.

## Guiding Constraints
- **Reproducibility:** Diffs must apply cleanly on pristine task checkouts with no embedded secrets or machine-specific state.
- **Provenance:** Every bundle line records model revision, prompt template, decoding parameters, container image, and run identifier.
- **Scalability:** Processes must support rapid regeneration (hours, not weeks) when fresh claims land.
- **Portability:** Bundles should be environment agnostic and executable inside the official SWE-bench harness containers.

---

## 1. Collection Strategies

### 1.1 Scripted Inference Pipelines (Primary)
1. **Container parity:** Build or pull a hermetic image derived from the official SWE-bench harness Dockerfile and pin it by digest (e.g., `ghcr.io/claimscope/swebench:<date>@sha256:...`).
2. **Task materialization:** For each instance, materialize the repository at the benchmark base commit using the harness dataset metadata.
3. **Context gathering:** Extract issue text, referenced files, and surrounding code with deterministic heuristics (e.g., ripgrep windows ±200 lines, dependency graph hints).
4. **Prompt governance:** Store prompt templates under `prompts/<id>.txt`, reference them by stable IDs (`pt:claimscope/swe:v1:repair`), and log the literal prompt in the bundle metadata.
5. **Inference sweeps:** Run pinned model endpoints or local weights with deterministic seeds. Default ladder: `(t=0.0, n=1)`, `(t=0.2, n=2)`, `(t=0.6, n=2)` using the same seed for reproducibility.
6. **Patch capture:** Apply model edits to a working tree, stage with `git add -A`, and export diffs using canonical flags (`git diff --cached --unified=3 --no-color --src-prefix=a/ --dst-prefix=b/ --ignore-cr-at-eol`).
7. **Bundle emission:** Emit one JSON object per candidate containing `instance_id`, `model_name_or_path`, `model_patch`, provenance, inference metadata, patch metadata, and a deterministic `content_hash` over patch + prompt + decoding config.
8. **Targeted subsets:** Support `--instances` filters or repo prefix filters so analysts can generate bundles for claim-specific slices without reprocessing the full Verified set.

### 1.2 Ingest Third-Party Predictions
1. **Source discovery:** Track official SWE-bench experiment repos, vendor blog attachments, and shared leaderboards for `all_preds.jsonl`, `patch.diff`, or zipped artifacts.
2. **Normalizer script:** Convert foreign formats into the Claimscope bundle schema, mapping available provenance fields (model, date, run logs). Compute missing hashes and stamp `generator: claimscope-normalizer@<version>`.
3. **Integrity checks:** Validate the original artifact checksum when provided and store it alongside the normalized bundle for audit.

### 1.3 Human-in-the-Loop Pruning (Optional)
1. **Review CLI:** Implement `claimscope bundle review` to present candidate diffs, allowing reviewers to approve, reject, or rerank up to `k` variants per instance.
2. **Audit trail:** Record reviewer UUID, decision, and timestamp in `provenance.human_review` along with a cosign signature when available.
3. **Guardrails:** Provide quick filters for oversized diffs (>5000 LOC), binary blobs, or vendor directories; rejected candidates are logged for model feedback loops.

### 1.4 Diff Normalization Rules
- Enforce LF endings (`dos2unix`).
- Strip timestamps, index hashes, and any environment-specific metadata.
- Reject binary hunks and renormalize rename headers.
- Require `git apply --3way --check` success on a pristine checkout before accepting a patch for the bundle.

---

## 2. Validation & Auto-Repair Pipeline

### 2.1 Structural Gates
1. **Schema validation:** JSON Schema (`claimscope.swe.v1.json`) ensures required fields, types, and size constraints.
2. **Patch dry run:** For every line, reset the repo and run `git apply --3way --check`. Fail fast on conflicts or whitespace-only issues.
3. **Scope limits:** Configurable limits on files changed (default ≤10), total added lines (≤400), and deny-list directories (e.g., `docs/`, `examples/`) unless referenced by the issue.
4. **Secret scanning:** Pass diffs through `gitleaks` or equivalent patterns for API keys, tokens, and unsafe shelling out.
5. **Encoding check:** Guarantee UTF-8 with normalized newlines.

### 2.2 Static & Smoke Testing
1. **Language-aware checks:**
   - Python: `python -m py_compile`, `ruff --select E,F --exit-non-zero-on-fix`, optional `mypy` if project uses typing.
   - JavaScript/TypeScript (future splits): `eslint --max-warnings=0`, `tsc --noEmit`.
2. **Impacted test sampling:** Use heuristics (changed filenames, symbol search) to select a minimal test subset and run `pytest -q -k <pattern>` with a tight timeout (≤90s) before the full harness.
3. **Dependency sanity:** Run repo-specific quick checks (e.g., `poetry check`, `npm test -- --runInBand --findRelatedTests`).

### 2.3 Safe Auto-Repair
1. **Whitespace fixes:** Re-run diffs through `git apply --reject --whitespace=fix` and regenerate clean patches when only formatting fails.
2. **Formatters:** Apply project-standard formatters (e.g., `black`, `ruff --fix-only I`, `isort`, `prettier`) to touched files only.
3. **EOF hygiene:** Ensure newline at EOF and strip trailing spaces.
4. **Failure policy:** If structural or static checks still fail after safe fixes, flag the line as `status: rejected:auto_repair_failed` and exclude it from release bundles.

### 2.4 Pre-Harness Certification
- Summarize validation outcomes per instance (pass/fail, attempted fixes, tooling versions) and attach the report to the bundle manifest for transparency.

---

## 3. Storage, Versioning, and Publication

### 3.1 Repository Layout (Git Source of Truth)
```
bundles/
  verified/
    YYYY-MM-DD.<vendor-or-origin>.<model-id>/
      predictions.claimscope.v1.jsonl
      MANIFEST.yaml
      prompts/
      receipts/            # filled after harness runs
schemas/
  claimscope.swe.v1.json
index.json                 # bundle catalog with tags and metadata
```
- Use signed commits/tags for releases.
- Enforce append-only policy; new bundles replace old ones via `replaces:` field in `MANIFEST.yaml` without mutating history.

### 3.2 MANIFEST Schema (YAML)
```yaml
bundle_id: urn:claimscope:swe:verified:2024-10-01.vendorx.gpt4mini
schema_version: claimscope.swe.v1
source_claim:
  - actor: Vendor X
    url: https://example.com/blog
    date: 2024-09-28
model:
  name: gpt-4.1-mini
  vendor: OpenAI
  revision: 2024-09-12
  endpoint: api
prompt_template_id: pt:claimscope/swe:v1:repair
container_image: ghcr.io/claimscope/swebench@sha256:...
decoding_defaults:
  temperature: 0.2
  top_p: 0.95
  max_tokens: 8192
  seed: 1234
hashes:
  file: sha256:...
  lines:
    sympy__sympy-20590: sha256:...
receipts: {}
```

### 3.3 OCI Artifact Mirror (Optional but Recommended)
- Push bundles using ORAS with media type `application/vnd.claimscope.swe-bundle.v1+jsonl`.
- Tag: `swebench/verified/<model>/<claim-date>-<run-id>`.
- Attach in-toto/SLSA provenance and harness receipts as OCI refs for downstream consumers.

### 3.4 CI Integration
1. **Validation job:** On PRs touching `bundles/**`, run schema validation, normalization checks, static/dry-run prechecks, and summarize results.
2. **Harness execution:** Run `python -m swebench.harness.run_evaluation` scoped to changed instance IDs with limited parallelism.
3. **Receipt generation:** Store harness metrics (pass rate, average time) in `receipts/results.json` and per-instance statuses in `receipts/instances.jsonl`.
4. **Artifact publication:** Upload receipts as build artifacts and commit them back when runs succeed.

---

## 4. Freshness & Monitoring

### 4.1 Claim Intake
- Watch vendor RSS feeds, SWE-bench leaderboard updates, and social channels with lightweight scrapers.
- Auto-open GitHub issues/PRs with prefilled MANIFEST skeletons referencing the claim and awaiting predictions.

### 4.2 Rapid Reproduction Profiles
- Maintain ready-to-run inference configs for top models (e.g., `gpt-4.1-mini`, `o3-mini`, `Llama-3.1-70B-Instruct` via vLLM).
- Trigger batch inference on relevant subsets immediately when new claims arrive; default SLA: bundle draft within 24 hours.

### 4.3 Bundle Deprecation Policy
- When a vendor updates numbers, ingest the new run as a fresh bundle and mark prior bundles as superseded via `replaces:` + `superseded_by:` fields.
- Never mutate released JSONL; treat bundles as immutable receipts.

### 4.4 Community Contributions
- Provide contribution guidelines and templates so external analysts can drop normalized bundles with minimal friction.
- Require validation CI to pass before merge; automatically publish receipts for accepted bundles.

---

## 5. Prediction Augmentation & Synthesis (When Vendors Withhold Artifacts)

### 5.1 Direct Reproduction
- Re-run the vendor-claimed model with documented prompts/decoding settings; mark bundle entries with `derived_from` referencing the public claim URL.

### 5.2 Cost-Constrained Distillation
- Use affordable open models (7B–13B) with retrieval augmentation to generate multiple candidates per instance.
- Rank candidates using validation signals (static checks, diff size, smoke tests) and keep the best-scoring patch; document the surrogate model in metadata.

### 5.3 Program Repair Loop
- Wrap generated patches in a bounded auto-repair loop (≤3 iterations) applying formatters, import fixers, and basic lint-driven edits before revalidating.

### 5.4 Synthetic Backports & Hard Negatives
- Identify upstream commits related to benchmark issues and backport partial fixes to craft near-miss patches for evaluation sanity checks. Clearly label as synthetic in metadata.

### 5.5 Third-Party Bundle Normalization
- Continuously ingest public prediction dumps (e.g., SWE-bench experiments repos) into Claimscope format to cross-check vendor claims even without direct collaboration.

---

## 6. Implementation Roadmap

| Timeframe | Milestone | Key Tasks |
|-----------|-----------|-----------|
| Week 1 | **Scaffold infrastructure** | Add JSON Schema, create bundle repo layout, implement `claimscope bundle validate/precheck` CLI, set up CI validation workflow. |
| Week 2 | **Bootstrap content** | Ingest 2–3 public runs, normalize into Claimscope bundles, and generate harness receipts locally and in CI. |
| Week 3 | **Inference pipeline MVP** | Ship scripted inference runner with prompt registry, diff normalization, and metadata emission for a 50-instance Verified slice. |
| Week 4 | **Human review + auto-repair** | Deliver review CLI, implement auto-repair heuristics, and add validation summary reporting. |
| Week 5+ | **Scaling & monitoring** | Automate claim intake, set up OCI artifact publishing, onboard external contributors, and formalize freshness SLAs. |

---

## 7. Success Metrics
- ≥95% of bundle lines pass structural validation and dry-run patch checks on first submission.
- Harness verification turnaround ≤24 hours for new claims (including CI receipts).
- All released bundles carry complete provenance and reproducible hashes; auditors can re-run predictions with documented configs.
- Growing catalog of bundles covering ≥80% of high-profile SWE-bench Verified claims within two weeks of publication.

