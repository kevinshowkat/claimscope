#!/usr/bin/env python3
"""Validate Claimscope SWE-bench prediction bundles."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - defensive
    raise SystemExit("PyYAML is required to run claimscope_bundle_validate") from exc

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError as exc:  # pragma: no cover - defensive
    raise SystemExit("jsonschema is required to run claimscope_bundle_validate") from exc


REQUIRED_MANIFEST_FIELDS = {"version", "dataset", "split", "predictions"}


def _load_schema(schema_path: Path) -> Draft202012Validator:
    data = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(data)


def _load_manifest(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("MANIFEST.yaml must decode to a mapping")
    missing = REQUIRED_MANIFEST_FIELDS - data.keys()
    if missing:
        raise ValueError(f"MANIFEST.yaml missing required fields: {sorted(missing)}")
    return data


def _iter_predictions(predictions_path: Path) -> Iterable[dict]:
    for line_number, raw_line in enumerate(predictions_path.read_text(encoding="utf-8").splitlines(), start=1):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            item = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"Prediction on line {line_number} must be an object")
        yield item


def _run(cmd: List[str], *, cwd: Path | None = None, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    return result


def _check_patch(patch: str, repo: Path) -> None:
    process = _run(["git", "apply", "--check", "--3way"], cwd=repo, input_text=patch)
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip() or "<no output>"
        raise RuntimeError(f"git apply --check --3way failed:\n{message}")


def _run_optional(cmd: List[str], description: str, *, cwd: Path | None = None) -> None:
    process = _run(cmd, cwd=cwd)
    if process.returncode != 0:
        raise RuntimeError(
            f"{description} failed (exit {process.returncode}):\n{process.stdout}{process.stderr}"
        )


def validate_bundle(bundle_dir: Path, schema_path: Path, repo_path: Path | None) -> None:
    manifest_path = bundle_dir / "MANIFEST.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing MANIFEST.yaml in {bundle_dir}")

    manifest = _load_manifest(manifest_path)

    predictions_path = bundle_dir / manifest["predictions"]
    if not predictions_path.exists():
        raise FileNotFoundError(f"Predictions file not found: {predictions_path}")

    validator = _load_schema(schema_path)

    for prediction in _iter_predictions(predictions_path):
        errors = sorted(validator.iter_errors(prediction), key=lambda e: e.path)
        if errors:
            details = "; ".join(f"{'/'.join(map(str, err.path)) or '<root>'}: {err.message}" for err in errors)
            raise ValueError(f"Prediction failed schema validation: {details}")
        if repo_path is not None:
            try:
                _check_patch(prediction["model_patch"], repo_path)
            except KeyError as exc:
                raise ValueError("Prediction missing required field 'model_patch'") from exc

    script_path = Path(__file__)

    _run_optional([sys.executable, "-m", "py_compile", str(script_path)], "py_compile")

    try:
        _run_optional(["ruff", "check", str(script_path)], "ruff lint")
    except FileNotFoundError:
        print("ruff not installed; skipping lint", file=sys.stderr)

    try:
        _run_optional(["mypy", "--ignore-missing-imports", str(script_path)], "mypy type-check")
    except FileNotFoundError:
        print("mypy not installed; skipping type-check", file=sys.stderr)

    try:
        _run_optional([
            "gitleaks",
            "detect",
            "--no-banner",
            "--redact",
            "--source",
            str(bundle_dir),
        ], "gitleaks scan")
    except FileNotFoundError:
        print("gitleaks not installed; skipping secret scan", file=sys.stderr)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Claimscope SWE-bench prediction bundle")
    parser.add_argument("bundle", type=Path, help="Path to bundle directory")
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "schemas" / "claimscope.swe.v1.json",
        help="Path to Claimscope SWE-bench schema",
    )
    parser.add_argument("--repo", type=Path, default=None, help="Optional git repository for git apply --check")
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        validate_bundle(args.bundle, args.schema, args.repo)
    except Exception as exc:  # pragma: no cover - CLI entry point
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
