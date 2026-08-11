# tests/test_power_model.py
from lowpower_llm_cluster.power_model import (
    CATEGORY_POWER_DEFAULTS,
    daily_energy_usage,
    energy_usage_wh,
    estimate_complete_node_power,
    estimate_device_power,
)


def test_measured_power_wins_over_published_and_inferred_values():
    part = {
        "category": "mini_pc",
        "measured_idle_w": 6.2,
        "measured_load_w": 31.4,
        "power_target_w": 65,
    }
    result = estimate_device_power(part)
    assert result["idle_w"] == 6.2
    assert result["load_w"] == 31.4
    assert result["basis"] == "measured_power"
    assert result["confidence"] == "high"
    assert result["inferred"] is False


def test_published_target_is_used_before_category_fallback():
    result = estimate_device_power({"category": "gpu_accelerator", "power_target_w": 250, "power_scope": "accelerator_board"})
    assert result["load_w"] == 250
    assert result["basis"] == "published_target_power"
    assert result["inferred"] is True


def test_published_maximum_can_generate_typical_planning_estimate():
    result = estimate_device_power({"category": "npu_accelerator", "power_max_w": 20})
    assert result["load_w"] == 16.4
    assert result["max_w"] == 20
    assert result["basis"] == "derived_from_published_maximum"


def test_every_catalog_category_has_nonzero_fallback_power():
    categories = {
        "compute_node", "mini_pc", "dev_board", "sbc", "embedded_board", "specialty_board",
        "control_plane", "apple_silicon_system", "mobile_phone", "tablet", "media_device",
        "gpu_accelerator", "npu_accelerator", "tpu_accelerator", "ai_asic_accelerator",
        "fpga_accelerator", "adaptive_soc", "decommissioned_accelerator", "network", "memory", "storage",
    }
    assert categories <= set(CATEGORY_POWER_DEFAULTS)
    for category in categories:
        result = estimate_device_power({"category": category})
        assert result["idle_w"] > 0
        assert result["load_w"] > result["idle_w"]
        assert result["basis"] == "inferred_category_baseline"
        assert result["confidence"] == "low"


def test_unknown_future_category_still_receives_fallback():
    result = estimate_device_power({"category": "future_quantum_widget"})
    assert result["idle_w"] == 5.0
    assert result["load_w"] == 25.0
    assert result["basis"] == "inferred_category_baseline"


def test_accelerator_complete_node_adds_host_and_efficiency_overhead():
    result = estimate_complete_node_power(
        {"category": "gpu_accelerator", "power_target_w": 250, "power_scope": "accelerator_board"},
        {"host_idle_w": 30, "host_load_w": 80, "psu_cooling_overhead_pct": 0.10},
    )
    assert result["load_w"] == 363.0
    assert result["idle_w"] > 30
    assert "plus_host" in result["basis"]


def test_integrated_apple_system_does_not_add_second_host():
    result = estimate_complete_node_power({"category": "apple_silicon_system", "power_target_w": 40})
    assert result["load_w"] == 40
    assert "plus_host" not in result["basis"]


def test_wh_calculation_uses_explicit_duty_cycle():
    result = energy_usage_wh({"idle_w": 10, "load_w": 50, "basis": "test", "confidence": "high"}, load_hours=4, idle_hours=20)
    assert result["wh"] == 400.0
    assert result["kwh"] == 0.4
    assert result["average_w"] == 16.67


def test_daily_energy_never_returns_unknown_for_supported_category():
    result = daily_energy_usage({"category": "storage"}, load_hours=2, idle_hours=22)
    assert result["energy"]["wh"] > 0
    assert result["power"]["confidence"] == "low"


def test_battery_and_charger_numbers_are_not_mistaken_for_consumption():
    result = estimate_device_power({"category": "mobile_phone", "battery_wh": 18, "charger_w": 45})
    assert result["basis"] == "inferred_category_baseline"
    assert result["load_w"] == CATEGORY_POWER_DEFAULTS["mobile_phone"]["load_w"]
