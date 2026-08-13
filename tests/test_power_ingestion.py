from __future__ import annotations

import json

from lowpower_llm_cluster.power_evidence import aggregate_power_observations
from lowpower_llm_cluster.power_ingestion import benchmark_power_observations, catalog_power_observations, refresh_power_evidence


CATALOG = {
    "parts": [
        {
            "id": "gpu",
            "name": "RTX Test Exact Board",
            "category": "gpu_accelerator",
            "accelerator_family": "RTX Test",
            "power_target_w": 300,
            "power_scope": "accelerator_board_power_reference",
            "source_url": "https://vendor.example/gpu",
        },
        {
            "id": "jetson",
            "name": "Jetson Test",
            "category": "dev_board",
            "hardware_class": "Jetson Test",
        },
    ]
}


def test_catalog_explicit_power_becomes_reusable_manufacturer_observation():
    rows = catalog_power_observations(CATALOG)
    assert len(rows) == 1
    row = rows[0]
    assert row["part_id"] == "gpu"
    assert row["load_w"] == 300
    assert row["source_type"] == "manufacturer_spec"
    assert row["eligible_for_device_power"] is True


def test_exact_signature_tokens_per_second_divided_by_tokens_per_joule_retains_scope():
    performance = {
        "records": [
            {
                "id": "speed", "part_id": "jetson", "source_type": "community_measured",
                "model": "Model A", "quantization": "Q4", "runtime": "llama.cpp", "runtime_version": "1",
                "backend": "CUDA", "workload": "decode", "generation_length": 64,
                "hardware_configuration": "Jetson Test; same config", "metric": "throughput", "value": 100, "unit": "tokens/s",
            },
            {
                "id": "eff", "part_id": "jetson", "source_type": "community_measured",
                "model": "Model A", "quantization": "Q4", "runtime": "llama.cpp", "runtime_version": "1",
                "backend": "CUDA", "workload": "decode", "generation_length": 64,
                "hardware_configuration": "Jetson Test; same config", "metric": "energy_efficiency", "value": 20, "unit": "tokens/J",
                "power_scope": "internal VDD_CPU_GPU rail; not wall input",
            },
        ]
    }
    rows = benchmark_power_observations(performance, CATALOG)
    derived = next(row for row in rows if row["id"].startswith("benchmark-derived:"))
    assert derived["load_w"] == 5.0
    assert derived["eligible_for_device_power"] is False
    assert "throughput_divided_by_tokens_per_joule" in derived["evidence_basis"]


def test_mismatched_benchmark_signatures_are_not_combined():
    performance = {
        "records": [
            {"id":"speed","part_id":"jetson","model":"A","quantization":"Q4","runtime":"x","runtime_version":"1","backend":"CPU","workload":"decode","metric":"throughput","value":100,"unit":"tokens/s"},
            {"id":"eff","part_id":"jetson","model":"B","quantization":"Q4","runtime":"x","runtime_version":"1","backend":"CPU","workload":"decode","metric":"energy_efficiency","value":20,"unit":"tokens/J","power_scope":"complete_node_input"},
        ]
    }
    assert not any(row["id"].startswith("benchmark-derived:") for row in benchmark_power_observations(performance, CATALOG))


def test_research_only_internal_rail_observation_cannot_train_device_power():
    part = CATALOG["parts"][1]
    payload = {"schema_version":1,"observations":[{
        "id":"rail","source_type":"community_measured","identity":{"model":"jetson test","family":"jetson test","category":"dev_board"},
        "load_w":5.0,"power_scope":"internal rail","eligible_for_device_power":False,
    }]}
    assert aggregate_power_observations(part, payload) is None


def test_refresh_is_append_only_and_reports_eligible_vs_research(tmp_path):
    performance = {
        "records": [
            {"id":"speed","part_id":"jetson","model":"A","quantization":"Q4","runtime":"x","runtime_version":"1","backend":"CPU","workload":"decode","metric":"throughput","value":100,"unit":"tokens/s","hardware_configuration":"same"},
            {"id":"eff","part_id":"jetson","model":"A","quantization":"Q4","runtime":"x","runtime_version":"1","backend":"CPU","workload":"decode","metric":"energy_efficiency","value":20,"unit":"tokens/J","hardware_configuration":"same","power_scope":"internal rail"},
        ]
    }
    perf_path = tmp_path / "performance.json"; perf_path.write_text(json.dumps(performance), encoding="utf-8")
    evidence_path = tmp_path / "evidence.json"
    spec_path = tmp_path / "spec-evidence.json"; spec_path.write_text(json.dumps({"records": []}), encoding="utf-8")
    sourced_path = tmp_path / "power-measurements.json"; sourced_path.write_text(json.dumps({"records": []}), encoding="utf-8")
    first = refresh_power_evidence(performance_path=perf_path, evidence_path=evidence_path, spec_evidence_path=spec_path, sourced_measurements_path=sourced_path, catalog=CATALOG)
    second = refresh_power_evidence(performance_path=perf_path, evidence_path=evidence_path, spec_evidence_path=spec_path, sourced_measurements_path=sourced_path, catalog=CATALOG)
    assert first["added"] == 2
    assert first["eligible_device_observations"] == 1
    assert first["research_only_observations"] == 1
    assert second["added"] == 0
