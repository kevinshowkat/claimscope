"""Utilities for recording reproducibility metadata for harness runs."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Connection


def _resolve_paths(paths: Optional[Sequence[Any]]) -> list[Path]:
    if not paths:
        return []
    resolved: list[Path] = []
    for entry in paths:
        if isinstance(entry, Path):
            resolved.append(entry.resolve())
        else:
            resolved.append(Path(str(entry)).resolve())
    return [p for p in resolved if p.exists() and p.is_file()]


def compute_digest(paths: Sequence[Any]) -> str:
    files = _resolve_paths(paths)
    digest = hashlib.sha256()
    for file_path in sorted(files, key=lambda p: str(p)):
        digest.update(f"FILE::{file_path.name}".encode("utf-8"))
        digest.update(file_path.read_bytes())
    return digest.hexdigest()


def _percentile(values: Sequence[float], fraction: float) -> Optional[float]:
    data = [float(v) for v in values if v is not None]
    if not data:
        return None
    ordered = sorted(data)
    if len(ordered) == 1:
        return ordered[0]
    index = int(max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction))))
    return ordered[index]


def _as_json(value: Any) -> str:
    if value is None:
        return "null"
    return json.dumps(value)


def record_trace(
    conn: Connection,
    run_id: str,
    *,
    harness_cmd: str,
    harness_digest: Optional[str] = None,
    harness_paths: Optional[Sequence[Any]] = None,
    dataset_id: Optional[str] = None,
    dataset_digest: Optional[str] = None,
    dataset_paths: Optional[Sequence[Any]] = None,
    docker_image_sha: Optional[str] = None,
    params: Optional[dict[str, Any]] = None,
    seeds: Optional[dict[str, Any]] = None,
    tokens_prompt: Optional[int] = None,
    tokens_output: Optional[int] = None,
    latencies: Optional[Sequence[float]] = None,
    cost_usd: Optional[float] = None,
    errors: Optional[dict[str, Any]] = None,
) -> None:
    harness_hash = harness_digest or (compute_digest(harness_paths or []) if harness_paths else None)
    dataset_hash = dataset_digest or (compute_digest(dataset_paths or []) if dataset_paths else None)

    latency_series = [float(v) for v in (latencies or [])]
    latency_payload: Optional[dict[str, Any]] = None
    if latency_series:
        latency_payload = {
            "p50": _percentile(latency_series, 0.5),
            "p95": _percentile(latency_series, 0.95),
            "samples": latency_series,
        }

    trace_id = f"trc_{uuid.uuid4().hex[:12]}"

    conn.execute(
        text(
            """
            INSERT INTO traces (
              id,
              run_id,
              harness_cmd,
              harness_commit_sha,
              dataset_id,
              dataset_commit_sha,
              dataset_hash,
              docker_image_sha,
              params,
              seeds,
              tokens_prompt,
              tokens_output,
              latency_breakdown,
              cost_usd,
              errors
            ) VALUES (
              :id,
              :run_id,
              :harness_cmd,
              :harness_commit_sha,
              :dataset_id,
              :dataset_commit_sha,
              :dataset_hash,
              :docker_image_sha,
              CAST(:params AS JSONB),
              CAST(:seeds AS JSONB),
              :tokens_prompt,
              :tokens_output,
              CAST(:latency AS JSONB),
              :cost_usd,
              CAST(:errors AS JSONB)
            )
            """
        ),
        {
            "id": trace_id,
            "run_id": run_id,
            "harness_cmd": harness_cmd,
            "harness_commit_sha": harness_hash,
            "dataset_id": dataset_id,
            "dataset_commit_sha": None,
            "dataset_hash": dataset_hash,
            "docker_image_sha": docker_image_sha,
            "params": _as_json(params),
            "seeds": _as_json(seeds),
            "tokens_prompt": tokens_prompt,
            "tokens_output": tokens_output,
            "latency": _as_json(latency_payload),
            "cost_usd": cost_usd,
            "errors": _as_json(errors),
        },
    )
