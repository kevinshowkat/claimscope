"""Simple calendar parser returning ISO dates."""

from __future__ import annotations

from datetime import datetime
from dateutil import parser


def run(phrase: str) -> str:
    if not phrase:
        raise ValueError("phrase required")
    dt = parser.parse(phrase, dayfirst=False, yearfirst=False, fuzzy=True)
    return dt.date().isoformat()
