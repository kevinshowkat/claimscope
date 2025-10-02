"""Run SWE-bench Verified evaluations.

The real evaluation flow is heavy: it needs repository snapshots, applies the
model-generated patches, builds the projects, and executes regression tests.
This module keeps the orchestration logic lightweight so the worker can either
call into a bundled CLI (for production) or fall back to deterministic fixtures
for smoke testing.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .logging_utils import get_logger

logger = get_logger("swebench")

DATASET_ID = "princeton-nlp/SWE-bench_Verified"
FIXTURE_FILENAME = "verified_sample.jsonl"
DEFAULT_MAX_CASES = 25


@dataclass
class EvaluationCase:
    instance_id: str
    repo: str
    total_tests: int
    passing_tests: int

    @property
    def passed(self) -> bool:
        return self.total_tests > 0 and self.passing_tests >= self.total_tests


class FixtureLoader:
    """Utility to load bundled SWE-bench fixture rows."""

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    def load(self, name: str = FIXTURE_FILENAME) -> List[EvaluationCase]:
        path = self.base_path / name
        if not path.exists():
            raise FileNotFoundError(f"Fixture {name} not found under {self.base_path}")
        cases: List[EvaluationCase] = []
        with path.open("r", encoding="ascii") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                cases.append(
                    EvaluationCase(
                        instance_id=payload["instance_id"],
                        repo=payload.get("repo", "unknown"),
                        total_tests=int(payload.get("total_tests", 0)),
                        passing_tests=int(payload.get("passing_tests", 0)),
                    )
                )
        return cases


class SwebenchRunner:
    """Wrapper around the SWE-bench CLI or bundled fixtures."""

    def __init__(
        self,
        *,
        dataset_root: Optional[Path] = None,
        cli_path: Optional[Path] = None,
        fixture_loader: Optional[FixtureLoader] = None,
    ) -> None:
        self.dataset_root = dataset_root
        self.cli_path = cli_path
        self.fixture_loader = fixture_loader

    def _run_cli(
        self,
        *,
        limit: int,
        seed: int,
        predictions_path: Path,
        dataset_name: Optional[str],
        run_id: str,
        max_workers: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> Tuple[Dict[str, Any], List[float]]:
        if not self.cli_path:
            raise RuntimeError("SWE-bench CLI path not configured")
        if not predictions_path.exists():
            raise RuntimeError(f"Predictions file missing: {predictions_path}")

        cmd = [
            "python",
            str(self.cli_path),
            "--predictions",
            str(predictions_path),
            "--run-id",
            run_id,
        ]
        if dataset_name:
            cmd.extend(["--dataset-name", dataset_name])
        if limit:
            cmd.extend(["--limit", str(limit)])
        if max_workers:
            cmd.extend(["--max-workers", str(max_workers)])
        if timeout:
            cmd.extend(["--timeout", str(timeout)])

        logger.info("Running SWE-bench CLI: %s", " ".join(cmd))
        t0 = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        dt = time.time() - t0
        if proc.returncode != 0:
            logger.error("SWE-bench CLI failed: %s", proc.stderr[:512])
            raise RuntimeError(f"SWE-bench CLI failed with exit code {proc.returncode}")

        output = proc.stdout.strip()
        try:
            payload = json.loads(output) if output else {}
        except json.JSONDecodeError as exc:
            logger.exception("Unable to parse SWE-bench CLI output: %s", output[:256])
            raise RuntimeError("SWE-bench CLI produced invalid JSON") from exc

        latencies = payload.get("latencies") or [dt]
        result = {
            "score_value": float(payload.get("accuracy", 0.0)),
            "n": int(payload.get("completed", 0)),
            "ops": {
                "wall_time_s": round(dt, 3),
                "p95_latency_s": round(max(latencies) if latencies else dt, 3),
                "cost_usd": float(payload.get("approx_cost_usd", 0.0)),
            },
            "cases": payload.get("cases", []),
            "report_path": payload.get("report_path"),
        }
        return result, [float(v) for v in latencies]

    def _run_fixture(self, limit: int, seed: int) -> Tuple[Dict[str, Any], List[float]]:
        if not self.fixture_loader:
            raise RuntimeError("Fixture loader unavailable for SWE-bench fallback")
        cases = self.fixture_loader.load()
        rng = random.Random(seed)
        rng.shuffle(cases)
        selected = cases[:limit] if limit else cases
        latencies: List[float] = []
        passed = 0
        evaluated_cases = []
        for case in selected:
            # Deterministic pseudo latency centred around 18 seconds per run.
            millis = 16000 + (case.total_tests * 350)
            jitter = rng.randint(0, 1500)
            latency = (millis + jitter) / 1000.0
            latencies.append(latency)
            verdict = case.passed
            passed += int(verdict)
            evaluated_cases.append(
                {
                    "instance_id": case.instance_id,
                    "repo": case.repo,
                    "passed": verdict,
                    "total_tests": case.total_tests,
                    "passing_tests": case.passing_tests,
                }
            )
        n = len(selected)
        accuracy = passed / n if n else 0.0
        lat_sorted = sorted(latencies)
        p95 = lat_sorted[int(0.95 * (len(lat_sorted) - 1))] if latencies else 0.0
        result = {
            "score_value": accuracy,
            "n": n,
            "ops": {
                "wall_time_s": round(sum(latencies), 3),
                "p95_latency_s": round(p95, 3),
                "cost_usd": 0.0,
            },
            "cases": evaluated_cases,
        }
        return result, latencies

    def run(self, *, limit: int, seed: int) -> Tuple[Dict[str, Any], List[float]]:
        return self._run_fixture(limit, seed)


def run_swebench_verified(
    *,
    limit: int = DEFAULT_MAX_CASES,
    seed: int = 1234,
    dataset_root: Optional[str] = None,
    cli_entrypoint: Optional[str] = None,
    predictions_path: Optional[str] = None,
    run_identifier: str,
    max_workers: Optional[int] = None,
    timeout: Optional[int] = None,
) -> Tuple[Dict[str, Any], List[float]]:
    """Execute a SWE-bench Verified evaluation.

    Parameters mirror the knobs referenced in marketing claims (trial count and
    deterministic seed). When the CLI entrypoint and dataset root are not
    provided, the harness falls back to bundled fixtures so CI can exercise the
    codepath without requiring the full benchmark assets.
    """

    dataset_path = Path(dataset_root) if dataset_root else None
    repo_root = Path(__file__).resolve().parents[3]
    default_cli = repo_root / "packages" / "harness" / "swebench" / "cli.py"
    cli_path = Path(cli_entrypoint) if cli_entrypoint else default_cli
    fixture_base = repo_root / "packages" / "harness" / "swebench" / "fixtures"
    loader = FixtureLoader(fixture_base)
    runner = SwebenchRunner(dataset_root=dataset_path, cli_path=cli_path, fixture_loader=loader)
    if os.getenv("SWEBENCH_FIXTURE_ONLY") == "1" or not predictions_path:
        return runner.run(limit=limit, seed=seed)

    dataset_name = dataset_root if dataset_root else "princeton-nlp/SWE-bench_Verified"
    return runner._run_cli(
        limit=limit,
        seed=seed,
        predictions_path=Path(predictions_path),
        dataset_name=dataset_name,
        run_id=run_identifier,
        max_workers=max_workers,
        timeout=timeout,
    )
