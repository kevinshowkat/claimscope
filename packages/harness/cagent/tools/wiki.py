"""Offline wiki lookup tool backed by bundled JSON."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Dict

_CACHE: Dict[str, dict] | None = None


def _load() -> Dict[str, dict]:
    global _CACHE
    if _CACHE is None:
        data_path = files("packages.harness.cagent.data").joinpath("wiki.json")
        with data_path.open("r", encoding="utf-8") as fh:
            entries = json.load(fh)
        _CACHE = {entry["title"].lower(): entry for entry in entries}
    return _CACHE


def run(query: str) -> str:
    if not query:
        raise ValueError("query required")
    entries = _load()
    key = query.lower()
    if key not in entries:
        raise KeyError(f"wiki entry not found: {query}")
    entry = entries[key]
    section = entry.get("sections", {}).get("summary")
    if not section:
        return entry.get("content", "")
    return section
