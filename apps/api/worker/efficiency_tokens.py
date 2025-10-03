"""Token efficiency telemetry harness.

This module replays a bundle of prompts across a primary model and one or more
comparators, capturing token usage and simple latency metrics so efficiency
claims can be validated with machine-verifiable logs.

The primary model configuration comes from the run's `model_config`, while the
claim settings must supply comparator configurations under
`settings["telemetry"]["comparators"]` and the prompts under
`settings["telemetry"]["prompts"]`.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from anthropic import Anthropic

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - optional dependency
    genai = None  # type: ignore

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore


class TokenTelemetryError(RuntimeError):
    """Raised when the telemetry harness cannot complete."""


@dataclass
class TelemetryResult:
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_s: float


def _resolve_api_key(ref: Optional[str], fallback_env: Optional[str] = None) -> Optional[str]:
    if ref:
        key = os.getenv(ref)
        if key:
            return key
    if fallback_env:
        return os.getenv(fallback_env)
    return None


def _call_anthropic(model: str, prompt: str, api_key: str, *, temperature: float, max_tokens: int) -> TelemetryResult:
    client = Anthropic(api_key=api_key)
    t0 = time.time()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    latency = time.time() - t0
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0))
    output_tokens = int(getattr(usage, "output_tokens", 0))
    total_tokens = int(getattr(usage, "total_tokens", input_tokens + output_tokens))
    return TelemetryResult(
        model=model,
        provider="anthropic",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        latency_s=latency,
    )


def _call_openai(model: str, prompt: str, api_key: str, *, temperature: float, max_tokens: int) -> TelemetryResult:
    if OpenAI is None:
        raise TokenTelemetryError("openai python package not installed; cannot call OpenAI provider")
    client = OpenAI(api_key=api_key)
    t0 = time.time()
    response = client.responses.create(
        model=model,
        input=prompt,
        temperature=temperature,
        max_output_tokens=max_tokens,
    )
    latency = time.time() - t0
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0))
    output_tokens = int(getattr(usage, "output_tokens", 0))
    total_tokens = int(getattr(usage, "total_tokens", input_tokens + output_tokens))
    return TelemetryResult(
        model=model,
        provider="openai",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        latency_s=latency,
    )


def _call_gemini(model: str, prompt: str, api_key: str, *, temperature: float, max_tokens: int) -> TelemetryResult:
    if genai is None:
        raise TokenTelemetryError("google-generativeai package not installed; cannot call Gemini provider")
    genai.configure(api_key=api_key)
    client = genai.GenerativeModel(model_name=model)
    generation_config = {"temperature": temperature, "max_output_tokens": max_tokens}
    t0 = time.time()
    response = client.generate_content(prompt, generation_config=generation_config)
    latency = time.time() - t0
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict):
        input_tokens = int(usage.get("prompt_token_count", 0))
        output_tokens = int(usage.get("candidates_token_count", 0))
        total_tokens = int(usage.get("total_token_count", input_tokens + output_tokens))
    else:
        input_tokens = output_tokens = 0
        total_tokens = 0
    return TelemetryResult(
        model=model,
        provider="gemini",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        latency_s=latency,
    )


def _call_model(config: Dict[str, Any], prompt: str, *, temperature: float, max_tokens: int) -> TelemetryResult:
    provider = (config.get("provider") or "anthropic").lower()
    name = config.get("name")
    if not name:
        raise TokenTelemetryError("model name missing from configuration")
    api_key_ref = config.get("api_key_ref")
    if provider == "anthropic":
        api_key = _resolve_api_key(api_key_ref, "ANTHROPIC_API_KEY")
        if not api_key:
            raise TokenTelemetryError("ANTHROPIC_API_KEY not configured for telemetry run")
        return _call_anthropic(name, prompt, api_key, temperature=temperature, max_tokens=max_tokens)
    if provider == "openai":
        api_key = _resolve_api_key(api_key_ref, "OPENAI_API_KEY")
        if not api_key:
            raise TokenTelemetryError("OPENAI_API_KEY not configured for telemetry run")
        return _call_openai(name, prompt, api_key, temperature=temperature, max_tokens=max_tokens)
    if provider in {"google", "gemini", "google_gemini"}:
        api_key = _resolve_api_key(api_key_ref, "GOOGLE_GEMINI_API_KEY")
        if not api_key:
            raise TokenTelemetryError("GOOGLE_GEMINI_API_KEY not configured for telemetry run")
        return _call_gemini(name, prompt, api_key, temperature=temperature, max_tokens=max_tokens)
    raise TokenTelemetryError(f"Unsupported provider for telemetry: {provider}")


def _summarise(results: Sequence[Sequence[TelemetryResult]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "latencies": [],
    }
    for prompt_results in results:
        if not prompt_results:
            continue
        # index 0 is always the primary run
        primary = prompt_results[0]
        out["requests"] += 1
        out["input_tokens"] += primary.input_tokens
        out["output_tokens"] += primary.output_tokens
        out["total_tokens"] += primary.total_tokens
        out.setdefault("per_prompt", []).append(
            {
                "model": primary.model,
                "provider": primary.provider,
                "input_tokens": primary.input_tokens,
                "output_tokens": primary.output_tokens,
                "total_tokens": primary.total_tokens,
                "latency_s": primary.latency_s,
            }
        )
        out["latencies"].append(primary.latency_s)
    return out


def run_efficiency_telemetry(
    *,
    prompts: Iterable[str],
    primary_config: Dict[str, Any],
    comparator_configs: Sequence[Dict[str, Any]],
    temperature: float = 0.0,
    max_output_tokens: int = 1024,
) -> Dict[str, Any]:
    if not prompts:
        raise TokenTelemetryError("telemetry prompts are required")
    if not comparator_configs:
        raise TokenTelemetryError("at least one comparator configuration is required")

    per_prompt_results: List[List[TelemetryResult]] = []
    comparator_totals = [
        {
            "model": cfg.get("name"),
            "provider": cfg.get("provider"),
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "latencies": [],
        }
        for cfg in comparator_configs
    ]

    for raw_prompt in prompts:
        prompt = raw_prompt.strip()
        if not prompt:
            continue
        prompt_results: List[TelemetryResult] = []

        primary = _call_model(
            primary_config,
            prompt,
            temperature=temperature,
            max_tokens=max_output_tokens,
        )
        prompt_results.append(primary)

        for index, comparator_cfg in enumerate(comparator_configs):
            comparator = _call_model(
                comparator_cfg,
                prompt,
                temperature=temperature,
                max_tokens=max_output_tokens,
            )
            prompt_results.append(comparator)
            comparator_totals[index]["input_tokens"] += comparator.input_tokens
            comparator_totals[index]["output_tokens"] += comparator.output_tokens
            comparator_totals[index]["total_tokens"] += comparator.total_tokens
            comparator_totals[index]["latencies"].append(comparator.latency_s)

        per_prompt_results.append(prompt_results)

    primary_summary = _summarise(per_prompt_results)
    total_primary_output = primary_summary["output_tokens"] or 1  # avoid div by zero

    comparator_summaries = []
    for totals in comparator_totals:
        output_tokens = totals["output_tokens"]
        savings_pct = None
        if output_tokens:
            savings_pct = (1 - (total_primary_output / output_tokens)) * 100.0
        comparator_summaries.append({
            **totals,
            "requests": len(totals["latencies"]),
            "savings_pct": savings_pct,
        })

    return {
        "primary": primary_summary,
        "comparators": comparator_summaries,
        "latencies": primary_summary.pop("latencies", []),
    }
