"""Thin wrapper around the official SWE-bench harness.

This script filters predictions to a requested subset, delegates execution to
`swebench.harness.run_evaluation.main`, then emits a compact JSON summary on
stdout so the Claimscope worker can aggregate status/metrics.

Environment prerequisites:
- Docker daemon accessible to the process (the upstream harness builds images per repo).
- Predictions file in JSONL or JSON list format containing objects with
  `instance_id`, `model`, and `model_patch` fields.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Iterable, List, Sequence

from swebench.harness.constants import KEY_INSTANCE_ID, KEY_MODEL
from swebench.harness.run_evaluation import main as swebench_main


def _load_predictions(path: Path) -> List[dict]:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass

    preds: List[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                preds.append(obj)
    return preds


def _write_predictions(path: Path, predictions: Sequence[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for item in predictions:
            handle.write(json.dumps(item, ensure_ascii=True))
            handle.write("\n")


def _subset(predictions: List[dict], limit: int | None, instance_ids: Iterable[str] | None) -> List[dict]:
    pool = predictions
    if instance_ids:
        wanted = {inst for inst in instance_ids}
        pool = [pred for pred in pool if pred.get(KEY_INSTANCE_ID) in wanted]
    if limit is not None and limit >= 0:
        pool = pool[:limit]
    return pool


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SWE-bench evaluation via Claimscope helper")
    parser.add_argument("--predictions", required=True, help="Path to predictions JSONL/JSON file")
    parser.add_argument("--dataset-name", default="princeton-nlp/SWE-bench_Verified", help="Dataset name or local JSON file")
    parser.add_argument("--split", default="test", help="Dataset split")
    parser.add_argument("--limit", type=int, default=None, help="Max number of predictions to evaluate")
    parser.add_argument("--instance-id", action="append", dest="instance_ids", help="Instance IDs to include (can repeat)")
    parser.add_argument("--run-id", required=True, help="Unique run identifier (propagated to harness logs)")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--cache-level", default="env")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--namespace", default="swebench")
    parser.add_argument("--instance-image-tag", default="latest")
    parser.add_argument("--open-file-limit", type=int, default=4096)
    parser.add_argument("--report-dir", default=".")
    args = parser.parse_args()

    predictions_path = Path(args.predictions)
    if not predictions_path.exists():
        json.dump({"error": f"predictions file not found: {predictions_path}"}, sys.stdout)
        sys.stdout.flush()
        return

    predictions = _load_predictions(predictions_path)
    if not predictions:
        json.dump({"error": "no predictions loaded"}, sys.stdout)
        sys.stdout.flush()
        return

    filtered = _subset(predictions, args.limit, args.instance_ids)
    if not filtered:
        json.dump({"error": "filtered predictions empty"}, sys.stdout)
        sys.stdout.flush()
        return

    with tempfile.TemporaryDirectory() as td:
        filtered_path = Path(td) / "predictions.jsonl"
        _write_predictions(filtered_path, filtered)

        report_path = swebench_main(
            dataset_name=args.dataset_name,
            split=args.split,
            instance_ids=[pred[KEY_INSTANCE_ID] for pred in filtered],
            predictions_path=str(filtered_path),
            max_workers=args.max_workers,
            force_rebuild=args.force_rebuild,
            cache_level=args.cache_level,
            clean=args.clean,
            open_file_limit=args.open_file_limit,
            run_id=args.run_id,
            timeout=args.timeout,
            namespace=args.namespace,
            rewrite_reports=False,
            modal=False,
            instance_image_tag=args.instance_image_tag,
            report_dir=args.report_dir,
        )

    try:
        report_data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - best effort parsing
        json.dump({"error": f"failed to parse report: {exc}"}, sys.stdout)
        sys.stdout.flush()
        return

    total = report_data.get("completed_instances", 0)
    resolved_ids = set(report_data.get("resolved_ids", []))
    unresolved_ids = set(report_data.get("unresolved_ids", []))
    error_ids = set(report_data.get("error_ids", []))

    resolved = len(resolved_ids)
    accuracy = resolved / total if total else 0.0

    cases = []
    for pred in filtered:
        instance_id = pred.get(KEY_INSTANCE_ID)
        if not instance_id:
            continue
        if instance_id in resolved_ids:
            status = "resolved"
        elif instance_id in unresolved_ids:
            status = "unresolved"
        elif instance_id in error_ids:
            status = "error"
        else:
            status = "pending"
        cases.append(
            {
                "instance_id": instance_id,
                "status": status,
                "model": pred.get(KEY_MODEL),
            }
        )

    payload = {
        "accuracy": accuracy,
        "completed": total,
        "resolved": resolved,
        "cases": cases,
        "report_path": str(report_path),
    }
    json.dump(payload, sys.stdout)
    sys.stdout.flush()


if __name__ == "__main__":
    main()
