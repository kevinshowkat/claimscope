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


def test_run_coding_competition_progress_callback() -> None:
    from apps.api.worker import coding_competition as cc

    primary = {"provider": "anthropic", "name": "primary"}
    comparator = {"provider": "anthropic", "name": "comp"}
    tasks = [{"id": "task", "prompt": "print('hi')", "tests": []}]

    original_call_model = cc._call_model
    original_run_tests = cc._run_tests

    def fake_call_model(config, prompt, temperature):
        return cc.ModelInvocation(
            model=config.get("name", "unknown"),
            provider=config.get("provider", "unknown"),
            response="def solution():\n    return 0\n",
            input_tokens=1,
            output_tokens=1,
            latency_s=0.01,
        )

    def fake_run_tests(task, response):
        return cc.TaskResult(task_id=task.get("id", "task"), success=True, test_latency_s=0.01)

    cc._call_model = fake_call_model
    cc._run_tests = fake_run_tests

    try:
        progress_events = []
        cc.run_coding_competition(
            tasks=tasks,
            primary_config=primary,
            comparator_configs=[comparator],
            temperature=0.0,
            progress_callback=lambda payload: progress_events.append(payload),
        )
    finally:
        cc._call_model = original_call_model
        cc._run_tests = original_run_tests

    assert progress_events, "expected progress updates"
    final = progress_events[-1]
    assert final.get("units_completed") == final.get("units_total")
    assert final.get("tasks_completed") == final.get("tasks_total")
