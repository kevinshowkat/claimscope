"""Available offline tools for the cAgent suite."""

from .calculator import run as calculator
from .sqlite import run as sqlite
from .wiki import run as wiki
from .calendar import run as calendar
from .fs import run as filesystem

TOOLS = {
    "calculator": calculator,
    "sqlite": sqlite,
    "wiki": wiki,
    "calendar": calendar,
    "fs": filesystem,
}

__all__ = ["TOOLS"]
