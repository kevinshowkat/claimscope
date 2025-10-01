"""Shared logging helpers for worker processes."""

from __future__ import annotations

import logging
import os
from typing import Optional

_LOGGER_INITIALISED = False


def _initialise_root(level: str) -> None:
    global _LOGGER_INITIALISED
    if _LOGGER_INITIALISED:
        return
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    _LOGGER_INITIALISED = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    level = os.getenv("WORKER_LOG_LEVEL", "INFO").upper()
    _initialise_root(level)
    return logging.getLogger(name or "worker")
