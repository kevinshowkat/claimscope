import os
import time
import random
import json
import tempfile
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from datasets import load_dataset
import requests

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")
API_KEY = os.getenv("ANTHROPIC_API_KEY")
PRICE_IN = float(os.getenv("ANTHROPIC_PRICE_INPUT_PER_MTOK", "0"))
PRICE_OUT = float(os.getenv("ANTHROPIC_PRICE_OUTPUT_PER_MTOK", "0"))
API_URL = os.getenv("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")

SYSTEM_INSTRUCT = (
    "You are a careful coding assistant. Complete the Python function as requested. "
    "Rules: Output only valid Python code for the function body or edits; no explanations or markdown."
)

USER_TEMPLATE = (
    "Complete this function. Provide only Python code that continues the given prompt.\n\n"
    "<PROMPT>\n{prompt}\n</PROMPT>\n"
)


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # remove first fence
        t = t.split("\n", 1)[1] if "\n" in t else ""
        # remove language hint if present (e.g., python)
        if t.lower().startswith("python\n"):
            t = t.split("\n", 1)[1] if "\n" in t else ""
        # remove trailing fence
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _run_tests(solution_code: str, test_code: str, timeout_s: int = 15) -> bool:
    """Run HumanEval test code against the provided solution in an isolated subprocess.
    Returns True if tests pass with exit code 0, False otherwise.
    """
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "solution.py").write_text(solution_code, encoding="utf-8")
        runner = (
            "import sys, importlib.util, types\n"
            "spec = importlib.util.spec_from_file_location('solution', 'solution.py')\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "sys.modules['solution'] = mod\n"
            "spec.loader.exec_module(mod)\n"
            "code = open('tests.py','r',encoding='utf-8').read()\n"
            "g={'__name__':'__main__'}\n"
            "exec(compile(code, 'tests.py', 'exec'), g, g)\n"
        )
        (tdp / "tests.py").write_text(test_code, encoding="utf-8")
        (tdp / "run.py").write_text(runner, encoding="utf-8")
        try:
            proc = subprocess.run(["python", "run.py"], cwd=str(tdp), capture_output=True, text=True, timeout=timeout_s)
            return proc.returncode == 0
        except subprocess.TimeoutExpired:
            return False


def _load_humaneval_dataset():
    last_exc = None
    for name in ["openai_humaneval", "openai/humaneval", "nuprl/HumanEval"]:
        try:
            ds = load_dataset(name)
            return ds
        except Exception as e:
            last_exc = e
            continue
    raise RuntimeError(f"Failed to load HumanEval dataset: {last_exc}")


def run_humaneval_subset(n: int = 25, seed: int = 1234, temperature: float = 0.0, max_tokens: int = 1024) -> Tuple[Dict[str, Any], List[float]]:
    assert API_KEY, "ANTHROPIC_API_KEY not set"

    ds = _load_humaneval_dataset()
    # Prefer 'test' split if available, else first split
    split = ds["test"] if "test" in ds else list(ds.values())[0]

    idxs = list(range(len(split)))
    rng = random.Random(seed)
    rng.shuffle(idxs)
    idxs = idxs[:n]

    latencies: List[float] = []
    usage_in = 0
    usage_out = 0
    passes = 0

    for i in idxs:
        row = split[i]
        prompt = row.get("prompt") or ""
        test_code = row.get("test") or ""
        # Ask model for continuation
        t0 = time.time()
        # Build request
        headers = {
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": DEFAULT_MODEL,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": SYSTEM_INSTRUCT,
            "messages": [{"role": "user", "content": [{"type": "text", "text": USER_TEMPLATE.format(prompt=prompt)}]}],
        }
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        dt = time.time() - t0
        latencies.append(dt)
        data = resp.json()
        text = "".join([blk.get("text", "") for blk in data.get("content", []) if blk.get("type") == "text"])
        completion = _strip_code_fences(text)
        solution_code = f"{prompt}{completion}\n"
        ok = _run_tests(solution_code, test_code, timeout_s=20)
        if ok:
            passes += 1
        usage = data.get("usage", {})
        try:
            usage_in += int(usage.get("input_tokens", 0))
            usage_out += int(usage.get("output_tokens", 0))
        except Exception:
            pass

    acc = passes / len(idxs) if idxs else 0.0
    lat_sorted = sorted(latencies)
    p95 = lat_sorted[int(0.95 * (len(lat_sorted) - 1))] if latencies else 0.0

    cost = 0.0
    if PRICE_IN or PRICE_OUT:
        cost = (usage_in / 1_000_000.0) * PRICE_IN + (usage_out / 1_000_000.0) * PRICE_OUT

    return (
        {
            "score_value": acc,
            "n": len(idxs),
            "ops": {
                "p95_latency_s": round(p95, 3),
                "tokens_prompt": usage_in,
                "tokens_output": usage_out,
                "cost_usd": round(cost, 5),
            },
        },
        latencies,
    )