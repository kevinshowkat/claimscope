from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict

Status = Literal["Replicated", "Setting Drift", "Underspecified", "Not Reproduced"]

class Settings(BaseModel):
    prompt_template: Optional[str] = None
    shots: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    k: Optional[int] = None
    seed: Optional[int] = None
    tools: Optional[List[str]] = None
    timeout_s: Optional[int] = None
    cot: Optional[bool] = None
    environment_sha: Optional[str] = None
    dataset_variant: Optional[str] = None

class Claim(BaseModel):
    id: str
    model: str
    domain: str
    task: str
    metric: str
    settings: Dict[str, Any]
    reference_score: Optional[float] = None
    source_url: Optional[str] = None
    confidence: float
    created_at: Optional[str] = None

class ModelConfig(BaseModel):
    provider: Literal["openai","anthropic","openrouter","vllm"]
    name: str
    api_key_ref: str

class SubmitClaimRequest(BaseModel):
    raw_text: Optional[str] = None
    url: Optional[str] = None

class SubmitClaimResponse(BaseModel):
    claim_ids: List[str]
    claims: List[Claim]

class RunReproductionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=("model_",))

    claim_id: str
    cfg: ModelConfig = Field(alias="model_config")
    budget_usd: float

class Artifact(BaseModel):
    name: str
    url: str
    sha256: Optional[str] = None

class RunStatusResponse(BaseModel):
    run_id: str
    status: Literal["queued","running","succeeded","failed"]
    scores: Optional[Dict[str, Any]] = None
    ops: Optional[Dict[str, Any]] = None
    artifacts: Optional[List[Artifact]] = None
    diffs: Optional[List[Dict[str, Any]]] = None
    ci: Optional[Dict[str, Any]] = None
    variance: Optional[Dict[str, Any]] = None
    trace_id: Optional[str] = None

class RunSummary(BaseModel):
    run_id: str
    status: Literal["queued","running","succeeded","failed"]
    score_value: Optional[float] = None
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None
    status_label: Optional[Status] = None
    created_at: Optional[str] = None

class ClaimWithRuns(Claim):
    runs: List[RunSummary] = Field(default_factory=list)
