from __future__ import annotations

from lowpower_llm_cluster.tco import apply_tco_to_summary, complete_node_power, deployment_requirements, evaluate_tco


SCENARIOS = {
    "component_costs_cad": {
        "host_platform": 300,
        "host_ram_32gb": 100,
        "storage_1tb": 80,
        "psu_750w": 120,
        "pcie_adapter": 40,
        "cooling": 60,
        "chassis_misc": 80,
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


def test_gpu_requires_complete_host_stack():
    gpu = {"category": "gpu_accelerator", "host_mode": "pcie_add_in_card", "memory_config_status": "fixed"}
    req = deployment_requirements(gpu)
    assert req["profile"] == "host_attached_pcie"
    assert "host_platform" in req["components"]
    assert "psu_750w" in req["components"]
    assert "pcie_adapter" in req["components"]


def test_500_gpu_does_not_have_500_complete_node_cost():
    gpu = {"category": "gpu_accelerator", "host_mode": "pcie_add_in_card", "memory_config_status": "fixed", "power_target_w": 350, "power_scope": "accelerator_board_power_reference"}
    tco = evaluate_tco(gpu, 500, scenarios=SCENARIOS)
    assert tco["infrastructure"]["total_cad"] == 780
    assert tco["complete_node_acquisition_cad"] == 1280
    assert tco["total_cost_of_ownership_cad"] > 1280


def test_gpu_board_power_is_not_relabeled_wall_power():
    gpu = {"category": "gpu_accelerator", "power_target_w": 350, "power_scope": "accelerator_board_power_reference"}
    power = complete_node_power(gpu, SCENARIOS)
    assert power["load_w"] > 350
    assert power["confidence"] == "low"
    assert "estimated_complete_node" in power["basis"]


def test_complete_system_has_no_host_infrastructure_assumption():
    complete = {"category": "compute_node", "hardware_class": "mini_pc", "memory_config_status": "included", "power_target_w": 65, "power_scope": "complete_node_input"}
    tco = evaluate_tco(complete, 700, scenarios=SCENARIOS)
    assert tco["infrastructure"]["total_cad"] == 0
    assert tco["complete_node_acquisition_cad"] == 700


def test_tco_can_demote_expensive_infrastructure_candidate(monkeypatch):
    parts = [
        {"id": "gpu", "category": "gpu_accelerator", "host_mode": "pcie_add_in_card", "memory_config_status": "fixed", "power_target_w": 350, "power_scope": "accelerator_board_power_reference"},
        {"id": "box", "category": "compute_node", "memory_config_status": "included", "power_target_w": 65, "power_scope": "complete_node_input"},
    ]
    monkeypatch.setattr("lowpower_llm_cluster.tco.load_catalog", lambda: {"parts": parts})
    summary = {"recommendations": [
        {"id": "gpu", "name": "Cheap 24GB GPU", "deal_score": 80.0, "current_cad": 500.0, "recommendation": "Buy", "reasons": []},
        {"id": "box", "name": "Integrated node", "deal_score": 76.0, "current_cad": 700.0, "recommendation": "Buy", "reasons": []},
    ]}
    result = apply_tco_to_summary(summary, scenarios=SCENARIOS)
    by_id = {row["id"]: row for row in result["recommendations"]}
    assert by_id["gpu"]["tco"]["complete_node_acquisition_cad"] == 1280
    assert by_id["box"]["tco"]["complete_node_acquisition_cad"] == 700
    assert by_id["box"]["deal_score"] >= by_id["gpu"]["deal_score"]
