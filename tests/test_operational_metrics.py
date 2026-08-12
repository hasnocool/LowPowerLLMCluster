# tests/test_operational_metrics.py
from __future__ import annotations

import pytest

from lowpower_llm_cluster.operational_metrics import (
    deployability_score,
    energy_proportionality,
    operational_dimensions,
    reliability_score,
    software_support_score,
    sustained_ratio,
    thermal_headroom_c,
)
from lowpower_llm_cluster.optimizer import rank_devices_full
from lowpower_llm_cluster.normalized_scoring import TaskRequirements


def test_operational_dimensions_are_transparent_and_separate() -> None:
    device = {
        "software": {
            "llama_cpp": True,
            "pytorch": True,
            "gguf": True,
            "linux": True,
            "driver_maturity": 80,
            "docker": True,
        },
        "deployability": {
            "installation": 90,
            "driver_setup": 80,
            "power_integration": 95,
            "host_compatibility": 90,
        },
        "soak": {
            "hours": 24,
            "crashes": 0,
            "resets": 0,
            "inference_errors": 0,
            "thermal_throttle_events": 0,
            "throughput_cv": 0.05,
            "automatic_recovery": True,
        },
        "burst_decode_tokens_s": 20.0,
        "sustained_decode_tokens_s": 18.0,
        "thermal_throttle_c": 95.0,
        "sustained_temp_c": 75.0,
        "idle_w": 5.0,
        "system_power_w": 50.0,
    }
    assert software_support_score(device) is not None
    assert deployability_score(device) is not None
    assert reliability_score(device) is not None
    assert sustained_ratio(device) == pytest.approx(0.9)
    assert thermal_headroom_c(device) == 20.0
    assert energy_proportionality(device) == pytest.approx(0.9)
    dimensions = operational_dimensions(device)
    assert dimensions["software_support"] is not None
    assert dimensions["deployability"] is not None


def test_explainable_optimizer_keeps_theoretical_and_practical_separate() -> None:
    devices = [
        {
            "id": "measured",
            "name": "Measured",
            "decode_tokens_s": 20.0,
            "prefill_tokens_s": 200.0,
            "system_power_w": 40.0,
            "usable_ai_memory_gb": 32.0,
            "model_capacity_b_q4": 50.0,
            "fp16_tflops": 8.0,
        },
        {
            "id": "paper-fast",
            "name": "Paper Fast",
            "fp16_tflops": 100.0,
            "int8_tops": 200.0,
            "usable_ai_memory_gb": 8.0,
        },
    ]
    rows = rank_devices_full(devices, TaskRequirements(workload="interactive_chat"))
    by_id = {row["id"]: row for row in rows}
    assert by_id["paper-fast"]["theoretical_score"] is not None
    assert any("no measured/sourced decode throughput" in reason for reason in by_id["paper-fast"]["reasons"])
    assert by_id["measured"]["practical_score"] is not None
