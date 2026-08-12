# tests/test_normalized_scoring.py
from __future__ import annotations

import pytest

from lowpower_llm_cluster.normalized_scoring import (
    MetricSpec,
    TaskRequirements,
    cluster_metrics,
    compatibility_gates,
    derive_metrics,
    normalize_metric,
    pareto_frontier,
    rank_devices,
)
from lowpower_llm_cluster.scoring_inputs import benchmark_result_to_device


def _devices() -> list[dict[str, object]]:
    return [
        {
            "id": "fast-gpu",
            "name": "Fast GPU",
            "decode_tokens_s": 40.0,
            "prefill_tokens_s": 400.0,
            "system_power_w": 100.0,
            "idle_w": 10.0,
            "usable_ai_memory_gb": 16.0,
            "model_capacity_b_q4": 24.0,
            "memory_bandwidth_gbs": 400.0,
            "price_usd": 300.0,
            "software_support": 95.0,
            "reliability": 90.0,
            "dc_powerability": 50.0,
            "sleep_wake": 85.0,
        },
        {
            "id": "efficient-apu",
            "name": "Efficient APU",
            "decode_tokens_s": 20.0,
            "prefill_tokens_s": 200.0,
            "system_power_w": 35.0,
            "idle_w": 5.0,
            "usable_ai_memory_gb": 32.0,
            "model_capacity_b_q4": 50.0,
            "memory_bandwidth_gbs": 100.0,
            "price_usd": 200.0,
            "software_support": 85.0,
            "reliability": 88.0,
            "dc_powerability": 95.0,
            "sleep_wake": 95.0,
        },
    ]


def test_lower_is_better_percentile_for_power() -> None:
    devices = _devices()
    efficient = normalize_metric(devices[1], devices, MetricSpec("system_power_w", 1.0, False))
    fast = normalize_metric(devices[0], devices, MetricSpec("system_power_w", 1.0, False))
    assert efficient is not None and fast is not None
    assert efficient > fast


def test_off_grid_profile_favors_efficiency_when_both_are_usable() -> None:
    rows = rank_devices(
        _devices(),
        TaskRequirements(workload="off_grid_ai", model_params_b=14, expected_output_tokens=1000),
    )
    assert rows[0]["id"] == "efficient-apu"
    assert rows[0]["eligible"] is True
    assert rows[0]["derived"]["tokens_per_kwh"] > rows[1]["derived"]["tokens_per_kwh"]


def test_model_fit_is_a_hard_compatibility_gate_when_memory_is_known() -> None:
    device = {"usable_ai_memory_gb": 8.0}
    failures = compatibility_gates(device, TaskRequirements(model_params_b=32, bits_per_weight=4.0))
    assert failures
    assert "model needs" in failures[0]


def test_energy_to_task_and_solar_recovery_are_arithmetic_only() -> None:
    metrics = derive_metrics(
        {"decode_tokens_s": 25.0, "prefill_tokens_s": 250.0, "system_power_w": 50.0},
        TaskRequirements(expected_prompt_tokens=1000, expected_output_tokens=500, available_solar_w=200),
    )
    assert metrics["task_seconds"] == pytest.approx(24.0)
    assert metrics["wh_per_task"] == pytest.approx(1 / 3)
    assert metrics["solar_recovery_hours"] == pytest.approx((1 / 3) / 200)


def test_pareto_frontier_removes_slower_higher_energy_device() -> None:
    rows = [
        {"id": "a", "derived": {"task_seconds": 10.0, "wh_per_task": 8.0}},
        {"id": "b", "derived": {"task_seconds": 14.0, "wh_per_task": 5.0}},
        {"id": "c", "derived": {"task_seconds": 20.0, "wh_per_task": 10.0}},
    ]
    assert {row["id"] for row in pareto_frontier(rows)} == {"a", "b"}


def test_cluster_scaling_efficiency_uses_measured_combined_speed() -> None:
    result = cluster_metrics(
        [{"decode_tokens_s": 14.0}, {"decode_tokens_s": 10.0}],
        measured_combined_decode_tokens_s=19.0,
    )
    assert result["ideal_decode_tokens_s"] == 24.0
    assert result["scaling_efficiency"] == pytest.approx(19 / 24)


def test_benchmark_bridge_requires_complete_node_power() -> None:
    result = {
        "schema_version": 2,
        "result_id": "x",
        "hardware_id": "node",
        "configuration_id": "cfg",
        "workload_class": "llm",
        "runtime": {"runtime_name": "llama.cpp"},
        "model": {"name": "m", "quantization": "Q4"},
        "workload": {"context_tokens": 4096},
        "metrics": {
            "generation_tokens_per_second": {"median": 12.0},
            "prompt_tokens_per_second": {"median": 100.0},
        },
        "power": {
            "decode": {"phase": "decode", "scope": "accelerator_board", "mean_w": 5.0},
        },
        "cost": {},
    }
    device = benchmark_result_to_device(result)
    assert device["metrics"]["decode_tokens_s"]["value"] == 12.0
    assert "system_power_w" not in device["metrics"]
