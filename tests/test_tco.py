from __future__ import annotations

from lowpower_llm_cluster.tco import apply_tco_to_summary, break_even_analysis, complete_node_power, deployment_requirements, evaluate_tco


SCENARIOS = {
    "component_costs_cad": {
        "cpu_host": 180, "motherboard": 140, "host_ram_32gb": 100, "system_ram_32gb": 100,
        "storage_1tb": 80, "psu_750w": 120, "power_supply": 80, "pcie_adapter": 40,
        "cooling": 60, "chassis": 100, "chassis_misc": 30,
    },
    "ownership_profiles": {
        "new-build": {"owned_components": []},
        "reuse-host-core": {"owned_components": ["cpu_host", "motherboard", "host_ram_32gb", "system_ram_32gb", "storage_1tb", "chassis", "chassis_misc"]},
        "reuse-complete-host": {"owned_components": ["cpu_host", "motherboard", "host_ram_32gb", "system_ram_32gb", "storage_1tb", "psu_750w", "power_supply", "cooling", "chassis", "chassis_misc"]},
        "reuse-everything": {"owned_components": ["cpu_host", "motherboard", "host_ram_32gb", "system_ram_32gb", "storage_1tb", "psu_750w", "power_supply", "pcie_adapter", "cooling", "chassis", "chassis_misc"]},
    },
    "power_assumptions": {"host_idle_w": 35, "host_load_w": 90, "gpu_idle_w": 20, "integrated_idle_ratio": 0.25, "psu_cooling_overhead_pct": 0.08},
    "energy_scenarios": {"mixed-3yr": {"load_hours_per_day": 6, "idle_hours_per_day": 18, "days_per_year": 365, "electricity_cad_per_kwh": 0.15, "years": 3}},
}


def gpu():
    return {"id": "gpu", "name": "24GB GPU", "category": "gpu_accelerator", "host_mode": "pcie_add_in_card", "memory_config_status": "fixed", "power_target_w": 350, "power_scope": "accelerator_board_power_reference"}


def box():
    return {"id": "box", "name": "Integrated node", "category": "compute_node", "hardware_class": "mini_pc", "memory_config_status": "included", "power_target_w": 65, "power_scope": "complete_node_input"}


def test_gpu_requires_full_new_build_stack():
    req = deployment_requirements(gpu())
    for component in ("cpu_host", "motherboard", "host_ram_32gb", "storage_1tb", "psu_750w", "pcie_adapter", "cooling", "chassis"):
        assert component in req["components"]


def test_new_build_gpu_counts_full_infrastructure():
    tco = evaluate_tco(gpu(), 500, scenarios=SCENARIOS)
    assert tco["infrastructure"]["total_cad"] == 850
    assert tco["complete_node_acquisition_cad"] == 1350


def test_reuse_host_core_only_buys_missing_support_parts():
    tco = evaluate_tco(gpu(), 500, scenarios=SCENARIOS, ownership_profile="reuse-host-core")
    assert tco["infrastructure"]["total_cad"] == 220
    assert tco["infrastructure"]["avoided_acquisition_cad"] == 630
    assert tco["complete_node_acquisition_cad"] == 720
    by_component = {row["component"]: row for row in tco["infrastructure"]["components"]}
    assert by_component["cpu_host"]["basis"] == "already_owned"
    assert by_component["psu_750w"]["basis"] == "planning_assumption"


def test_reuse_complete_host_can_reduce_gpu_to_adapter_only():
    tco = evaluate_tco(gpu(), 500, scenarios=SCENARIOS, ownership_profile="reuse-complete-host")
    assert tco["infrastructure"]["total_cad"] == 40
    assert tco["complete_node_acquisition_cad"] == 540


def test_custom_owned_components_stack_on_profile():
    tco = evaluate_tco(gpu(), 500, scenarios=SCENARIOS, ownership_profile="reuse-host-core", owned_components=["psu_750w"])
    assert tco["infrastructure"]["total_cad"] == 100


def test_owned_hardware_does_not_remove_complete_node_power():
    new = evaluate_tco(gpu(), 500, scenarios=SCENARIOS, ownership_profile="new-build")
    reused = evaluate_tco(gpu(), 500, scenarios=SCENARIOS, ownership_profile="reuse-everything")
    assert new["power"] == reused["power"]
    assert reused["operating"] == new["operating"]
    assert reused["complete_node_acquisition_cad"] < new["complete_node_acquisition_cad"]


def test_gpu_board_power_is_not_relabeled_wall_power():
    power = complete_node_power(gpu(), SCENARIOS)
    assert power["load_w"] > 350 and power["confidence"] == "low"


def test_complete_system_has_no_host_infrastructure_assumption():
    assert evaluate_tco(box(), 700, scenarios=SCENARIOS)["complete_node_acquisition_cad"] == 700


def test_break_even_accepts_different_ownership_profiles():
    result = break_even_analysis(gpu(), 500, box(), 700, scenarios=SCENARIOS, ownership_profile_a="reuse-host-core")
    assert result["a"]["ownership_profile"] == "reuse-host-core"
    assert result["a"]["tco"]["complete_node_acquisition_cad"] == 720
    assert result["price_a_break_even_cad"] > break_even_analysis(gpu(), 500, box(), 700, scenarios=SCENARIOS)["price_a_break_even_cad"]


def test_tco_ranking_changes_with_ownership(monkeypatch):
    parts = [gpu(), box()]
    monkeypatch.setattr("lowpower_llm_cluster.tco.load_catalog", lambda: {"parts": parts})
    summary = {"recommendations": [
        {"id": "gpu", "name": "Cheap 24GB GPU", "deal_score": 80.0, "current_cad": 500.0, "recommendation": "Buy", "reasons": []},
        {"id": "box", "name": "Integrated node", "deal_score": 76.0, "current_cad": 700.0, "recommendation": "Buy", "reasons": []},
    ]}
    fresh = apply_tco_to_summary({"recommendations": [dict(row, reasons=[]) for row in summary["recommendations"]]}, scenarios=SCENARIOS)
    reuse = apply_tco_to_summary({"recommendations": [dict(row, reasons=[]) for row in summary["recommendations"]]}, scenarios=SCENARIOS, ownership_profile="reuse-host-core")
    fresh_gpu = next(row for row in fresh["recommendations"] if row["id"] == "gpu")
    reuse_gpu = next(row for row in reuse["recommendations"] if row["id"] == "gpu")
    assert reuse_gpu["tco"]["complete_node_acquisition_cad"] < fresh_gpu["tco"]["complete_node_acquisition_cad"]
