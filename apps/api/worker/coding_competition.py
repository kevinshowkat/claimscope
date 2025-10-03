"""Claimscope coding competition harness.

Runs the in-house comparative coding benchmark by generating Python solutions
for each task, executing the embedded tests, and recording pass/fail outcomes
per model.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from anthropic import Anthropic

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None  # type: ignore

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore

from .logging_utils import get_logger

os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("GOOGLE_CLOUD_DISABLE_ALTS", "1")

logger = get_logger("coding_competition")

_DEFAULT_TEST_TIMEOUT_S = max(5.0, float(os.getenv("CODING_COMPETITION_TEST_TIMEOUT", "12")))


def _extract_python_code(response: str) -> str:
    """Normalize model output into runnable Python source."""
    stripped = response.strip()
    if "```" not in stripped:
        return stripped
    lines = stripped.splitlines()
    in_block = False
    accumulator = []
    for line in lines:
        marker = line.strip()
        if marker.startswith("```"):
            if not in_block:
                in_block = True
                continue
            break
        if in_block:
            accumulator.append(line)
    if accumulator:
        return "\n".join(accumulator).strip()
    return stripped

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
    test_latency_s: float
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
        if hasattr(client, "responses"):
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
        else:
            chat = client.chat.completions.create(
                model=name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=2048,
            )
            latency = time.time() - t0
            text = "".join(choice.message.content or "" for choice in getattr(chat, "choices", []) or [])
            usage = getattr(chat, "usage", None)
            input_tokens = int(getattr(usage, "prompt_tokens", 0))
            output_tokens = int(getattr(usage, "completion_tokens", 0))
        return ModelInvocation(name, provider, text, input_tokens, output_tokens, latency)

    if provider in {"google", "gemini", "google_gemini"}:
        if genai is None:
            raise CodingBenchError("google-generativeai package not installed")
        api_key = _resolve_api_key(api_key_ref, "GOOGLE_GEMINI_API_KEY")
        if not api_key:
            raise CodingBenchError("GOOGLE_GEMINI_API_KEY not configured")
        genai.configure(api_key=api_key)
        def _build_model(name_candidate: str):
            full = name_candidate if name_candidate.lower().startswith("models/") else f"models/{name_candidate}"
            return genai.GenerativeModel(model_name=full, system_instruction=SYSTEM_PROMPT), full

        client, model_name = _build_model(name)
        generation_config = {"temperature": temperature, "max_output_tokens": 2048}
        t0 = time.time()
        try:
            response = client.generate_content(prompt, generation_config=generation_config)
        except Exception as exc:  # pragma: no cover
            error_text = str(exc).lower()
            if "not found" in error_text or "unsupported" in error_text:
                fallback_names = []
                if not model_name.endswith("-latest"):
                    fallback_names.append(f"{model_name}-latest")
                fallback_names.extend(
                    [
                        "models/gemini-2.5-pro",
                        "models/gemini-2.0-pro-exp",
                        "models/gemini-2.0-pro",
                        "models/gemini-1.5-pro-latest",
                    ]
                )
                discovered = None
                for fallback in fallback_names:
                    try:
                        client, model_name = _build_model(fallback)
                        response = client.generate_content(prompt, generation_config=generation_config)
                        break
                    except Exception:
                        continue
                else:
                    discovered = _discover_gemini_model(
                        [
                            "gemini-2.5-pro-latest",
                            "gemini-2.5-pro",
                            "gemini-2.0-pro-exp",
                            "gemini-2.0-pro",
                            "gemini-1.5-pro-latest",
                        ]
                    )
                    if not discovered:
                        raise
                    client, model_name = _build_model(discovered)
                    response = client.generate_content(prompt, generation_config=generation_config)
            else:
                raise
        latency = time.time() - t0
        text = getattr(response, "text", None)
        if not text:
            candidates = getattr(response, "candidates", []) or []
            parts: List[str] = []
            blocked = False
            for candidate in candidates:
                safety = getattr(candidate, "safety_ratings", []) or []
                if any(getattr(rating, "blocked", False) for rating in safety):
                    blocked = True
                    continue
                content = getattr(candidate, "content", None)
                if content is None:
                    continue
                for part in getattr(content, "parts", []) or []:
                    value = getattr(part, "text", None)
                    if value:
                        parts.append(value)
            if not parts and blocked:
                logger.warning("gemini response blocked by safety filters", extra={"model": model_name})
            text = "".join(parts)
        usage = getattr(response, "usage_metadata", None)
        input_tokens = 0
        output_tokens = 0
        if isinstance(usage, dict):
            input_tokens = int(usage.get("prompt_token_count", 0))
            output_tokens = int(usage.get("candidates_token_count", 0))
        reported = model_name.split("/")[-1] if model_name else name
        return ModelInvocation(reported, "gemini", text or "", input_tokens, output_tokens, latency)

    raise CodingBenchError(f"Unsupported provider for coding bench: {provider}")


def _run_tests(task: Dict[str, Any], solution: str) -> TaskResult:
    tests = task.get("tests") or []
    if not tests:
        raise CodingBenchError(f"Task {task.get('id')} missing tests")
    with tempfile.TemporaryDirectory() as td:
        source = _extract_python_code(solution)
        path = Path(td) / "solution.py"
        path.write_text(source, encoding="utf-8")
        setup = [
            "import importlib.util, sys",
            "spec = importlib.util.spec_from_file_location('solution', 'solution.py')",
            "module = importlib.util.module_from_spec(spec)",
            "spec.loader.exec_module(module)",
            "sys.modules['solution'] = module",
            "globals().update({name: getattr(module, name) for name in dir(module) if not name.startswith('_')})",
        ]
        checks = []
        for idx, case in enumerate(tests):
            script = case.get("script")
            if script:
                if isinstance(script, list):
                    lines = [str(line) for line in script]
                else:
                    lines = str(script).splitlines()
                checks.extend(lines)
                continue

            expr = case.get("input")
            if not expr:
                continue
            result_var = f"_result_{idx}"
            expected = case.get("expected")
            raises = case.get("raises")
            message = case.get("message")
            if raises:
                checks.append("try:")
                checks.append(f"    {result_var} = {expr}")
                checks.append(f"except {raises} as _exc_{idx}:")
                if message:
                    checks.append(f"    assert str(_exc_{idx}) == {message!r}, 'expected message {message!r}'")
                else:
                    checks.append("    pass")
                checks.append("else:")
                checks.append(f"    raise AssertionError('Expected {raises}')")
            else:
                if expected is None:
                    raise CodingBenchError(f"Test case missing expected value for task {task.get('id')} expression {expr}")
                checks.extend(
                    [
                        f"{result_var} = {expr}",
                        f"assert repr({result_var}) == {expected!r}, f\"Expected {expected!r}, got {{repr({result_var})}}\"",
                    ]
                )
        script = "\n".join([*setup, *checks])
        runner = Path(td) / "runner.py"
        runner.write_text(script, encoding="utf-8")
        started = time.perf_counter()
        python_bin = os.environ.get("CLAIMSCOPE_PYTHON_BIN") or sys.executable or "python"
        try:
            subprocess.run(
                [python_bin, str(runner)],
                cwd=td,
                capture_output=True,
                text=True,
                timeout=_DEFAULT_TEST_TIMEOUT_S,
                check=True,
            )
            duration = time.perf_counter() - started
            return TaskResult(task_id=str(task.get("id")), success=True, test_latency_s=duration)
        except subprocess.CalledProcessError as exc:  # pragma: no cover
            duration = time.perf_counter() - started
            return TaskResult(
                task_id=str(task.get("id")),
                success=False,
                test_latency_s=duration,
                stderr=exc.stderr or exc.stdout,
            )
        except subprocess.TimeoutExpired:  # pragma: no cover
            duration = time.perf_counter() - started
            return TaskResult(task_id=str(task.get("id")), success=False, test_latency_s=duration, stderr="timeout")


def run_coding_competition(
    *,
    tasks: Optional[Iterable[Dict[str, Any]]] = None,
    primary_config: Dict[str, Any],
    comparator_configs: List[Dict[str, Any]],
    temperature: float = 0.0,
    max_workers: Optional[int] = None,
) -> Dict[str, Any]:
    tasks_data = list(tasks) if tasks else _load_tasks()
    if not tasks_data:
        raise CodingBenchError("no tasks available for coding competition")
    if not comparator_configs:
        raise CodingBenchError("comparators required for coding competition")

    active_tasks: List[Tuple[int, Dict[str, Any]]] = []
    for idx, task in enumerate(tasks_data):
        if task.get("prompt"):
            active_tasks.append((idx, task))
    if not active_tasks:
        raise CodingBenchError("no valid prompts available for coding competition")

    task_index_lookup = {original_idx: pos for pos, (original_idx, _) in enumerate(active_tasks)}

    total_models = 1 + len(comparator_configs)
    default_workers = max(16, min(total_models * 8, 64))
    worker_env = os.getenv("CODING_COMPETITION_MAX_WORKERS")
    if max_workers is None:
        if worker_env:
            try:
                max_workers = max(1, int(worker_env))
            except ValueError:
                max_workers = default_workers
        else:
            max_workers = default_workers
    else:
        max_workers = max(1, max_workers)

    num_tasks = len(active_tasks)
    num_comparators = len(comparator_configs)

    primary_results: List[Optional[TaskResult]] = [None] * num_tasks
    primary_invocations: List[Optional[ModelInvocation]] = [None] * num_tasks
    comparator_invocations: List[List[Optional[Tuple[ModelInvocation, TaskResult]]]] = [
        [None] * num_comparators for _ in range(num_tasks)
    ]

    def _evaluate(
        task_pos: int,
        task_data: Dict[str, Any],
        cfg: Dict[str, Any],
        comparator_index: int,
        is_primary: bool,
    ) -> Tuple[int, bool, int, ModelInvocation, TaskResult]:
        prompt = task_data.get("prompt")
        model_name = cfg.get("name", "unknown")
        provider = cfg.get("provider", "unknown")
        try:
            invocation = _call_model(cfg, prompt, temperature)
            result = _run_tests(task_data, invocation.response)
        except Exception as exc:  # pragma: no cover - external API errors dominate here
            logger.exception(
                "coding_competition model invocation failed",
                extra={
                    "task": task_data.get("id"),
                    "model": model_name,
                    "provider": provider,
                },
            )
            invocation = ModelInvocation(
                model=model_name,
                provider=provider,
                response="",
                input_tokens=0,
                output_tokens=0,
                latency_s=0.0,
            )
            result = TaskResult(
                task_id=str(task_data.get("id")),
                success=False,
                test_latency_s=0.0,
                stderr=str(exc)[:500],
            )
        return task_pos, is_primary, comparator_index, invocation, result

    logger.info(
        "coding_competition starting", extra={
            "tasks": len(active_tasks),
            "models": total_models,
            "max_workers": max_workers,
            "test_timeout_s": _DEFAULT_TEST_TIMEOUT_S,
        }
    )

    futures = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for task_pos, task in active_tasks:
            futures.append(
                executor.submit(
                    _evaluate,
                    task_pos,
                    task,
                    primary_config,
                    -1,
                    True,
                )
            )
            for comp_idx, comparator_cfg in enumerate(comparator_configs):
                futures.append(
                    executor.submit(
                        _evaluate,
                        task_pos,
                        task,
                        comparator_cfg,
                        comp_idx,
                        False,
                    )
                )

        for future in as_completed(futures):
            task_pos, is_primary, comparator_index, invocation, result = future.result()
            target_idx = task_index_lookup.get(task_pos)
            if target_idx is None:
                continue
            if is_primary:
                primary_invocations[target_idx] = invocation
                primary_results[target_idx] = result
            else:
                comparator_invocations[target_idx][comparator_index] = (invocation, result)

    logger.info(
        "coding_competition complete",
        extra={
            "primary_avg_latency": sum(inv.latency_s for inv in primary_invocations) / len(primary_invocations),
            "primary_avg_test_latency": sum(res.test_latency_s for res in primary_results) / len(primary_results),
        },
    )

    # Ensure all results are present
    for idx, result in enumerate(primary_results):
        if result is None or primary_invocations[idx] is None:
            raise CodingBenchError("primary model evaluation incomplete")
        for comp_idx, value in enumerate(comparator_invocations[idx]):
            if value is None:
                raise CodingBenchError("comparator evaluation incomplete")

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

    for idx, (original_idx, task) in enumerate(active_tasks):
        primary_invocation = primary_invocations[idx]
        primary_result = primary_results[idx]
        task_record = {
            "task_id": task.get("id"),
            "primary": {
                "model": primary_invocation.model,
                "provider": primary_invocation.provider,
                    "success": primary_result.success,
                    "stderr": primary_result.stderr,
                    "input_tokens": primary_invocation.input_tokens,
                    "output_tokens": primary_invocation.output_tokens,
                    "latency_s": primary_invocation.latency_s,
                    "test_latency_s": primary_result.test_latency_s,
                },
                "comparators": [],
            }

        for comp_idx, (invocation, result) in enumerate(comparator_invocations[idx]):
            summary = comparators_summary[comp_idx]
            summary["attempted"] += 1
            if result.success:
                summary["passed"] += 1
            summary["input_tokens"] += invocation.input_tokens
            summary["output_tokens"] += invocation.output_tokens
            summary["latencies"].append(invocation.latency_s)
            task_record["comparators"].append(
                {
                    "model": invocation.model,
                    "provider": invocation.provider,
                    "success": result.success,
                    "stderr": result.stderr,
                    "input_tokens": invocation.input_tokens,
                    "output_tokens": invocation.output_tokens,
                    "latency_s": invocation.latency_s,
                    "test_latency_s": result.test_latency_s,
                }
            )

        per_task.append(task_record)

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
_GEMINI_DISCOVERY_CACHE: Dict[str, str] = {}
_GEMINI_DISCOVERY_TS = 0.0
_GEMINI_DISCOVERY_TTL = 300.0  # seconds


def _discover_gemini_model(preferred: Sequence[str]) -> Optional[str]:
    if genai is None:
        return None
    global _GEMINI_DISCOVERY_CACHE, _GEMINI_DISCOVERY_TS
    now = time.time()
    if not _GEMINI_DISCOVERY_CACHE or now - _GEMINI_DISCOVERY_TS > _GEMINI_DISCOVERY_TTL:
        try:
            models = list(genai.list_models())
        except Exception:  # pragma: no cover - discovery failure is acceptable
            return None
        cache: Dict[str, str] = {}
        for model in models:
            name = getattr(model, "name", None)
            if not name:
                continue
            methods = getattr(model, "supported_generation_methods", []) or []
            if "generateContent" not in methods:
                continue
            short = name.split("/")[-1]
            cache[short] = name
        _GEMINI_DISCOVERY_CACHE = cache
        _GEMINI_DISCOVERY_TS = now
    for candidate in preferred:
        normalized = candidate.split("/")[-1]
        if normalized in _GEMINI_DISCOVERY_CACHE:
            return _GEMINI_DISCOVERY_CACHE[normalized]
    if _GEMINI_DISCOVERY_CACHE:
        # Return the most "advanced" looking model by sorting descending lexicographically
        return sorted(_GEMINI_DISCOVERY_CACHE.values(), reverse=True)[0]
    return None
