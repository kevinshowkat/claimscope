# SWE-bench Verified Harness

This directory scaffolds the evaluation assets Claimscope uses to reproduce
SWE-bench Verified claims. The full benchmark is heavy (~120 GB of repository
snapshots) so only lightweight metadata ships with the repo. Production runs
mount the artifact bundle built from:

- `princeton-nlp/SWE-bench_Verified` Hugging Face dataset
- Pinned SWE-bench harness commit `74a5e21`
- Deterministic scaffold invoking bash + string-edit tools only

For local smoke tests, developers can point the worker to the fixture file in
`fixtures/verified_sample.jsonl`, which contains a short subset of repository
IDs and expected verdicts. The coding worker consumes these fixtures via
`apps/api/worker/coding_swebench.py` when `SWEBENCH_FIXTURE_ONLY=1` is set.

### Full evaluation

The `cli.py` module wraps the upstream harness so a call like the following
evaluates an arbitrary predictions file and writes the upstream report JSON to
disk:

```bash
python packages/harness/swebench/cli.py \
  --predictions /path/to/predictions.jsonl \
  --dataset-name princeton-nlp/SWE-bench_Verified \
  --run-id local_run_001 \
  --limit 25
```

Requirements:
- Docker daemon accessible to the process (the official harness builds images).
- Predictions file structured as JSON lines with `instance_id`, `model`, and
  `model_patch` fields.
- Optional: set `SWEBENCH_MAX_WORKERS`, `SWEBENCH_TIMEOUT_S`, or
  `SWEBENCH_PREDICTIONS` to customize worker defaults.

When the worker receives a claim with `task="SWE-bench Verified"`, it expects a
`swebench_predictions` setting pointing to a JSON/JSONL predictions file. If
unset, the run is marked underspecified.

**Usage sketch**

```bash
# Build harness assets
python scripts/build_swebench_bundle.py --output dist/swebench_bundle.tar.gz

# Run smoke evaluation (subset)
SWEBENCH_FIXTURE_ONLY=1 python -m apps.api.worker.coding_swebench
```

The real runner streams repository archives from object storage, applies model
patches, executes unit tests inside an ephemeral sandbox, and aggregates
pass@1 accuracy. See the worker module for detailed behavior.
