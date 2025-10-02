"""Playwright-powered runner for the deterministic cGUI-10 suite."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple
import zipfile

from .trace_manifest import compute_digest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_DIR = REPO_ROOT / "packages" / "harness" / "cgui"
CONFIG_PATH = PACKAGE_DIR / "playwright.config.ts"
REPORT_PATH = PACKAGE_DIR / "playwright-report.json"
TEST_RESULTS_DIR = PACKAGE_DIR / "test-results"
PLAYWRIGHT_MARKER = PACKAGE_DIR / ".playwright-installed"


@dataclass
class TestResult:
    name: str
    status: str
    duration_ms: float
    attachments: List[Dict[str, Any]]


def _ensure_dependencies(env: Dict[str, str]) -> None:
    node_modules = PACKAGE_DIR / "node_modules"
    if not node_modules.exists():
        subprocess.run(["npm", "install"], cwd=PACKAGE_DIR, check=True, env=env)

    if not PLAYWRIGHT_MARKER.exists():
        subprocess.run(
            ["npx", "playwright", "install", "chromium"],
            cwd=PACKAGE_DIR,
            check=True,
            env=env,
        )
        PLAYWRIGHT_MARKER.write_text("chromium\n", encoding="utf-8")


def _collect_results() -> List[TestResult]:
    if not REPORT_PATH.exists():
        raise FileNotFoundError("playwright-report.json not found")
    with REPORT_PATH.open("r", encoding="utf-8") as fh:
        report = json.load(fh)

    collected: List[TestResult] = []

    def walk(suite: Dict[str, Any]) -> None:
        for child in suite.get("suites", []):
            walk(child)
        for spec in suite.get("specs", []):
            test_name = spec.get("title", "")
            for test in spec.get("tests", []):
                # Only track first result (no retries configured)
                result = test.get("results", [{}])[0]
                collected.append(
                    TestResult(
                        name=test_name,
                        status=result.get("status", "unknown"),
                        duration_ms=float(result.get("duration", 0.0)),
                        attachments=result.get("attachments", []),
                    )
                )

    walk(report.get("suites", [report])[0])
    if not collected and "suites" not in report:
        # fallback for single suite reports
        for spec in report.get("specs", []):
            result = spec.get("tests", [{}])[0]
            collected.append(
                TestResult(
                    name=spec.get("title", ""),
                    status=result.get("status", "unknown"),
                    duration_ms=float(result.get("duration", 0.0)),
                    attachments=result.get("attachments", []),
                )
            )
    return collected


def _bundle_traces(results: List[TestResult]) -> Tuple[str, int]:
    trace_paths: List[Path] = []
    for result in results:
        for attachment in result.attachments:
            if attachment.get("name") == "trace" and attachment.get("path"):
                raw_path = Path(attachment["path"])
                if not raw_path.is_absolute():
                    raw_path = (PACKAGE_DIR / raw_path).resolve()
                trace_paths.append(raw_path)

    if not trace_paths:
        return "", 0

    with tempfile.TemporaryDirectory() as td:
        bundle_path = Path(td) / "playwright_trace.zip"
        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in trace_paths:
                if not path.exists():
                    continue
                arcname = path.name
                if arcname in zf.namelist():
                    arcname = f"{path.parent.name}_{arcname}"
                zf.write(path, arcname=arcname)

        data = bundle_path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    data_url = f"data:application/zip;base64,{encoded}"
    return data_url, len(data)


def run_cgui_suite() -> Tuple[Dict[str, Any], List[float], Dict[str, Any] | None, Dict[str, Any]]:
    env = os.environ.copy()
    env.setdefault("CGUI_BASE_URL", "http://localhost:3999")

    _ensure_dependencies(env)

    if REPORT_PATH.exists():
        REPORT_PATH.unlink()
    if TEST_RESULTS_DIR.exists():
        shutil.rmtree(TEST_RESULTS_DIR)

    cmd = [
        "npx",
        "playwright",
        "test",
        "--config",
        str(CONFIG_PATH),
    ]
    completed = subprocess.run(cmd, cwd=PACKAGE_DIR, env=env, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "Playwright suite failed",
            completed.stdout,
            completed.stderr,
        )

    results = _collect_results()
    total = len(results) or 1
    passes = sum(1 for result in results if result.status == "passed")
    timeouts = sum(1 for result in results if result.status == "timedOut")
    durations_ms = [result.duration_ms for result in results]

    sorted_ms = sorted(durations_ms)
    p95 = 0.0
    if sorted_ms:
        index = int(0.95 * (len(sorted_ms) - 1))
        p95 = sorted_ms[index] / 1000.0

    bundle_url, bundle_size = _bundle_traces(results)

    metrics = {
        "task_success": passes / total,
        "timeout_rate": timeouts / total,
        "timeouts": timeouts,
    }

    result = {
        "score_value": metrics["task_success"],
        "metrics": metrics,
        "ops": {
            "p95_latency_s": round(p95, 3),
            "cost_usd": 0.0,
            "tokens_prompt": 0,
            "tokens_output": 0,
            "timeout_rate": round(metrics["timeout_rate"], 3),
        },
    }

    artifact: Dict[str, Any] | None = None
    if bundle_size > 0 and bundle_url:
        artifact = {
            "name": "playwright_trace.zip",
            "content_type": "application/zip",
            "data_url": bundle_url,
            "bytes": bundle_size,
            "sha256": None,
        }

    durations = [ms / 1000.0 for ms in durations_ms]

    tests_dir = PACKAGE_DIR / "tests"
    web_app_dir = REPO_ROOT / "apps" / "web" / "app" / "cgui"
    static_dir = REPO_ROOT / "apps" / "web" / "public" / "cgui"

    dataset_paths = (
        [p for p in tests_dir.rglob("*.ts")]
        + [p for p in web_app_dir.rglob("*.tsx")]
        + [p for p in static_dir.rglob("*") if p.is_file()]
    )
    harness_paths = [Path(__file__), CONFIG_PATH]

    metadata = {
        "suite": "cGUI-10",
        "dataset_id": "cgui-10",
        "dataset_hash": compute_digest(dataset_paths),
        "harness_hash": compute_digest(harness_paths),
        "seeds": {"playwright": 0},
        "params": {
            "test_count": len(results),
            "base_url": env["CGUI_BASE_URL"],
        },
    }

    return result, durations, artifact, metadata
