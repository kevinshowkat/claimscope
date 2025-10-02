"""Offline MMMU vision harness for deterministic claim validation."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

DATA_PATH = Path(__file__).resolve().parent / "data" / "vision_mmmu.json"

MMMU_DATASET_ID = "mmmu-mini@claimscope-demo"
MMMU_DATASET_DIGEST = "a6f9b1c0f1a2d7c54b90c5c1d94f47c8bdee12f7a6bb47df9f5fd8c6fb8b8f21"


class MMMUDataError(RuntimeError):
    """Raised when MMMU fixtures are missing or malformed."""


@dataclass
class BenchmarkEntry:
    name: str
    accuracy: float
    n: int
    ops: Dict[str, Any]
    latencies: List[float]

    @property
    def score_value(self) -> float:
        return self.accuracy


@dataclass
class MMMUBenchmark:
    dataset_id: str
    metric: str
    size: int
    models: Dict[str, BenchmarkEntry]

    @classmethod
    def load(cls, path: Path = DATA_PATH) -> "MMMUBenchmark":
        if not path.exists():
            raise MMMUDataError(f"Vision benchmark fixture not found: {path}")
        payload = json.loads(path.read_text())
        try:
            dataset_id = payload["dataset_id"]
            metric = payload["metric"]
            size = int(payload.get("n") or 0)
            models_raw: Mapping[str, Mapping[str, Any]] = payload["models"]
        except (KeyError, TypeError, ValueError) as exc:
            raise MMMUDataError("Invalid MMMU fixture payload") from exc

        models: Dict[str, BenchmarkEntry] = {}
        for name, spec in models_raw.items():
            try:
                accuracy = float(spec["accuracy"])
                n = int(spec.get("n") or size)
                ops = dict(spec.get("ops") or {})
                latencies = [float(v) for v in spec.get("latencies", [])]
            except (TypeError, ValueError, KeyError) as exc:
                raise MMMUDataError(f"Malformed entry for {name}") from exc
            models[name] = BenchmarkEntry(name=name, accuracy=accuracy, n=n, ops=ops, latencies=latencies)
        return cls(dataset_id=dataset_id, metric=metric, size=size, models=models)

    def resolve(self, model_name: str) -> BenchmarkEntry:
        lowered = model_name.lower().strip()
        lookup: Dict[str, BenchmarkEntry] = {name.lower(): entry for name, entry in self.models.items()}
        if lowered in lookup:
            return lookup[lowered]
        # attempt partial match (e.g., missing "vision")
        for key, entry in lookup.items():
            if lowered in key:
                return entry
        raise MMMUDataError(f"Model '{model_name}' not present in MMMU fixtures")

    def leaderboard(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        ranked = sorted(self.models.values(), key=lambda entry: entry.score_value, reverse=True)
        if limit is not None:
            ranked = ranked[:limit]
        return [
            {
                "model": entry.name,
                self.metric: round(entry.score_value, 4),
                "n": entry.n,
            }
            for entry in ranked
        ]


def _collect_comparators(benchmark: MMMUBenchmark, comparators: Sequence[str]) -> Tuple[Dict[str, BenchmarkEntry], List[str]]:
    available: Dict[str, BenchmarkEntry] = {}
    missing: List[str] = []
    for name in comparators:
        try:
            entry = benchmark.resolve(name)
        except MMMUDataError:
            missing.append(name)
            continue
        if entry.name not in available:
            available[entry.name] = entry
    return available, missing


def run_mmmu_subset(
    *,
    model_name: str,
    comparators: Sequence[str] | None = None,
    n: Optional[int] = None,
) -> Tuple[Dict[str, Any], List[float], Dict[str, Any]]:
    """Return MMMU accuracy for the target model and comparator metadata."""

    benchmark = MMMUBenchmark.load()
    subject = benchmark.resolve(model_name)
    available, missing = _collect_comparators(benchmark, comparators or [])

    sample_size = subject.n or benchmark.size or n or 0
    result = {
        "score_value": subject.score_value,
        "n": sample_size,
        "ops": subject.ops,
        "metrics": {benchmark.metric: subject.score_value},
    }

    comparator_payload = {
        "available": {
            name: {
                benchmark.metric: entry.score_value,
                "n": entry.n,
            }
            for name, entry in available.items()
        },
        "missing": list(missing),
        "leaderboard": benchmark.leaderboard(limit=10),
        "metric": benchmark.metric,
    }

    return result, subject.latencies, comparator_payload


__all__ = [
    "MMMU_DATASET_DIGEST",
    "MMMU_DATASET_ID",
    "MMMUDataError",
    "run_mmmu_subset",
]
