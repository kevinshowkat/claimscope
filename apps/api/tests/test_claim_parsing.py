import pytest

from apps.api.app.main import (
    _build_claim_settings,
    _contains_comparative_language,
    _detect_primary_model,
    _extract_comparators,
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


@pytest.mark.parametrize(
    "comparative, comparators, multimodal, expected",
    [
        (True, ["GPT-4"], True, {"requires_comparison": True, "comparand_models": ["GPT-4"], "requires_multimodal_harness": True}),
        (False, [], False, {}),
    ],
)
def test_build_claim_settings_shapes_flags(comparative, comparators, multimodal, expected):
    settings = _build_claim_settings(
        comparative=comparative,
        comparators=comparators,
        requires_multimodal=multimodal,
    )
    assert settings == expected
