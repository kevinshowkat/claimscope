import os
import uuid
from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .schemas import (
    SubmitClaimRequest,
    SubmitClaimResponse,
    RunReproductionRequest,
    RunStatusResponse,
    Claim,
    ClaimWithRuns,
    RunSummary,
)
from .db import run_migrations, session

app = FastAPI(title="Claimscope API", version="0.1.0")

# Allow local dev UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _startup():
    # Run idempotent migrations
    run_migrations()

@app.post("/submit_claim", response_model=SubmitClaimResponse)
def submit_claim(body: SubmitClaimRequest):
    if not body.raw_text and not body.url:
        raise HTTPException(status_code=400, detail="Provide raw_text or url")

    # Simple keyword-based parsing for demo presets, allow multiple claims
    raw = (body.raw_text or "").lower()
    source_url = body.url

    candidates = []
    def add(domain: str, task: str, metric: str, ref: float | None, conf: float):
        candidates.append({
            "model": "Claude Sonnet 4.5",  # as provided in example text (label only)
            "domain": domain,
            "task": task,
            "metric": metric,
            "reference_score": ref,
            "confidence": conf,
        })

    if "humaneval" in raw or "coding" in raw or "best coding" in raw:
        add("coding", "HumanEval", "pass@1", 0.78, 0.85)
    if "cagent" in raw or "agents" in raw or "complex agents" in raw:
        add("agents", "cAgent-12", "success@1", 0.67, 0.8)
    if "cgui" in raw or "computers" in raw or "browser" in raw or "computer-use" in raw:
        add("computer-use", "cGUI-10", "task_success", 0.70, 0.8)
    if "gsm8k" in raw or "reasoning" in raw or "math" in raw:
        add("reasoning-math", "GSM8K", "accuracy", 0.94, 0.9)

    if not candidates:
        # default to a single reasoning-math claim
        add("reasoning-math", "GSM8K", "accuracy", 0.94, 0.6)

    out_ids: List[str] = []
    out_claims: List[Claim] = []

    import json as _json
    with session() as conn:
        for c in candidates:
            claim_id = f"clm_{uuid.uuid4().hex[:8]}"
            conn.execute(
                text(
                    """
                    INSERT INTO claims (id, model, domain, task, metric, settings, reference_score, source_url, confidence)
                    VALUES (:id, :model, :domain, :task, :metric, CAST(:settings AS JSONB), :reference_score, :source_url, :confidence)
                    """
                ),
                {
                    "id": claim_id,
                    "model": c["model"],
                    "domain": c["domain"],
                    "task": c["task"],
                    "metric": c["metric"],
                    "settings": _json.dumps({}),
                    "reference_score": c["reference_score"],
                    "source_url": source_url,
                    "confidence": c["confidence"],
                },
            )
            out_ids.append(claim_id)
            out_claims.append(Claim(id=claim_id, model=c["model"], domain=c["domain"], task=c["task"], metric=c["metric"], settings={}, reference_score=c["reference_score"], source_url=source_url, confidence=c["confidence"]))
        conn.commit()

    return SubmitClaimResponse(claim_ids=out_ids, claims=out_claims)

MIN_BUDGET_LLM = float(os.getenv("MIN_LLM_BUDGET_USD", "0.02"))


@app.post("/run_reproduction")
def run_reproduction(body: RunReproductionRequest):
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    with session() as conn:
        # basic existence check & fetch domain for budget enforcement
        claim_row = conn.execute(
            text("SELECT domain FROM claims WHERE id=:id"),
            {"id": body.claim_id},
        ).mappings().first()
        if not claim_row:
            raise HTTPException(status_code=404, detail="claim_id not found")

        domain = claim_row["domain"]
        if body.budget_usd < 0:
            raise HTTPException(status_code=400, detail="budget_usd must be non-negative")

        if domain in {"coding", "reasoning-math"} and body.budget_usd < MIN_BUDGET_LLM:
            raise HTTPException(
                status_code=400,
                detail=f"budget_usd below minimum {MIN_BUDGET_LLM:.2f} required for {domain}",
            )
        import json as _json
        model_cfg_payload = body.cfg.model_dump(mode="json")
        model_cfg_payload["budget_usd"] = round(body.budget_usd, 4)
        conn.execute(
            text(
                """
                INSERT INTO runs (id, claim_id, model_config, status)
                VALUES (:id, :claim_id, CAST(:model_config AS JSONB), :status)
                """
            ),
            {
                "id": run_id,
                "claim_id": body.claim_id,
                "model_config": _json.dumps(model_cfg_payload),
                "status": "queued",
            },
        )
        conn.commit()
    return {"run_id": run_id}

@app.get("/runs/{run_id}", response_model=RunStatusResponse)
def get_run(run_id: str):
    with session() as conn:
        row = conn.execute(text("SELECT * FROM runs WHERE id=:id"), {"id": run_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="run_id not found")
        arts = conn.execute(text("SELECT name, url, sha256 FROM artifacts WHERE run_id=:id ORDER BY created_at ASC"), {"id": run_id}).mappings().all()
        artifacts = [{"name": a["name"], "url": a["url"], "sha256": a.get("sha256")} for a in arts]
        return RunStatusResponse(
            run_id=row["id"],
            status=row["status"],
            scores=row.get("score_value") and {"metric": "unknown", "value": row["score_value"]} or None,
            ops=row.get("ops"),
            artifacts=artifacts,
            diffs=row.get("diffs"),
            ci=(None if row.get("ci_lower") is None else {"lower": row["ci_lower"], "upper": row["ci_upper"], "method": "bootstrap"}),
            variance=None,
            trace_id=row.get("trace_id"),
        )

@app.get("/claims/{claim_id}", response_model=ClaimWithRuns)
def get_claim(claim_id: str):
    with session() as conn:
        c = conn.execute(text("SELECT * FROM claims WHERE id=:id"), {"id": claim_id}).mappings().first()
        if not c:
            raise HTTPException(status_code=404, detail="claim_id not found")
        runs = conn.execute(
            text(
                "SELECT id, status, score_value, ci_lower, ci_upper, status_label, created_at FROM runs WHERE claim_id=:id ORDER BY created_at DESC"
            ),
            {"id": claim_id},
        ).mappings().all()
        return ClaimWithRuns(
            id=c["id"],
            model=c["model"],
            domain=c["domain"],
            task=c["task"],
            metric=c["metric"],
            settings=c["settings"],
            reference_score=c["reference_score"],
            source_url=c["source_url"],
            confidence=c["confidence"],
            created_at=str(c["created_at"]) if c.get("created_at") else None,
            runs=[
                RunSummary(
                    run_id=r["id"],
                    status=r["status"],
                    score_value=r["score_value"],
                    ci_lower=r["ci_lower"],
                    ci_upper=r["ci_upper"],
                    status_label=r["status_label"],
                    created_at=str(r["created_at"]) if r.get("created_at") else None,
                )
                for r in runs
            ],
        )
