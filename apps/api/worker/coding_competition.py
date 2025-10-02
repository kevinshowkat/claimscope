"""Claimscope coding competition harness.

Runs the in-house comparative coding benchmark by generating Python solutions
for each task, executing the embedded tests, and recording pass/fail outcomes
per model.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from anthropic import Anthropic

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore

TASKS_PATH = Path(__file__).resolve().parents[3] / "packages" / "harness" / "coding_competition" / "tasks.json"
SYSTEM_PROMPT = (
    "You are a careful senior Python engineer. Generate only Python code that solves the task. "
    "Do not provide explanations or markdown."
)


class CodingBenchError(RuntimeError):
    """Raised when the coding benchmark cannot run to completion."""


@dataclass
class ModelInvocation:
    model: str
    provider: str
    response: str
    input_tokens: int
    output_tokens: int
    latency_s: float


@dataclass
class TaskResult:
    task_id: str
    success: bool
    stderr: Optional[str] = None


def _load_tasks() -> List[Dict[str, Any]]:
    if not TASKS_PATH.exists():
        raise CodingBenchError(f"coding competition tasks file missing: {TASKS_PATH}")
    return json.loads(TASKS_PATH.read_text(encoding="utf-8"))


def _resolve_api_key(ref: Optional[str], fallback_env: Optional[str]) -> Optional[str]:
    if ref:
        key = os.getenv(ref)
        if key:
            return key
    if fallback_env:
        return os.getenv(fallback_env)
    return None


def _call_model(config: Dict[str, Any], prompt: str, temperature: float) -> ModelInvocation:
    provider = (config.get("provider") or "anthropic").lower()
    name = config.get("name")
    if not name:
        raise CodingBenchError("model name missing from configuration")
    api_key_ref = config.get("api_key_ref")

    if provider == "anthropic":
        api_key = _resolve_api_key(api_key_ref, "ANTHROPIC_API_KEY")
        if not api_key:
            raise CodingBenchError("ANTHROPIC_API_KEY not configured")
        client = Anthropic(api_key=api_key)
        t0 = time.time()
        message = client.messages.create(
            model=name,
            max_tokens=2048,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
            system=SYSTEM_PROMPT,
        )
        latency = time.time() - t0
        text = "".join(block.text for block in message.content if getattr(block, "type", "text") == "text")
        usage = getattr(message, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0))
        output_tokens = int(getattr(usage, "output_tokens", 0))
        return ModelInvocation(name, provider, text, input_tokens, output_tokens, latency)

    if provider == "openai":
        if OpenAI is None:
            raise CodingBenchError("openai package not installed")
        api_key = _resolve_api_key(api_key_ref, "OPENAI_API_KEY")
        if not api_key:
            raise CodingBenchError("OPENAI_API_KEY not configured")
        client = OpenAI(api_key=api_key)
        t0 = time.time()
        response = client.responses.create(
            model=name,
            input=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            temperature=temperature,
            max_output_tokens=2048,
        )
        latency = time.time() - t0
        text = "".join(part.text for part in response.output_text)
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0))
        output_tokens = int(getattr(usage, "output_tokens", 0))
        return ModelInvocation(name, provider, text, input_tokens, output_tokens, latency)

    raise CodingBenchError(f"Unsupported provider for coding bench: {provider}")


def _run_tests(task: Dict[str, Any], solution: str) -> TaskResult:
    tests = task.get("tests") or []
    if not tests:
        raise CodingBenchError(f"Task {task.get('id')} missing tests")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "solution.py"
        path.write_text(solution, encoding="utf-8")
        setup = [
            "import importlib.util, sys",
            "spec = importlib.util.spec_from_file_location('solution', 'solution.py')",
            "module = importlib.util.module_from_spec(spec)",
            "spec.loader.exec_module(module)",
        ]
        checks = []
        for case in tests:
            expr = case.get("input")
            expected = case.get("expected")
            checks.append(
                f"print(repr({expr})) if repr({expr}) == '{expected}' else (_ for _ in ()).throw(AssertionError('Expected {expected}'))"
            )
        script = "\n".join([*setup, *checks])
        runner = Path(td) / "runner.py"
        runner.write_text(script, encoding="utf-8")
        try:
            subprocess.run(["python", str(runner)], cwd=td, capture_output=True, text=True, timeout=20, check=True)
            return TaskResult(task_id=str(task.get("id")), success=True)
        except subprocess.CalledProcessError as exc:  # pragma: no cover
            return TaskResult(task_id=str(task.get("id")), success=False, stderr=exc.stderr or exc.stdout)
        except subprocess.TimeoutExpired:  # pragma: no cover
            return TaskResult(task_id=str(task.get("id")), success=False, stderr="timeout")


def run_coding_competition(
    *,
    tasks: Optional[Iterable[Dict[str, Any]]] = None,
    primary_config: Dict[str, Any],
    comparator_configs: List[Dict[str, Any]],
    temperature: float = 0.0,
) -> Dict[str, Any]:
    tasks_data = list(tasks) if tasks else _load_tasks()
    if not tasks_data:
        raise CodingBenchError("no tasks available for coding competition")
    if not comparator_configs:
        raise CodingBenchError("comparators required for coding competition")

    primary_results = []
    comparators_summary: List[Dict[str, Any]] = [
        {
            "model": cfg.get("name"),
            "provider": cfg.get("provider"),
            "passed": 0,
            "attempted": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "latencies": [],
        }
        for cfg in comparator_configs
    ]

    per_task: List[Dict[str, Any]] = []

    for task in tasks_data:
        prompt = task.get("prompt")
        if not prompt:
            continue
        primary_invocation = _call_model(primary_config, prompt, temperature)
        primary_result = _run_tests(task, primary_invocation.response)
        primary_results.append(primary_result)

        comparator_details = []
        for idx, comparator_cfg in enumerate(comparator_configs):
            invocation = _call_model(comparator_cfg, prompt, temperature)
            result = _run_tests(task, invocation.response)
            summary = comparators_summary[idx]
            summary["attempted"] += 1
            if result.success:
                summary["passed"] += 1
            summary["input_tokens"] += invocation.input_tokens
            summary["output_tokens"] += invocation.output_tokens
            summary["latencies"].append(invocation.latency_s)
            comparator_details.append(
                {
                    "model": invocation.model,
                    "provider": invocation.provider,
                    "success": result.success,
                    "stderr": result.stderr,
                    "input_tokens": invocation.input_tokens,
                    "output_tokens": invocation.output_tokens,
                    "latency_s": invocation.latency_s,
                }
            )

        per_task.append(
            {
                "task_id": task.get("id"),
                "primary": {
                    "model": primary_invocation.model,
                    "provider": primary_invocation.provider,
                    "success": primary_result.success,
                    "stderr": primary_result.stderr,
                    "input_tokens": primary_invocation.input_tokens,
                    "output_tokens": primary_invocation.output_tokens,
                    "latency_s": primary_invocation.latency_s,
                },
                "comparators": comparator_details,
            }
        )

    primary_passed = sum(1 for result in primary_results if result.success)
    total_tasks = len(primary_results)

    baseline_summary = {
        "passed": primary_passed,
        "attempted": total_tasks,
        "pass_rate": primary_passed / total_tasks if total_tasks else 0.0,
    }

    comparator_outputs = []
    for summary in comparators_summary:
        attempted = summary["attempted"] or 1
        comparator_outputs.append(
            {
                **summary,
                "pass_rate": summary["passed"] / attempted,
                "avg_latency_s": (sum(summary["latencies"]) / attempted) if summary["latencies"] else 0.0,
            }
        )

    return {
        "baseline": baseline_summary,
        "comparators": comparator_outputs,
        "tasks": per_task,
    }
