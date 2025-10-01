"""Read-only file system tool for bundled documents."""

from __future__ import annotations

import pathlib
from importlib.resources import files

_ROOT = files("packages.harness.cagent.data").joinpath("files")


def run(path: str) -> str:
    if not path:
        raise ValueError("path required")
    safe_path = path.strip().lstrip("/")
    target = pathlib.Path(_ROOT) / safe_path
    target = target.resolve()
    if not str(target).startswith(str(pathlib.Path(_ROOT).resolve())):
        raise ValueError("path escapes sandbox")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(path)
    return target.read_text("utf-8")
