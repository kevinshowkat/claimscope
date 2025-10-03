import pytest

from apps.api.app.main import (
    _build_claim_settings,
    _contains_comparative_language,
    _detect_primary_model,
    _extract_comparators,
    _extract_model_mentions,
    _resolve_comparator_models,
)


def test_comparative_detection_picks_up_superlatives():
    raw = "Claude Opus 4 is the world's best coding model, better than GPT-4o or Gemini."
    assert _contains_comparative_language(raw) is True


def test_extract_comparators_handles_such_as_phrases():
    raw = (
        "The Llama 3.2 11B vision model exceeds closed models, such as Claude 3 Haiku and GPT-4o, on image tasks."
    )
    comparators = _extract_comparators(raw)
    assert "Claude 3 Haiku" in comparators
    assert "GPT-4o" in comparators


def test_detect_primary_model_prefers_named_model_variant():
    raw = "The Llama 3.2 11B Vision model is a drop-in replacement for text equivalents."
    detected = _detect_primary_model(raw)
    assert detected is not None
    assert detected.lower().startswith("llama 3.2")


def test_extract_model_mentions_picks_multiple_models():
    raw = "Claude Opus 4 faces GPT-4o, GPT-5-mini, and Gemini 1.5 Pro in head-to-head coding trials."
    mentions = _extract_model_mentions(raw)
    assert "Claude Opus 4" in mentions
    assert "GPT-4o" in mentions
    assert any(name.lower().startswith("gpt-5") for name in mentions)


@pytest.mark.parametrize(
    "comparative, comparators, comparator_configs, multimodal, expected",
    [
        (
            True,
            ["GPT-4"],
            [{"provider": "openai", "name": "gpt-4"}],
            True,
            {
                "requires_comparison": True,
                "comparand_models": ["GPT-4"],
                "comparative_models": [{"provider": "openai", "name": "gpt-4"}],
                "requires_multimodal_harness": True,
            },
        ),
        (False, [], [], False, {}),
    ],
)
def test_build_claim_settings_shapes_flags(
    comparative, comparators, comparator_configs, multimodal, expected
):
    settings = _build_claim_settings(
        comparative=comparative,
        comparators=comparators,
        comparator_configs=comparator_configs,
        requires_multimodal=multimodal,
    )
    assert settings == expected


def test_resolve_comparator_models_adds_cross_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("GOOGLE_GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    names, configs = _resolve_comparator_models(
        "Claude Opus 4",
        ["Claude Sonnet 4"],
        include_defaults=True,
    )
    assert "Claude Sonnet 4" in names
    providers = {cfg["provider"] for cfg in configs}
    assert "openai" in providers
    assert "anthropic" in providers
    model_names = {cfg["name"] for cfg in configs}
    assert any(name.startswith("gpt-5") for name in model_names)


def test_resolve_comparator_models_keeps_names_without_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    names, configs = _resolve_comparator_models(
        "Claude Opus 4",
        ["GPT-4o"],
        include_defaults=True,
    )
    assert "GPT-4o" in names
    assert any(label.startswith("GPT-5") for label in names)
    assert configs == []


def test_resolve_comparator_models_handles_gpt5_alias(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    names, configs = _resolve_comparator_models(
        "Claude Opus 4",
        ["gpt-5-thinking"],
        include_defaults=False,
    )
    assert any(label.lower().startswith("gpt-5") for label in names)
    assert configs and configs[0]["name"].startswith("gpt-5")


def test_resolve_comparator_models_falls_back_to_unknown_labels():
    names, configs = _resolve_comparator_models(
        "Claude Opus 4",
        ["ACME Model X"],
        include_defaults=False,
    )
    assert "ACME Model X" in names
    assert configs == []
