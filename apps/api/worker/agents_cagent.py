"""Offline runner for the cAgent-12 suite."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from packages.harness.cagent import TASKS_PATH
from packages.harness.cagent.tools import TOOLS


@dataclass
class StepTrace:
    tool: str
    input: str
    output: str
    expected: str
    success: bool
    elapsed_ms: float
    error: str | None = None


@dataclass
class TaskOutcome:
    task_id: str
    name: str
    description: str
    success: bool
    final_answer: str
    expected_final: str
    steps: List[StepTrace]
    duration_ms: float


def _load_tasks() -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    for path in sorted(Path(TASKS_PATH).glob("*.y*ml")):
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                raise ValueError(f"Task file {path.name} malformed")
            data.setdefault("allowed_tools", [])
            tasks.append(data)
    return tasks


def _call_tool(tool: str, raw_input: str) -> str:
    if tool not in TOOLS:
        raise KeyError(f"unsupported tool: {tool}")
    func = TOOLS[tool]
    result = func(raw_input)
    return str(result)


def run_cagent_suite() -> Tuple[Dict[str, Any], List[float], Dict[str, Any]]:
    tasks = _load_tasks()
    outcomes: List[TaskOutcome] = []
    tool_calls = 0
    tool_errors = 0
    wall_times: List[float] = []

    for task in tasks:
        steps_data = task.get("steps", [])
        expected_final = str(task.get("final_answer", "")).strip()
        task_start = time.perf_counter()
        traces: List[StepTrace] = []
        task_success = True

        for step in steps_data:
            tool = step.get("tool")
            raw_input = str(step.get("input", ""))
            expected = str(step.get("expect", "")).strip()
            tool_calls += 1
            t0 = time.perf_counter()
            error: str | None = None
            output: str
            try:
                output = _call_tool(tool, raw_input)
            except Exception as exc:  # noqa: BLE001 deterministic error capture
                output = str(exc)
                error = str(exc)
                tool_errors += 1
                task_success = False
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            success = error is None and output.strip() == expected
            if not success:
                task_success = False
            traces.append(
                StepTrace(
                    tool=tool,
                    input=raw_input,
                    output=output,
                    expected=expected,
                    success=success,
                    elapsed_ms=elapsed_ms,
                    error=error,
                )
            )

        duration_ms = (time.perf_counter() - task_start) * 1000.0
        wall_times.append(duration_ms)

        outcomes.append(
            TaskOutcome(
                task_id=str(task.get("id")),
                name=str(task.get("name", "")),
                description=str(task.get("description", "")),
                success=task_success,
                final_answer=expected_final,
                expected_final=expected_final,
                steps=traces,
                duration_ms=duration_ms,
            )
        )

    successes = sum(1 for o in outcomes if o.success)
    total = len(outcomes) or 1
    success_rate = successes / total
    tool_error_rate = tool_errors / tool_calls if tool_calls else 0.0
    action_timeout_rate = 0.0  # deterministic offline harness

    sorted_wall = sorted(wall_times)
    if sorted_wall:
        idx = int(0.95 * (len(sorted_wall) - 1))
        p95_wall = sorted_wall[idx] / 1000.0
    else:
        p95_wall = 0.0

    trace_payload = {
        "suite": "cAgent-12",
        "success_rate": success_rate,
        "tool_error_rate": tool_error_rate,
        "action_timeout_rate": action_timeout_rate,
        "tasks": [
            {
                "id": o.task_id,
                "name": o.name,
                "description": o.description,
                "success": o.success,
                "duration_ms": round(o.duration_ms, 3),
                "expected_final": o.expected_final,
                "steps": [
                    {
                        "tool": s.tool,
                        "input": s.input,
                        "output": s.output,
                        "expected": s.expected,
                        "success": s.success,
                        "elapsed_ms": round(s.elapsed_ms, 3),
                        "error": s.error,
                    }
                    for s in o.steps
                ],
            }
            for o in outcomes
        ],
    }

    artifact_json = json.dumps(trace_payload, ensure_ascii=False, indent=2)
    artifact_b64 = base64.b64encode(artifact_json.encode("utf-8")).decode("ascii")
    artifact = {
        "name": "agent_trace.json",
        "content_type": "application/json",
        "data_url": f"data:application/json;base64,{artifact_b64}",
        "sha256": None,
        "bytes": len(artifact_json.encode("utf-8")),
    }

    result = {
        "score_value": success_rate,
        "metrics": {
            "success@1": success_rate,
            "success@3": success_rate,
            "tool_error_rate": tool_error_rate,
            "action_timeout_rate": action_timeout_rate,
        },
        "ops": {
            "p95_latency_s": round(p95_wall, 3),
            "cost_usd": 0.0,
            "tokens_prompt": 0,
            "tokens_output": 0,
            "tool_error_rate": round(tool_error_rate, 3),
            "action_timeout_rate": round(action_timeout_rate, 3),
        },
    }

    return result, wall_times, artifact
