import os
import time
import random
import json
from typing import Any, Dict, List, Tuple
from datasets import load_dataset
import anthropic
from anthropic import Anthropic

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")
API_KEY = os.getenv("ANTHROPIC_API_KEY")
PRICE_IN = float(os.getenv("ANTHROPIC_PRICE_INPUT_PER_MTOK", "0"))
PRICE_OUT = float(os.getenv("ANTHROPIC_PRICE_OUTPUT_PER_MTOK", "0"))
RETRIABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 521, 522, 523, 524, 525, 526, 527, 529}
MAX_RETRIES = max(1, int(os.getenv("ANTHROPIC_MAX_RETRIES", "5")))
BACKOFF_BASE_SECONDS = max(0.1, float(os.getenv("ANTHROPIC_BACKOFF_BASE", "1.0")))

PROMPT_TEMPLATE = (
    "You are a careful mathematician. Solve the following problem. "
    "Return only the final numeric answer.\n\nProblem: {question}\nAnswer:"
)


def extract_numeric(s: str) -> str:
    # Grab last number-like token
    import re
    matches = re.findall(r"-?\d+(?:\.\d+)?", s)
    return matches[-1] if matches else s.strip()


def run_gsm8k_subset(n: int = 25, seed: int = 1234, temperature: float = 0.2, shots: int = 0) -> Tuple[Dict[str, Any], List[float]]:
    assert API_KEY, "ANTHROPIC_API_KEY not set"
    client = Anthropic(api_key=API_KEY)

    ds = load_dataset("openai/gsm8k", "main")
    test = ds["test"]
    rng = random.Random(seed)
    idxs = list(range(len(test)))
    rng.shuffle(idxs)
    idxs = idxs[:n]

    latencies: List[float] = []
    correct = 0
    usage_in = 0
    usage_out = 0

    for i in idxs:
        q = test[i]["question"]
        gold = test[i]["answer"]
        prompt = PROMPT_TEMPLATE.format(question=q)
        t0 = time.time()
        msg = None
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                msg = client.messages.create(
                    model=DEFAULT_MODEL,
                    max_tokens=512,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}],
                )
                last_exc = None
                break
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                if status is None and hasattr(exc, "response"):
                    status = getattr(getattr(exc, "response"), "status_code", None)
                retriable_candidates = [
                    getattr(anthropic, "RateLimitError", None),
                    getattr(anthropic, "APIConnectionError", None),
                    getattr(anthropic, "ServiceUnavailableError", None),
                    getattr(anthropic, "InternalServerError", None),
                    getattr(anthropic, "OverloadedError", None),
                ]
                retriable_types = tuple(t for t in retriable_candidates if isinstance(t, type)) or tuple()
                retriable = status in RETRIABLE_STATUS or isinstance(exc, retriable_types)
                last_exc = exc
                if retriable and attempt < MAX_RETRIES - 1:
                    delay = BACKOFF_BASE_SECONDS * (2 ** attempt) + rng.random() * 0.5
                    time.sleep(delay)
                    continue
                raise

        if msg is None:
            raise RuntimeError("Anthropic call failed without response") from last_exc

        dt = time.time() - t0
        latencies.append(dt)
        text = "".join([blk.text for blk in msg.content if getattr(blk, "type", "text") == "text"]) if hasattr(msg, "content") else str(msg)
        pred = extract_numeric(text)
        gold_num = extract_numeric(gold)
        if pred == gold_num:
            correct += 1
        # usage
        try:
            usage_in += int(msg.usage.input_tokens)
            usage_out += int(msg.usage.output_tokens)
        except Exception:
            pass

    acc = correct / n if n else 0.0
    lat_sorted = sorted(latencies)
    p95 = lat_sorted[int(0.95 * (len(lat_sorted) - 1))] if latencies else 0.0

    cost = 0.0
    if PRICE_IN or PRICE_OUT:
        cost = (usage_in / 1_000_000.0) * PRICE_IN + (usage_out / 1_000_000.0) * PRICE_OUT

    return (
        {
            "score_value": acc,
            "n": n,
            "ops": {
                "p95_latency_s": round(p95, 3),
                "tokens_prompt": usage_in,
                "tokens_output": usage_out,
                "cost_usd": round(cost, 5),
            },
        },
        latencies,
    )


def bootstrap_ci(values: List[int], n: int, reps: int = 1000, seed: int = 1234) -> Tuple[float, float]:
    # values are 0/1 correctness
    import random as _r
    _r.seed(seed)
    means: List[float] = []
    for _ in range(reps):
        sample = [_r.choice(values) for __ in range(n)]
        means.append(sum(sample) / float(n))
    means.sort()
    lo = means[int(0.025 * reps)]
    hi = means[int(0.975 * reps)]
    return lo, hi
