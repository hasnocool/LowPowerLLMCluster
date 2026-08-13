from __future__ import annotations

import pytest

from lowpower_llm_cluster.normalized_scoring import MetricSpec, TaskRequirements, cluster_metrics, compatibility_gates, derive_metrics, normalize_metric, pareto_frontier, rank_devices
from lowpower_llm_cluster.scoring_inputs import benchmark_result_to_device, merge_device_records


def _metric(value: float, source_type: str = "measured_local", confidence: float = 1.0) -> dict[str, object]:
    return {"value": value, "source_type": source_type, "confidence": confidence}


def _devices() -> list[dict[str, object]]:
    return [
        {"id": "fast-gpu", "name": "Fast GPU", "metrics": {"decode_tokens_s": _metric(40), "prefill_tokens_s": _metric(400), "system_power_w": _metric(100), "idle_w": _metric(10), "usable_ai_memory_gb": _metric(16, "manufacturer", .75), "model_capacity_b_q4": _metric(24, "derived_estimate", .6), "memory_bandwidth_gbs": _metric(400, "manufacturer", .75), "price_usd": _metric(300, "reported", .9), "software_support": _metric(95, "reported", .9), "reliability": _metric(90), "dc_powerability": _metric(50, "reported", .9), "sleep_wake": _metric(85, "reported", .9)}},
        {"id": "efficient-apu", "name": "Efficient APU", "metrics": {"decode_tokens_s": _metric(20), "prefill_tokens_s": _metric(200), "system_power_w": _metric(35), "idle_w": _metric(5), "usable_ai_memory_gb": _metric(32, "manufacturer", .75), "model_capacity_b_q4": _metric(50, "derived_estimate", .6), "memory_bandwidth_gbs": _metric(100, "manufacturer", .75), "price_usd": _metric(200, "reported", .9), "software_support": _metric(85, "reported", .9), "reliability": _metric(88), "dc_powerability": _metric(95, "reported", .9), "sleep_wake": _metric(95, "reported", .9)}}
    ]


def test_unannotated_metric_is_not_normalized_as_full_confidence_evidence() -> None:
    devices = [{"system_power_w": 25.0}, {"system_power_w": 50.0}]
    assert normalize_metric(devices[0], devices, MetricSpec("system_power_w", 1.0, False)) is None


def test_lower_is_better_percentile_for_power() -> None:
    devices = _devices()
    efficient = normalize_metric(devices[1], devices, MetricSpec("system_power_w", 1.0, False))
    fast = normalize_metric(devices[0], devices, MetricSpec("system_power_w", 1.0, False))
    assert efficient is not None and fast is not None and efficient > fast


def test_off_grid_profile_favors_efficiency_when_both_are_usable() -> None:
    rows = rank_devices(_devices(), TaskRequirements(workload="off_grid_ai", model_params_b=14, expected_output_tokens=1000))
    assert rows[0]["id"] == "efficient-apu"
    assert rows[0]["eligible"] is True
    assert rows[0]["derived"]["tokens_per_kwh"] > rows[1]["derived"]["tokens_per_kwh"]


def test_profile_minimum_is_a_hard_eligibility_gate() -> None:
    slow = {"id": "slow", "name": "Slow", "metrics": {"decode_tokens_s": _metric(2), "system_power_w": _metric(10)}}
    row = rank_devices([slow], TaskRequirements(workload="interactive_chat"))[0]
    assert row["eligible"] is False
    assert any("decode_tokens_s" in failure for failure in row["gates"])


def test_model_fit_is_a_hard_compatibility_gate_when_memory_is_known() -> None:
    failures = compatibility_gates({"usable_ai_memory_gb": 8.0}, TaskRequirements(model_params_b=32, bits_per_weight=4.0))
    assert failures and "model needs" in failures[0]


def test_task_energy_uses_phase_specific_power() -> None:
    metrics = derive_metrics({"decode_tokens_s": 25.0, "prefill_tokens_s": 250.0, "system_power_w": 50.0, "prefill_power_w": 100.0}, TaskRequirements(expected_prompt_tokens=1000, expected_output_tokens=500, available_solar_w=200))
    assert metrics["task_seconds"] == pytest.approx(24.0)
    assert metrics["joules_per_task"] == pytest.approx(1400.0)
    assert metrics["wh_per_task"] == pytest.approx(1400 / 3600)


def test_task_energy_falls_back_to_decode_power_when_prefill_power_missing() -> None:
    metrics = derive_metrics({"decode_tokens_s": 25.0, "prefill_tokens_s": 250.0, "system_power_w": 50.0}, TaskRequirements(expected_prompt_tokens=1000, expected_output_tokens=500))
    assert metrics["wh_per_task"] == pytest.approx(1 / 3)


def test_pareto_frontier_excludes_explicitly_ineligible_rows() -> None:
    rows = [
        {"id": "a", "eligible": True, "derived": {"task_seconds": 10.0, "wh_per_task": 8.0}},
        {"id": "b", "eligible": True, "derived": {"task_seconds": 14.0, "wh_per_task": 5.0}},
        {"id": "bad", "eligible": False, "derived": {"task_seconds": 1.0, "wh_per_task": 1.0}},
        {"id": "legacy", "derived": {"task_seconds": 20.0, "wh_per_task": 10.0}},
    ]
    assert {row["id"] for row in pareto_frontier(rows)} == {"a", "b"}


def test_cluster_scaling_efficiency_uses_measured_combined_speed() -> None:
    result = cluster_metrics([{"decode_tokens_s": 14.0}, {"decode_tokens_s": 10.0}], measured_combined_decode_tokens_s=19.0)
    assert result["ideal_decode_tokens_s"] == 24.0
    assert result["scaling_efficiency"] == pytest.approx(19 / 24)


def _benchmark(*, result_id: str, model: str = "m", quantization: str = "Q4", context: int = 4096) -> dict[str, object]:
    return {"schema_version": 2, "result_id": result_id, "hardware_id": "node", "configuration_id": "cfg", "workload_class": "llm", "runtime": {"runtime_name": "llama.cpp"}, "model": {"name": model, "quantization": quantization}, "workload": {"context_tokens": context}, "metrics": {"generation_tokens_per_second": {"median": 12.0}, "prompt_tokens_per_second": {"median": 100.0}}, "power": {"decode": {"phase": "decode", "scope": "accelerator_board", "mean_w": 5.0}}, "cost": {}}


def test_benchmark_bridge_requires_complete_node_power_and_does_not_infer_context_capacity() -> None:
    device = benchmark_result_to_device(_benchmark(result_id="x"))
    assert device["metrics"]["decode_tokens_s"]["value"] == 12.0
    assert "system_power_w" not in device["metrics"]
    assert device["benchmarked_context_tokens"] == 4096
    assert "context_capacity_tokens" not in device


def test_benchmark_condition_identity_prevents_incompatible_merges() -> None:
    first = benchmark_result_to_device(_benchmark(result_id="a", model="model-a"))
    second = benchmark_result_to_device(_benchmark(result_id="b", model="model-b"))
    assert first["id"] != second["id"]
    assert len(merge_device_records([first, second])) == 2
