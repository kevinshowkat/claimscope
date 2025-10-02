"""SWE-bench Verified harness assets.

This package intentionally ships only lightweight fixtures and metadata so the
worker can run deterministic smoke suites while heavier assets stream from
object storage in production deployments.
"""

from importlib import resources
from pathlib import Path
from typing import Iterable

FIXTURE_PACKAGE = "packages.harness.swebench.fixtures"


def load_fixture(name: str) -> str:
    """Return the text content of a fixture stored under ``fixtures/``."""
    with resources.files(FIXTURE_PACKAGE).joinpath(name).open("r", encoding="ascii") as handle:
        return handle.read()


def iter_fixture_paths() -> Iterable[Path]:
    """Yield paths for all fixtures included with the harness."""
    root = resources.files(FIXTURE_PACKAGE)
    for item in root.iterdir():
        if item.is_file():
            yield Path(item)
