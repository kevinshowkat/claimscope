from __future__ import annotations

from apps.api.worker.coding_competition import _extract_python_code, _run_tests


def test_run_tests_supports_script_blocks() -> None:
    task = {
        "id": "script-demo",
        "tests": [
            {"script": "assert demo() == 5"},
        ],
    }
    solution = "def demo():\n    return 5\n"
    result = _run_tests(task, solution)
    assert result.success is True


def test_extract_python_code_plain_source() -> None:
    src = "def foo():\n    return 42"
    assert _extract_python_code(src) == src


def test_extract_python_code_fenced_block() -> None:
    response = """Here you go:\n```python\n# file.py\nprint('hi')\n```"""
    assert _extract_python_code(response) == "# file.py\nprint('hi')"


def test_extract_python_code_handles_missing_code_block() -> None:
    response = "```\nprint('hi')\n```"
    assert _extract_python_code(response) == "print('hi')"
