import base64
import json

from apps.api.worker.agents_cagent import run_cagent_suite


def test_cagent_suite_metrics_and_artifact():
    result, durations, artifact, metadata = run_cagent_suite()

    assert result["metrics"]["success@1"] == 1.0
    assert result["metrics"]["success@3"] == 1.0
    assert result["metrics"]["tool_error_rate"] == 0.0
    assert result["metrics"]["action_timeout_rate"] == 0.0
    assert len(durations) == 12

    assert artifact["name"] == "agent_trace.json"
    assert artifact["content_type"] == "application/json"
    assert artifact["bytes"] > 200

    prefix, encoded = artifact["data_url"].split(",", 1)
    assert prefix.startswith("data:application/json;base64")
    payload = base64.b64decode(encoded)
    data = json.loads(payload)
    assert data["suite"] == "cAgent-12"
    assert len(data["tasks"]) == 12
    assert all(task["success"] for task in data["tasks"])

    assert metadata["suite"] == "cAgent-12"
    assert metadata["dataset_id"] == "cagent-12"
    assert isinstance(metadata["dataset_hash"], str) and len(metadata["dataset_hash"]) == 64
    assert isinstance(metadata["harness_hash"], str) and len(metadata["harness_hash"]) == 64
    assert len(metadata["seeds"]) == 12
