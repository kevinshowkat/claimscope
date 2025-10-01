import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import create_engine, text

from .agents_cagent import run_cagent_suite
from .coding_humaneval import run_humaneval_subset
from .gui_cgui import run_cgui_suite
from .logging_utils import get_logger
from .reasoning_gsm8k import bootstrap_ci, run_gsm8k_subset
from .trace_manifest import record_trace

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/claimscope")
engine = create_engine(DATABASE_URL, future=True)
logger = get_logger("worker")

REPO_ROOT = Path(__file__).resolve().parents[3]
HUMANEVAL_PATHS = [REPO_ROOT / "apps" / "api" / "worker" / "coding_humaneval.py"]
GSM8K_PATHS = [REPO_ROOT / "apps" / "api" / "worker" / "reasoning_gsm8k.py"]

ESTIMATED_LLM_COSTS: Dict[str, float] = {
    "coding": 0.02,
    "reasoning-math": 0.02,
}

SEED_RESULTS: Dict[str, Dict[str, Any]] = {
    "coding": {
        "score_value": 0.76,
        "ci_lower": 0.69,
        "ci_upper": 0.82,
        "ops": {"p95_latency_s": 2.4, "tokens_prompt": 14200, "tokens_output": 3000, "cost_usd": 0.018},
        "diffs": [{"dimension": "prompt_template", "ref": "tmpl_a", "obs": "tmpl_b"}],
        "status_label": "Setting Drift",
    },
    "agents": {
        "score_value": 0.64,
        "ci_lower": 0.46,
        "ci_upper": 0.79,
        "ops": {"p95_latency_s": 9.8, "cost_usd": 0.012, "tool_error_rate": 0.03},
        "diffs": [],
        "status_label": "Replicated",
    },
    "computer-use": {
        "score_value": 0.69,
        "ci_lower": 0.45,
        "ci_upper": 0.86,
        "ops": {"p95_latency_s": 17.2, "cost_usd": 0.006},
        "diffs": [],
        "status_label": "Replicated",
    },
    "reasoning-math": {
        "score_value": 0.91,
        "ci_lower": 0.88,
        "ci_upper": 0.94,
        "ops": {"p95_latency_s": 3.1, "cost_usd": 0.015},
        "diffs": [],
        "status_label": "Replicated",
    },
}

ARTIFACTS: Dict[str, Dict[str, Any]] = {
    "coding": {"name": "logs.txt", "url": "http://localhost:3000/demo/artifacts/logs.txt", "sha256": "demo", "bytes": 64, "content_type": "text/plain"},
    "agents": {"name": "agent_trace.json", "url": "http://localhost:3000/demo/artifacts/agent_trace.json", "sha256": "demo", "bytes": 128, "content_type": "application/json"},
    "computer-use": {"name": "playwright_trace.zip", "url": "http://localhost:3000/demo/artifacts/playwright_trace.zip", "sha256": "demo", "bytes": 256, "content_type": "application/zip"},
    "reasoning-math": {"name": "logs.txt", "url": "http://localhost:3000/demo/artifacts/logs.txt", "sha256": "demo", "bytes": 64, "content_type": "text/plain"},
}


def _status_from_exception(exc: Exception) -> Optional[int]:
    status = getattr(exc, "status_code", None)
    if status is not None:
        try:
            return int(status)
        except (TypeError, ValueError):
            return None
    response = getattr(exc, "response", None)
    if response is not None:
        return getattr(response, "status_code", None)
    return None


def _record_failure(
    conn,
    run_id: str,
    trace_id: str,
    *,
    reason: str,
    message: str,
    extra: Optional[Dict[str, Any]] = None,
    status_label: str = "Failed",
) -> None:
    payload = {"reason": reason, "message": message}
    if extra:
        payload.update(extra)
    conn.execute(
        text(
            "UPDATE runs SET status='failed', trace_id=:trace_id, diffs=CAST(:diffs AS JSONB), status_label=:label WHERE id=:id"
        ),
        {
            "id": run_id,
            "trace_id": trace_id,
            "label": status_label,
            "diffs": json.dumps([payload]),
        },
    )
    conn.commit()

def _coerce_budget(model_cfg: Dict[str, Any]) -> float:
    raw = model_cfg.get("budget_usd", 0.0)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _load_run_context(conn, run_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        text(
            """
            SELECT c.domain, c.task, r.model_config
            FROM runs r
            JOIN claims c ON c.id = r.claim_id
            WHERE r.id = :run_id
            """
        ),
        {"run_id": run_id},
    ).mappings().first()
    if not row:
        return None

    model_cfg = row["model_config"]
    if isinstance(model_cfg, str):
        try:
            model_cfg = json.loads(model_cfg)
        except json.JSONDecodeError:
            model_cfg = {}
    return {"domain": row["domain"], "task": row["task"], "model_config": model_cfg or {}}


def process_one(run_id: str, claim_id: str) -> None:
    with engine.connect() as conn:
        ctx = _load_run_context(conn, run_id)
        if ctx is None:
            logger.error("run %s missing context; marking failed", run_id)
            conn.execute(text("UPDATE runs SET status='failed' WHERE id=:id"), {"id": run_id})
            conn.commit()
            return

        domain = ctx["domain"] or "coding"
        task = ctx["task"] or ""
        model_cfg = ctx["model_config"]
        budget = _coerce_budget(model_cfg)
        trace_id = f"tr_{uuid.uuid4().hex[:6]}"

        def _guard_cost(expected_cost: float) -> bool:
            if expected_cost <= 0:
                return True
            if budget <= 0:
                logger.warning(
                    "run %s requires >= %.4f budget but none provided; marking failed",
                    run_id,
                    expected_cost,
                )
                conn.execute(
                    text(
                        "UPDATE runs SET status='failed', trace_id=:trace_id, diffs=CAST(:diffs AS JSONB) WHERE id=:id"
                    ),
                    {
                        "id": run_id,
                        "trace_id": trace_id,
                        "diffs": json.dumps([{"reason": "missing_budget", "required_usd": expected_cost}]),
                    },
                )
                conn.commit()
                return False
            if expected_cost <= budget:
                return True
            logger.warning(
                "run %s exceeds budget (expected %.4f > budget %.4f); marking failed",
                run_id,
                expected_cost,
                budget,
            )
            conn.execute(
                text(
                    "UPDATE runs SET status='failed', trace_id=:trace_id, diffs=CAST(:diffs AS JSONB) WHERE id=:id"
                ),
                {
                    "id": run_id,
                    "trace_id": trace_id,
                    "diffs": json.dumps([{"reason": "budget_exceeded", "expected_cost_usd": expected_cost}]),
                },
            )
            conn.commit()
            return False

        # Real GSM8K path
        if domain == "reasoning-math" and task.lower().startswith("gsm8k"):
            if not _guard_cost(ESTIMATED_LLM_COSTS.get(domain, 0.0)):
                return
            try:
                res, lats = run_gsm8k_subset(n=25, seed=1234, temperature=0.2)
                acc = res["score_value"]
                # Build binary list for bootstrap
                n = res.get("n", 25)
                # Approximate successes from accuracy
                k = int(round(acc * n))
                vals = [1]*k + [0]*(n-k)
                lo, hi = bootstrap_ci(vals, n=n, reps=1000, seed=1234)
                conn.execute(
                    text(
                        """
                        UPDATE runs SET status=:status, score_value=:score_value, ci_lower=:ci_lower, ci_upper=:ci_upper,
                          ops=CAST(:ops AS JSONB), diffs=CAST(:diffs AS JSONB), status_label=:status_label,
                          trace_id=:trace_id, completed_at=now()
                        WHERE id=:id
                        """
                    ),
                    {
                        "id": run_id,
                        "status": "succeeded",
                        "score_value": acc,
                        "ci_lower": lo,
                        "ci_upper": hi,
                        "ops": json.dumps(res["ops"]),
                        "diffs": json.dumps([]),
                        "status_label": "Replicated",
                        "trace_id": trace_id,
                    },
                )
                record_trace(
                    conn,
                    run_id,
                    harness_cmd="python -m worker.reasoning_gsm8k",
                    harness_paths=GSM8K_PATHS,
                    dataset_id="gsm8k@subset-25",
                    params={"n": n, "temperature": 0.2, "budget_usd": budget},
                    seeds={"sample_seed": 1234},
                    tokens_prompt=int(res["ops"].get("tokens_prompt") or 0),
                    tokens_output=int(res["ops"].get("tokens_output") or 0),
                    latencies=lats,
                    cost_usd=float(res["ops"].get("cost_usd", 0.0)),
                )
                conn.commit()
                return
            except Exception as e:
                logger.exception("GSM8K runner error for %s", run_id)
                status = _status_from_exception(e)
                reason = "anthropic_overloaded" if status == 529 else "anthropic_error"
                extra = {"status_code": status} if status else {}
                _record_failure(
                    conn,
                    run_id,
                    trace_id,
                    reason=reason,
                    message=str(e),
                    extra=extra if extra else None,
                    status_label="Failed",
                )
                return

        # Real HumanEval (coding)
        if domain == "coding" and task.lower().startswith("humaneval"):
            if not _guard_cost(ESTIMATED_LLM_COSTS.get(domain, 0.0)):
                return
            try:
                res, lats = run_humaneval_subset(n=25, seed=1234, temperature=0.0, max_tokens=1024)
                acc = res["score_value"]
                n = res.get("n", 25)
                k = int(round(acc * n))
                vals = [1]*k + [0]*(n-k)
                lo, hi = bootstrap_ci(vals, n=n, reps=1000, seed=1234)
                conn.execute(
                    text(
                        """
                        UPDATE runs SET status=:status, score_value=:score_value, ci_lower=:ci_lower, ci_upper=:ci_upper,
                          ops=CAST(:ops AS JSONB), diffs=CAST(:diffs AS JSONB), status_label=:status_label,
                          trace_id=:trace_id, completed_at=now()
                        WHERE id=:id
                        """
                    ),
                    {
                        "id": run_id,
                        "status": "succeeded",
                        "score_value": acc,
                        "ci_lower": lo,
                        "ci_upper": hi,
                        "ops": json.dumps(res["ops"]),
                        "diffs": json.dumps([]),
                        "status_label": "Replicated",
                        "trace_id": trace_id,
                    },
                )
                record_trace(
                    conn,
                    run_id,
                    harness_cmd="python -m worker.coding_humaneval",
                    harness_paths=HUMANEVAL_PATHS,
                    dataset_id="openai/humaneval",
                    params={"n": n, "temperature": 0.0, "max_tokens": 1024, "budget_usd": budget},
                    seeds={"sample_seed": 1234},
                    tokens_prompt=int(res["ops"].get("tokens_prompt") or 0),
                    tokens_output=int(res["ops"].get("tokens_output") or 0),
                    latencies=lats,
                    cost_usd=float(res["ops"].get("cost_usd", 0.0)),
                )
                conn.commit()
                return
            except Exception as e:
                logger.exception("HumanEval runner error for %s", run_id)
                status = _status_from_exception(e)
                reason = "anthropic_overloaded" if status == 529 else "anthropic_error"
                extra = {"status_code": status} if status else {}
                _record_failure(
                    conn,
                    run_id,
                    trace_id,
                    reason=reason,
                    message=str(e),
                    extra=extra if extra else None,
                    status_label="Failed",
                )
                return

        if domain == "agents" and task.lower().startswith("cagent"):
            try:
                res, durations, artifact, metadata = run_cagent_suite()
                conn.execute(
                    text(
                        """
                        UPDATE runs
                        SET status=:status,
                            score_value=:score_value,
                            ops=CAST(:ops AS JSONB),
                            diffs=CAST(:diffs AS JSONB),
                            status_label=:status_label,
                            trace_id=:trace_id,
                            completed_at=now()
                        WHERE id=:id
                        """
                    ),
                    {
                        "id": run_id,
                        "status": "succeeded",
                        "score_value": res["score_value"],
                        "ops": json.dumps(res["ops"]),
                        "diffs": json.dumps([{"metrics": res["metrics"]}]),
                        "status_label": "Replicated",
                        "trace_id": trace_id,
                    },
                )
                if artifact:
                    conn.execute(
                        text(
                            """
                            INSERT INTO artifacts (id, run_id, name, url, sha256, bytes, content_type)
                            VALUES (:id, :run_id, :name, :url, :sha256, :bytes, :content_type)
                            """
                        ),
                        {
                            "id": f"art_{uuid.uuid4().hex[:8]}",
                            "run_id": run_id,
                            "name": artifact["name"],
                            "url": artifact["data_url"],
                            "sha256": artifact.get("sha256"),
                            "bytes": artifact.get("bytes"),
                            "content_type": artifact.get("content_type"),
                        },
                    )
                record_trace(
                    conn,
                    run_id,
                    harness_cmd="python -m worker.agents_cagent",
                    harness_digest=metadata.get("harness_hash"),
                    dataset_id=metadata.get("dataset_id"),
                    dataset_digest=metadata.get("dataset_hash"),
                    params={**metadata.get("params", {}), "budget_usd": budget},
                    seeds=metadata.get("seeds"),
                    tokens_prompt=0,
                    tokens_output=0,
                    latencies=[d / 1000.0 for d in durations],
                    cost_usd=0.0,
                )
                conn.commit()
                return
            except Exception as exc:
                logger.exception("cAgent suite error for %s", run_id)
                _record_failure(
                    conn,
                    run_id,
                    trace_id,
                    reason="harness_error",
                    message=str(exc),
                )
                return

        if domain == "computer-use" and task.lower().startswith("cgui"):
            try:
                res, durations, artifact, metadata = run_cgui_suite()
                conn.execute(
                    text(
                        """
                        UPDATE runs
                        SET status=:status,
                            score_value=:score_value,
                            ops=CAST(:ops AS JSONB),
                            diffs=CAST(:diffs AS JSONB),
                            status_label=:status_label,
                            trace_id=:trace_id,
                            completed_at=now()
                        WHERE id=:id
                        """
                    ),
                    {
                        "id": run_id,
                        "status": "succeeded",
                        "score_value": res["score_value"],
                        "ops": json.dumps(res["ops"]),
                        "diffs": json.dumps([{"metrics": res["metrics"]}]),
                        "status_label": "Replicated",
                        "trace_id": trace_id,
                    },
                )
                if artifact:
                    conn.execute(
                        text(
                            """
                            INSERT INTO artifacts (id, run_id, name, url, sha256, bytes, content_type)
                            VALUES (:id, :run_id, :name, :url, :sha256, :bytes, :content_type)
                            """
                        ),
                        {
                            "id": f"art_{uuid.uuid4().hex[:8]}",
                            "run_id": run_id,
                            "name": artifact["name"],
                            "url": artifact["data_url"],
                            "sha256": artifact.get("sha256"),
                            "bytes": artifact.get("bytes"),
                            "content_type": artifact.get("content_type"),
                        },
                    )
                record_trace(
                    conn,
                    run_id,
                    harness_cmd="python -m worker.gui_cgui",
                    harness_digest=metadata.get("harness_hash"),
                    dataset_id=metadata.get("dataset_id"),
                    dataset_digest=metadata.get("dataset_hash"),
                    params={**metadata.get("params", {}), "budget_usd": budget},
                    seeds=metadata.get("seeds"),
                    tokens_prompt=0,
                    tokens_output=0,
                    latencies=durations,
                    cost_usd=0.0,
                )
                conn.commit()
                return
            except Exception as exc:
                logger.exception("cGUI suite error for %s", run_id)
                _record_failure(
                    conn,
                    run_id,
                    trace_id,
                    reason="harness_error",
                    message=str(exc),
                )
                return

        # Fallback to seeded paths for other domains
        seed = SEED_RESULTS.get(domain, SEED_RESULTS["coding"])
        conn.execute(
            text(
                """
                UPDATE runs SET status=:status, score_value=:score_value, ci_lower=:ci_lower, ci_upper=:ci_upper,
                  ops=CAST(:ops AS JSONB), diffs=CAST(:diffs AS JSONB), status_label=:status_label,
                  trace_id=:trace_id, completed_at=now()
                WHERE id=:id
                """
            ),
            {
                "id": run_id,
                "status": "succeeded",
                "score_value": seed["score_value"],
                "ci_lower": seed["ci_lower"],
                "ci_upper": seed["ci_upper"],
                "ops": json.dumps(seed["ops"]),
                "diffs": json.dumps(seed["diffs"]),
                "status_label": seed["status_label"],
                "trace_id": trace_id,
            },
        )
        # add one artifact
        art = ARTIFACTS.get(domain, ARTIFACTS["coding"])
        conn.execute(
            text(
                """
                INSERT INTO artifacts (id, run_id, name, url, sha256, bytes, content_type)
                VALUES (:id, :run_id, :name, :url, :sha256, :bytes, :content_type)
                """
            ),
            {
                "id": f"art_{uuid.uuid4().hex[:8]}",
                "run_id": run_id,
                "name": art["name"],
                "url": art["url"],
                "sha256": art["sha256"],
                "bytes": art["bytes"],
                "content_type": art["content_type"],
            },
        )
        record_trace(
            conn,
            run_id,
            harness_cmd=f"seeded::{domain}",
            dataset_id=f"seeded::{domain}",
            params={"domain": domain, "task": task, "budget_usd": budget},
            seeds={"mode": "seeded"},
            tokens_prompt=int(seed["ops"].get("tokens_prompt") or 0),
            tokens_output=int(seed["ops"].get("tokens_output") or 0),
            cost_usd=float(seed["ops"].get("cost_usd") or 0.0),
        )
        conn.commit()


def main() -> None:
    logger.info("worker starting")
    while True:
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT id, claim_id FROM runs WHERE status='queued' ORDER BY created_at ASC LIMIT 1")
                ).mappings().first()
                if row:
                    logger.info("picked run %s for claim %s", row['id'], row['claim_id'])
                    # Mark running
                    conn.execute(text("UPDATE runs SET status='running' WHERE id=:id"), {"id": row["id"]})
                    conn.commit()
                    time.sleep(0.2)
                    process_one(run_id=row["id"], claim_id=row["claim_id"])
                    logger.info("finished run %s", row['id'])
                else:
                    time.sleep(0.5)
        except Exception as e:
            logger.exception("worker loop error")
            time.sleep(1.0)

if __name__ == "__main__":
    main()
