from __future__ import annotations

from lowpower_llm_cluster.tco import apply_tco_to_summary, break_even_analysis, complete_node_power, deployment_requirements, evaluate_tco


SCENARIOS = {
    "component_costs_cad": {
        "cpu_host": 180,
        "motherboard": 140,
        "host_ram_32gb": 100,
        "storage_1tb": 80,
        "psu_750w": 120,
        "pcie_adapter": 40,
        "cooling": 60,
        "chassis": 100,
        "chassis_misc": 30,
    },
    "power_assumptions": {
        "host_idle_w": 35,
        "host_load_w": 90,
        "gpu_idle_w": 20,
        "integrated_idle_ratio": 0.25,
        "psu_cooling_overhead_pct": 0.08,
    },
    "energy_scenarios": {
        "mixed-3yr": {
            "load_hours_per_day": 6,
            "idle_hours_per_day": 18,
            "days_per_year": 365,
            "electricity_cad_per_kwh": 0.15,
            "years": 3,
        }
    },
}


def gpu():
    return {"id": "gpu", "name": "24GB GPU", "category": "gpu_accelerator", "host_mode": "pcie_add_in_card", "memory_config_status": "fixed", "power_target_w": 350, "power_scope": "accelerator_board_power_reference"}


def box():
    return {"id": "box", "name": "Integrated node", "category": "compute_node", "hardware_class": "mini_pc", "memory_config_status": "included", "power_target_w": 65, "power_scope": "complete_node_input"}


def test_gpu_requires_full_new_build_stack():
    req = deployment_requirements(gpu())
    assert req["profile"] == "host_attached_pcie"
    for component in ("cpu_host", "motherboard", "host_ram_32gb", "storage_1tb", "psu_750w", "pcie_adapter", "cooling", "chassis"):
        assert component in req["components"]


def test_500_gpu_does_not_have_500_complete_node_cost():
    tco = evaluate_tco(gpu(), 500, scenarios=SCENARIOS)
    assert tco["infrastructure"]["total_cad"] == 850
    assert tco["complete_node_acquisition_cad"] == 1350
    assert tco["total_cost_of_ownership_cad"] > 1350


def test_gpu_board_power_is_not_relabeled_wall_power():
    power = complete_node_power(gpu(), SCENARIOS)
    assert power["load_w"] > 350
    assert power["confidence"] == "low"
    assert "estimated_complete_node" in power["basis"]


def test_complete_system_has_no_host_infrastructure_assumption():
    tco = evaluate_tco(box(), 700, scenarios=SCENARIOS)
    assert tco["infrastructure"]["total_cad"] == 0
    assert tco["complete_node_acquisition_cad"] == 700


def test_break_even_solves_gpu_price_threshold():
    result = break_even_analysis(gpu(), 500, box(), 700, scenarios=SCENARIOS)
    assert result["currently_cheaper"] == "b"
    assert result["price_a_break_even_cad"] < 500
    assert result["price_b_break_even_cad"] > 700
    assert result["electricity_rate_break_even_cad_per_kwh"] is None or result["electricity_rate_break_even_cad_per_kwh"] >= 0


def test_break_even_can_solve_load_hours_when_threshold_is_in_range():
    local = {**SCENARIOS, "component_costs_cad": {key: 0 for key in SCENARIOS["component_costs_cad"]}}
    a = {"id": "a", "name": "Fast hungry", "category": "compute_node", "memory_config_status": "included", "power_target_w": 300, "power_scope": "complete_node_input"}
    b = {"id": "b", "name": "Slow efficient", "category": "compute_node", "memory_config_status": "included", "power_target_w": 80, "power_scope": "complete_node_input"}
    result = break_even_analysis(a, 300, b, 500, scenarios=local)
    value = result["load_hours_per_day_break_even"]
    assert value is None or 0 <= value <= 24


def test_tco_can_demote_expensive_infrastructure_candidate(monkeypatch):
    parts = [gpu(), box()]
    monkeypatch.setattr("lowpower_llm_cluster.tco.load_catalog", lambda: {"parts": parts})
    summary = {"recommendations": [
        {"id": "gpu", "name": "Cheap 24GB GPU", "deal_score": 80.0, "current_cad": 500.0, "recommendation": "Buy", "reasons": []},
        {"id": "box", "name": "Integrated node", "deal_score": 76.0, "current_cad": 700.0, "recommendation": "Buy", "reasons": []},
    ]}
    result = apply_tco_to_summary(summary, scenarios=SCENARIOS)
    by_id = {row["id"]: row for row in result["recommendations"]}
    assert by_id["gpu"]["tco"]["complete_node_acquisition_cad"] == 1350
    assert by_id["box"]["tco"]["complete_node_acquisition_cad"] == 700
    assert by_id["box"]["deal_score"] >= by_id["gpu"]["deal_score"]
