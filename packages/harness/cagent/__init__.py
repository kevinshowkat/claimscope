"""Claimscope cAgent-12 harness utilities."""
from importlib.resources import files

DATA_PATH = files("packages.harness.cagent") / "data"
TASKS_PATH = files("packages.harness.cagent") / "tasks"
TOOLS_PATH = files("packages.harness.cagent") / "tools"

__all__ = ["DATA_PATH", "TASKS_PATH", "TOOLS_PATH"]
