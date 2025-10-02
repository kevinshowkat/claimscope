import pytest

from apps.api.worker.vision_mmmu import run_mmmu_subset


def test_mmmu_harness_returns_comparator_scores():
    result, latencies, report = run_mmmu_subset(
        model_name="Llama 3.2 11B Vision",
        comparators=["Claude 3 Haiku", "Gemini 1.5 Pro"],
    )

    assert pytest.approx(result["score_value"], rel=1e-6) == 0.74
    assert len(latencies) >= 1

    available = report["available"]
    assert "Claude 3 Haiku" in available
    assert "Gemini 1.5 Pro" in available
    metric_key = report["metric"]
    assert available["Claude 3 Haiku"][metric_key] < result["score_value"]
    assert report["leaderboard"][0][metric_key] >= result["score_value"]


def test_mmmu_harness_marks_missing_comparators():
    _, _, report = run_mmmu_subset(
        model_name="Llama 3.2 11B Vision",
        comparators=["Imaginary Vision Model"],
    )

    assert "Imaginary Vision Model" in report["missing"]
