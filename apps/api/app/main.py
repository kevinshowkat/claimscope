import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
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

COMPARATIVE_MARKERS = (
    "best",
    "better than",
    "state of the art",
    "state-of-the-art",
    "beats",
    "beat",
    "outperforms",
    "outperform",
    "top",
    "leading",
    "vs",
    "versus",
    "compared to",
)

VISION_MARKERS = (
    "vision",
    "image",
    "multimodal",
    "multi-modal",
    "mmmu",
    "mmbench",
    "perception",
)


_HYPHEN_NORMALIZE_RE = re.compile(r"[‐‑‒–—−]")


def _normalize_hyphen_variants(text: str) -> str:
    return _HYPHEN_NORMALIZE_RE.sub("-", text)


def _normalize_model_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


MODEL_NAME_PATTERNS = [
    r"claude opus\s*[0-9.]*",
    r"claude sonnet\s*[0-9.]*",
    r"claude haiku\s*[0-9.]*",
    r"claude\s*[0-9.]*",
    r"gpt-[0-9a-zA-Z.\-]+",
    r"gemini\s*[0-9.]*\s*(?:pro|flash|ultra)?",
    r"llama\s*[0-9.]*\s*(?:vision)?\s*(?:[0-9]{1,2}b|[0-9]{1,2}\.?[0-9]*b)?",
]


_GPT_SUFFIXES = [
    "thinking",
    "mini",
    "thinking mini",
    "nano",
    "thinking nano",
]


def _extract_model_mentions(text: str) -> List[str]:
    normalized = _normalize_hyphen_variants(text)
    hits: Dict[str, Tuple[int, str]] = {}
    for pattern in MODEL_NAME_PATTERNS:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            value = re.sub(r"\s+", " ", match.group(0).strip())
            if not value:
                continue
            if value.lower().startswith("gpt-"):
                suffix_space = normalized[match.end():]
                for suffix in _GPT_SUFFIXES:
                    if suffix_space.lower().startswith(f" {suffix}"):
                        value = f"{value} {suffix}".strip()
                        break
            norm = _normalize_model_name(value)
            start = match.start()
            existing = hits.get(norm)
            if existing is None or start < existing[0]:
                hits[norm] = (start, value)
    ordered = sorted(hits.values(), key=lambda item: item[0])
    return [value for _, value in ordered]


_MODEL_REGISTRY: List[Dict[str, Any]] = [
    {
        "display": "GPT-4o",
        "provider": "openai",
        "model": os.getenv("CLAIMSCOPE_MODEL_GPT4O", "gpt-4o"),
        "env": "OPENAI_API_KEY",
        "aliases": ["gpt-4o", "gpt 4o", "gpt4o"],
        "variants": ["gpt-4o"],
        "default_compare": True,
    },
    {
        "display": "GPT-4o mini",
        "provider": "openai",
        "model": os.getenv("CLAIMSCOPE_MODEL_GPT4O_MINI", "gpt-4o-mini"),
        "env": "OPENAI_API_KEY",
        "aliases": ["gpt-4o mini", "gpt 4o mini", "gpt4o mini"],
        "variants": ["gpt-4o-mini"],
    },
    {
        "display": "GPT-5",
        "provider": "openai",
        "model": os.getenv("CLAIMSCOPE_MODEL_GPT5", "gpt-5"),
        "env": "OPENAI_API_KEY",
        "aliases": [
            "gpt-5",
            "gpt 5",
            "gpt-5-thinking",
            "gpt 5 thinking",
        ],
        "variants": ["gpt-5", "gpt-5-thinking", "gpt-5-chat-latest"],
        "default_compare": True,
    },
    {
        "display": "GPT-5 thinking",
        "provider": "openai",
        "model": os.getenv("CLAIMSCOPE_MODEL_GPT5_THINKING", "gpt-5-thinking"),
        "env": "OPENAI_API_KEY",
        "aliases": [
            "gpt-5 thinking",
            "gpt 5 thinking",
            "gpt-5-thinking",
        ],
        "variants": ["gpt-5-thinking", "gpt-5-thinking-latest"],
        "default_compare": True,
    },
    {
        "display": "GPT-5 mini",
        "provider": "openai",
        "model": os.getenv("CLAIMSCOPE_MODEL_GPT5_MINI", "gpt-5-mini"),
        "env": "OPENAI_API_KEY",
        "aliases": [
            "gpt-5 mini",
            "gpt 5 mini",
            "gpt-5-thinking-mini",
            "gpt 5 thinking mini",
        ],
        "variants": ["gpt-5-mini", "gpt-5-thinking-mini"],
        "default_compare": True,
    },
    {
        "display": "GPT-5 nano",
        "provider": "openai",
        "model": os.getenv("CLAIMSCOPE_MODEL_GPT5_NANO", "gpt-5-nano"),
        "env": "OPENAI_API_KEY",
        "aliases": [
            "gpt-5 nano",
            "gpt 5 nano",
            "gpt-5-thinking-nano",
            "gpt 5 thinking nano",
        ],
        "variants": ["gpt-5-nano", "gpt-5-thinking-nano"],
    },
    {
        "display": "Gemini 1.5 Pro",
        "provider": "gemini",
        "model": os.getenv("CLAIMSCOPE_MODEL_GEMINI_PRO", "gemini-1.5-pro"),
        "env": "GOOGLE_GEMINI_API_KEY",
        "aliases": ["gemini 1.5 pro", "gemini pro", "gemini 1.5"],
        "variants": ["gemini-1.5-pro", "gemini-2.5-pro"],
    },
    {
        "display": "Claude Sonnet 4.5",
        "provider": "anthropic",
        "model": os.getenv("CLAIMSCOPE_MODEL_CLAUDE_SONNET45", "claude-sonnet-4-5-20250929"),
        "env": "ANTHROPIC_API_KEY",
        "aliases": ["claude sonnet 4.5", "sonnet 4.5"],
        "variants": ["claude-sonnet-4-5-20250929", "claude-sonnet-4-5-latest"],
        "default_compare": True,
    },
    {
        "display": "Claude Sonnet 4",
        "provider": "anthropic",
        "model": os.getenv("CLAIMSCOPE_MODEL_CLAUDE_SONNET4", "claude-sonnet-4-20250514"),
        "env": "ANTHROPIC_API_KEY",
        "aliases": ["claude sonnet 4", "sonnet 4", "claude sonnet"],
        "variants": ["claude-sonnet-4-20250514", "claude-sonnet-4-latest"],
    },
    {
        "display": "Claude Sonnet 3.7",
        "provider": "anthropic",
        "model": os.getenv("CLAIMSCOPE_MODEL_CLAUDE_SONNET37", "claude-3-7-sonnet-20250219"),
        "env": "ANTHROPIC_API_KEY",
        "aliases": ["claude sonnet 3.7", "sonnet 3.7"],
        "variants": ["claude-3-7-sonnet-20250219", "claude-3-7-sonnet-latest"],
    },
    {
        "display": "Claude Opus 4",
        "provider": "anthropic",
        "model": os.getenv("CLAIMSCOPE_MODEL_CLAUDE_OPUS4", "claude-opus-4-20250514"),
        "env": "ANTHROPIC_API_KEY",
        "aliases": ["claude opus 4", "opus 4", "claude opus"],
        "variants": ["claude-opus-4-20250514", "claude-opus-4-latest"],
    },
    {
        "display": "Claude Opus 4.1",
        "provider": "anthropic",
        "model": os.getenv("CLAIMSCOPE_MODEL_CLAUDE_OPUS41", "claude-opus-4-1-20250805"),
        "env": "ANTHROPIC_API_KEY",
        "aliases": ["claude opus 4.1", "opus 4.1"],
        "variants": ["claude-opus-4-1-20250805"],
    },
    {
        "display": "Claude Haiku 3.5",
        "provider": "anthropic",
        "model": os.getenv("CLAIMSCOPE_MODEL_CLAUDE_HAIKU35", "claude-3-5-haiku-20241022"),
        "env": "ANTHROPIC_API_KEY",
        "aliases": ["claude haiku 3.5", "haiku 3.5", "claude haiku"],
        "variants": ["claude-3-5-haiku-20241022", "claude-3-5-haiku-latest"],
    },
]

_PROVIDER_MODEL_CACHE: Dict[str, Set[str]] = {}
_PROVIDER_MODEL_CACHE_TS: Dict[str, float] = {}
_PROVIDER_CACHE_TTL_S = 300.0


def _provider_discovery_enabled() -> bool:
    value = os.getenv("CLAIMSCOPE_ENABLE_PROVIDER_DISCOVERY", "")
    return value.lower() in {"1", "true", "yes"}

_MODEL_ALIAS_LOOKUP: Dict[str, Dict[str, Any]] = {}
for entry in _MODEL_REGISTRY:
    aliases = entry.get("aliases") or []
    aliases.append(entry["display"])
    normalized_aliases = {_normalize_model_name(alias) for alias in aliases}
    entry["_aliases"] = normalized_aliases
    for alias in normalized_aliases:
        _MODEL_ALIAS_LOOKUP[alias] = entry


def _lookup_model_entry(name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    return _MODEL_ALIAS_LOOKUP.get(_normalize_model_name(name))


def _fetch_provider_models(provider: str) -> Optional[Set[str]]:
    try:
        if provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                return None
            resp = requests.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                timeout=5,
            )
            if resp.status_code != 200:
                return None
            payload = resp.json()
            data = payload.get("data") or payload.get("models") or []
            return {
                item.get("id") or item.get("name")
                for item in data
                if isinstance(item, dict) and (item.get("id") or item.get("name"))
            }
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return None
            resp = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5,
            )
            if resp.status_code != 200:
                return None
            payload = resp.json()
            data = payload.get("data") or []
            return {
                item.get("id")
                for item in data
                if isinstance(item, dict) and item.get("id")
            }
        if provider == "gemini":
            api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
            if not api_key:
                return None
            resp = requests.get(
                "https://generativelanguage.googleapis.com/v1/models",
                params={"key": api_key},
                timeout=5,
            )
            if resp.status_code != 200:
                return None
            payload = resp.json()
            data = payload.get("models") or []
            return {
                item.get("name") or item.get("displayName")
                for item in data
                if isinstance(item, dict) and (item.get("name") or item.get("displayName"))
            }
    except requests.RequestException:
        return None
    return None


def _get_provider_models(provider: str) -> Optional[Set[str]]:
    if not _provider_discovery_enabled():
        return None
    if not provider:
        return None
    now = time.time()
    cached = _PROVIDER_MODEL_CACHE.get(provider)
    ts = _PROVIDER_MODEL_CACHE_TS.get(provider, 0.0)
    if cached is not None and now - ts < _PROVIDER_CACHE_TTL_S:
        return cached
    models = _fetch_provider_models(provider)
    if models:
        _PROVIDER_MODEL_CACHE[provider] = models
        _PROVIDER_MODEL_CACHE_TS[provider] = now
        return models
    _PROVIDER_MODEL_CACHE_TS[provider] = now
    return cached


def _pick_model_identifier(entry: Dict[str, Any]) -> Optional[str]:
    provider = entry.get("provider")
    configured = entry.get("model")
    variants = entry.get("variants") or []
    candidates: List[str] = []
    for candidate in [configured, *variants]:
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    if not candidates:
        return configured
    available = _get_provider_models(provider)
    if available is None:
        return candidates[0]
    # Allow matching against provider-prefixed names (e.g., models/{id})
    normalized_available = {item for item in available}
    short_available = {item.split("/", 1)[-1] for item in available}
    for candidate in candidates:
        if candidate in normalized_available:
            return candidate
        prefixed = f"models/{candidate}"
        if prefixed in normalized_available:
            return prefixed
        if candidate.startswith("models/"):
            short = candidate.split("/", 1)[-1]
            if short in short_available:
                return candidate
        if candidate in short_available:
            # Return the available entry with the provider prefix if present
            for entry_id in normalized_available:
                if entry_id.split("/", 1)[-1] == candidate:
                    return entry_id
    return candidates[0]


def _resolve_comparator_models(
    primary: Optional[str],
    requested: List[str],
    *,
    include_defaults: bool = True,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    primary_entry = _lookup_model_entry(primary)
    primary_key = None
    primary_provider: Optional[str] = None
    if primary_entry:
        primary_model_name = _pick_model_identifier(primary_entry) or primary_entry["model"]
        primary_key = (primary_entry["provider"], primary_model_name)
        primary_provider = primary_entry.get("provider")

    resolved_names: List[str] = []
    resolved_configs: List[Dict[str, Any]] = []
    seen_keys = set()
    seen_names = set()

    def _add_display(name: str) -> None:
        if not name:
            return
        norm = _normalize_model_name(name)
        if norm in seen_names:
            return
        seen_names.add(norm)
        resolved_names.append(name)

    def _maybe_add(entry: Optional[Dict[str, Any]], *, fallback: Optional[str] = None) -> None:
        if entry:
            chosen_model = _pick_model_identifier(entry) or entry.get("model")
            key = (entry["provider"], chosen_model)
            if primary_key and key == primary_key:
                return
            display_name = entry.get("display") or fallback
            if display_name:
                _add_display(display_name)
            env_var = entry.get("env")
            has_credentials = not env_var or os.getenv(env_var)
            if not has_credentials and primary_provider and entry.get("provider") == primary_provider:
                has_credentials = True
            if not has_credentials:
                return
            if key in seen_keys:
                return
            seen_keys.add(key)
            config: Dict[str, Any] = {"provider": entry["provider"], "name": chosen_model}
            api_key_ref = entry.get("api_key_ref") or env_var
            if api_key_ref:
                config["api_key_ref"] = api_key_ref
            resolved_configs.append(config)
        elif fallback:
            _add_display(fallback)

    for name in requested:
        entry = _lookup_model_entry(name)
        if entry:
            _maybe_add(entry)
        else:
            _maybe_add(None, fallback=name)

    if include_defaults:
        for entry in _MODEL_REGISTRY:
            if not entry.get("default_compare"):
                continue
            _maybe_add(entry)

    return resolved_names, resolved_configs


def _contains_comparative_language(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in COMPARATIVE_MARKERS)


def _extract_comparators(text: str) -> List[str]:
    normalized = _normalize_hyphen_variants(text)
    candidates: List[str] = []
    lowered = normalized.lower()

    patterns = [
        r"compared to\s+([^.;]+)",
        r"versus\s+([^.;]+)",
        r"vs\.?\s+([^.;]+)",
        r"than\s+([^.;]+)",
        r"such as\s+([^.;]+)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, normalized, flags=re.IGNORECASE)
        for match in matches:
            tokens = re.split(r",|\/| and | or |;", match)
            for token in tokens:
                cleaned = token.strip().strip("'\"")
                if not cleaned:
                    continue
                # Skip generic placeholders
                lowered_token = cleaned.lower()
                if lowered_token in {"other models", "others", "other systems", "baseline"}:
                    continue
                if cleaned not in candidates:
                    candidates.append(cleaned)

    # Handle cases like "closed models, such as ..." by ensuring we captured capitalised words
    if not candidates:
        capitalised = re.findall(r"([A-Z][A-Za-z0-9\- ]{2,})", normalized)
        for candidate in capitalised:
            if candidate.lower() in lowered:
                if candidate.lower() in lowered and candidate not in candidates:
                    candidates.append(candidate)

    return candidates[:5]


def _extract_percentage_near(text: str, keywords: List[str]) -> Optional[float]:
    if not keywords:
        return None
    normalized = _normalize_hyphen_variants(text)
    lowered = normalized.lower()
    keyword_ranges: List[Tuple[int, int]] = []
    for keyword in keywords:
        pattern = re.escape(keyword.lower())
        for kw_match in re.finditer(pattern, lowered):
            keyword_ranges.append((kw_match.start(), kw_match.end()))
    if not keyword_ranges:
        return None

    best: Optional[Tuple[int, float]] = None
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%", normalized):
        mid = (match.start() + match.end()) // 2
        for start, end in keyword_ranges:
            if start <= mid <= end:
                distance = 0
            elif mid < start:
                distance = start - mid
            else:
                distance = mid - end
            try:
                value = float(match.group(1))
            except ValueError:
                continue
            if best is None or distance < best[0]:
                best = (distance, value)
            elif best and distance == best[0] and value:  # prefer later keyword match if tie
                best = (distance, value)
    if best is None:
        return None
    return best[1]


def _extract_percentage_range(text: str, keywords: List[str]) -> Optional[Tuple[float, float]]:
    normalized = _normalize_hyphen_variants(text)
    lowered = normalized.lower()
    if not keywords:
        return None
    pattern = r"(\d+(?:\.\d+)?)\s*[-\u2013]\s*(\d+(?:\.\d+)?)\s*%"
    for match in re.finditer(pattern, normalized):
        start, end = match.span()
        window = lowered[max(0, start - 64): min(len(lowered), end + 64)]
        if any(keyword in window for keyword in keywords):
            try:
                lo = float(match.group(1))
                hi = float(match.group(2))
            except ValueError:
                continue
            if hi < lo:
                lo, hi = hi, lo
            return lo, hi
    return None


def _extract_capabilities(text: str) -> List[str]:
    normalized = _normalize_hyphen_variants(text)
    lowered = normalized.lower()
    patterns = [
        r"(?:including|across|such as)\s+([^.;]+)",
        r"(?:covering|spanning)\s+([^.;]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            fragment = normalized[match.start(1):match.end(1)]
            parts = re.split(r",| and | & |/", fragment)
            cleaned = []
            for part in parts:
                value = part.strip().strip(". ")
                if value:
                    cleaned.append(value)
            if cleaned:
                return cleaned[:6]
    return []


def _detect_primary_model(text: str) -> Optional[str]:
    mentions = _extract_model_mentions(text)
    return mentions[0] if mentions else None


def _build_claim_settings(
    *,
    comparative: bool,
    comparators: List[str],
    comparator_configs: Optional[List[Dict[str, Any]]],
    requires_multimodal: bool,
) -> Dict[str, Any]:
    settings: Dict[str, Any] = {}
    if comparative:
        settings["requires_comparison"] = True
        if comparators:
            settings["comparand_models"] = comparators
        if comparator_configs:
            settings["comparative_models"] = comparator_configs
    if requires_multimodal:
        settings["requires_multimodal_harness"] = True
    return settings


@app.post("/submit_claim", response_model=SubmitClaimResponse)
def submit_claim(body: SubmitClaimRequest):
    if not body.raw_text and not body.url:
        raise HTTPException(status_code=400, detail="Provide raw_text or url")

    # Simple keyword-based parsing for demo presets, allow multiple claims
    source_text = body.raw_text or ""
    normalized_text = _normalize_hyphen_variants(source_text)
    raw = normalized_text.lower()
    source_url = body.url

    candidates = []

    def add(
        domain: str,
        task: str,
        metric: str,
        ref: Optional[float],
        conf: float,
        *,
        settings: Optional[Dict[str, Any]] = None,
        model_hint: Optional[str] = None,
    ) -> None:
        local_settings = dict(settings or {})
        if domain != "vision" and "requires_multimodal_harness" in local_settings:
            local_settings.pop("requires_multimodal_harness")
        candidates.append(
            {
                "model": model_hint or _detect_primary_model(source_text) or "Unspecified Model",
                "domain": domain,
                "task": task,
                "metric": metric,
                "reference_score": ref,
                "confidence": conf,
                "settings": local_settings,
            }
        )

    primary_model = _detect_primary_model(source_text)
    model_mentions = _extract_model_mentions(source_text)
    if primary_model is None and model_mentions:
        primary_model = model_mentions[0]

    comparative = _contains_comparative_language(body.raw_text or "")
    comparators = _extract_comparators(body.raw_text or "") if comparative else []
    if primary_model:
        comparators = [c for c in comparators if _normalize_model_name(c) != _normalize_model_name(primary_model)]

    if comparative:
        for mention in model_mentions:
            if primary_model and _normalize_model_name(mention) == _normalize_model_name(primary_model):
                continue
            if mention not in comparators:
                comparators.append(mention)

    resolved_comparators, comparator_configs = _resolve_comparator_models(
        primary_model,
        comparators,
        include_defaults=comparative and not comparators,
    )

    if comparative:
        comparators = resolved_comparators
    else:
        comparators = []
        comparator_configs = []

    requires_multimodal = any(marker in raw for marker in VISION_MARKERS)

    settings = _build_claim_settings(
        comparative=comparative,
        comparators=comparators,
        comparator_configs=comparator_configs,
        requires_multimodal=requires_multimodal,
    )

    comparative_suite = None
    if comparative and ("coding" in raw or "coder" in raw or "code" in raw):
        comparative_suite = "coding_competition"

    if "humaneval" in raw or "coding" in raw or "best coding" in raw:
        if comparative_suite is None and "swe-bench" not in raw and "swebench" not in raw and "aider" not in raw:
            add("coding", "HumanEval", "pass@1", 0.78, 0.85, settings=settings, model_hint=primary_model)
    if "cagent" in raw or "agents" in raw or "complex agents" in raw:
        add("agents", "cAgent-12", "success@1", 0.67, 0.8, settings=settings, model_hint=primary_model)
    if "cgui" in raw or "computers" in raw or "browser" in raw or "computer-use" in raw:
        add("computer-use", "cGUI-10", "task_success", 0.70, 0.8, settings=settings, model_hint=primary_model)
    if requires_multimodal or "vision" in raw or "image" in raw:
        add("vision", "MMMU-mini", "accuracy", None, 0.7, settings=settings, model_hint=primary_model)
    if "gsm8k" in raw or "reasoning" in raw or "math" in raw:
        add("reasoning-math", "GSM8K", "accuracy", 0.94, 0.9, settings=settings, model_hint=primary_model)

    swebench_score = None
    swebench_keywords = ["swe-bench", "swebench"]
    if any(keyword in raw for keyword in swebench_keywords):
        swebench_score = _extract_percentage_near(body.raw_text or "", swebench_keywords)
        ref = swebench_score / 100.0 if swebench_score is not None else 0.0
        add("coding", "SWE-bench Verified", "pass@1", ref, 0.9, settings=settings, model_hint=primary_model)

    aider_keywords = ["aider", "polyglot"]
    if "aider" in raw or "polyglot" in raw:
        aider_score = _extract_percentage_near(body.raw_text or "", aider_keywords)
        ref = aider_score / 100.0 if aider_score is not None else 0.0
        add("coding", "Aider Polyglot", "pass@1", ref, 0.85, settings=settings, model_hint=primary_model)

    frontend_keywords = ["front-end", "frontend", "front end"]
    if any(keyword in raw for keyword in frontend_keywords):
        frontend_score = _extract_percentage_near(body.raw_text or "", frontend_keywords)
        ref = frontend_score / 100.0 if frontend_score is not None else None
        add("coding", "Front-end developer study", "win_rate", ref, 0.7, settings=settings, model_hint=primary_model)

    efficiency_tokens = ["token", "tokens"]
    efficiency_markers = (
        "less output tokens",
        "fewer output tokens",
        "less tokens",
        "fewer tokens",
        "reduced tokens",
        "token savings",
    )
    if any(marker in raw for marker in efficiency_markers):
        range_values = _extract_percentage_range(body.raw_text or "", efficiency_tokens)
        single_value = _extract_percentage_near(body.raw_text or "", efficiency_tokens)
        capabilities = _extract_capabilities(body.raw_text or "")
        efficiency_settings: Dict[str, Any] = {
            "claim_type": "efficiency_delta",
            "metric": "output_tokens",
            "comparand_models": comparators,
            "range": None,
            "capabilities": capabilities,
        }
        if range_values:
            lo, hi = range_values
            efficiency_settings["range"] = {"min": lo, "max": hi}
        elif single_value is not None:
            efficiency_settings["range"] = {"value": single_value}
        add(
            "efficiency",
            "Token efficiency",
            "token_delta",
            None,
            0.6,
            settings={**settings, **efficiency_settings},
            model_hint=primary_model,
        )

    def with_suite(base_settings: Dict[str, Any]) -> Dict[str, Any]:
        if not comparative_suite:
            return base_settings
        merged = dict(base_settings)
        merged["comparative_suite"] = comparative_suite
        return merged

    # Re-run coding additions to include suite info where applicable
    if comparative_suite:
        add(
            "coding",
            "Claimscope coding competition",
            "pass_rate",
            None,
            0.7,
            settings=with_suite(settings),
            model_hint=primary_model,
        )

    if not candidates:
        # default to a single reasoning-math claim
        add("reasoning-math", "GSM8K", "accuracy", 0.94, 0.6, settings=settings, model_hint=primary_model)

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
                    "settings": _json.dumps(c.get("settings") or {}),
                    "reference_score": c["reference_score"],
                    "source_url": source_url,
                    "confidence": c["confidence"],
                },
            )
            out_ids.append(claim_id)
            out_claims.append(
                Claim(
                    id=claim_id,
                    model=c["model"],
                    domain=c["domain"],
                    task=c["task"],
                    metric=c["metric"],
                    settings=c.get("settings") or {},
                    reference_score=c["reference_score"],
                    source_url=source_url,
                    confidence=c["confidence"],
                    validation_count=0,
                )
            )
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
        row = conn.execute(
            text(
                """
                SELECT r.*, c.validation_count
                FROM runs r
                JOIN claims c ON c.id = r.claim_id
                WHERE r.id = :id
                """
            ),
            {"id": run_id},
        ).mappings().first()
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
            validation_count=row.get("validation_count"),
            status_label=row.get("status_label"),
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
            validation_count=int(c.get("validation_count") or 0),
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
