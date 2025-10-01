"""Read-only SQLite tool bound to the bundled dataset."""

from __future__ import annotations

import os
import sqlite3
from importlib.resources import files
from typing import Any, Iterable, List

DB_PATH = files("packages.harness.cagent.data").joinpath("sample.db")


class SQLiteToolError(RuntimeError):
    pass


def _ensure_allowed(query: str) -> None:
    stripped = query.strip().lower()
    if not stripped.startswith("select"):
        raise SQLiteToolError("only SELECT queries are permitted")
    disallowed = {"update", "insert", "delete", "drop", "alter", "pragma"}
    if any(word in stripped for word in disallowed):
        raise SQLiteToolError("mutation queries are not allowed")


def run(query: str) -> str:
    if not os.path.exists(DB_PATH):
        raise SQLiteToolError("database not found")
    _ensure_allowed(query)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query)
        rows = cur.fetchall()
        if not rows:
            return "[]"
        result: List[dict[str, Any]] = [dict(row) for row in rows]
        return str(result)
    finally:
        conn.close()
