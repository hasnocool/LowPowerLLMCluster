from __future__ import annotations

from lowpower_llm_cluster.power_evidence import add_power_observation, aggregate_power_observations, hardware_power_identity, observation_match_level
from lowpower_llm_cluster import power_model


def _apple():
    return {
        "id": "m1max",
        "name": "MacBook Pro M1 Max",
        "category": "apple_silicon_system",
        "configuration": {"apple_a_number": "A2485", "model_identifier": "MacBookPro18,2", "soc": "Apple M1 Max", "memory_capacity_gb": 64, "storage_gb": 2000},
    }


def _payload():
    return {
        "schema_version": 1,
        "observations": [
            {"id": "m1-a", "source_type": "community_measured", "identity": {"exact_id": "a2485", "apple_model_identifier":"macbookpro18,2", "model": "apple m1 max", "category": "apple_silicon_system", "memory_gb": 64, "storage_gb": 2000}, "idle_w": 5.0, "load_w": 52.0},
            {"id": "m1-b", "source_type": "vendor_measured", "identity": {"exact_id": "a2485", "apple_model_identifier":"macbookpro18,2", "model": "apple m1 max", "category": "apple_silicon_system", "memory_gb": 64, "storage_gb": 2000}, "idle_w": 6.0, "load_w": 48.0},
            {"id": "cat", "source_type": "derived_estimate", "identity": {"category": "apple_silicon_system"}, "idle_w": 8.0, "load_w": 45.0},
        ],
    }


def test_exact_configuration_evidence_beats_category():
    aggregate = aggregate_power_observations(_apple(), _payload())
    assert aggregate is not None
    assert aggregate["match_level"] > 40
    assert aggregate["sample_count"] == 2
    assert aggregate["load_w"] == 50.0
    assert aggregate["load_p25_w"] == 49.0
    assert aggregate["load_p75_w"] == 51.0
    assert aggregate["match_basis"].startswith("hardware_specific:")


def test_configuration_conflict_blocks_exact_match():
    row = _payload()["observations"][0]
    mismatched = _apple(); mismatched["configuration"]["memory_capacity_gb"] = 32
    level, reason = observation_match_level(mismatched, row)
    assert level == 0
    assert reason == "configuration_conflict:memory_gb"


def test_ssd_controller_and_nand_make_narrow_identity():
    part={"name":"Example NVMe 1TB","category":"storage","configuration":{"storage_gb":1000,"ssd_controller":"Phison E18","nand_type":"Micron 176L TLC"}}
    identity=hardware_power_identity(part)
    assert identity["storage_controller"] == "phison e18"
    assert identity["nand_type"] == "micron 176l tlc"
    row={"identity":{"storage_controller":"phison e18","nand_type":"different nand","category":"storage"},"load_w":6}
    assert observation_match_level(part,row)[0] == 0


def test_gpu_board_revision_and_host_context_are_conflict_dimensions():
    part={"name":"RTX 3090","category":"gpu_accelerator","mpn":"900-1G136-2510-000","configuration":{"board_revision":"B1","host_cpu":"Ryzen 5 5600","host_motherboard":"B550-A PRO","host_ram_gb":32}}
    identity=hardware_power_identity(part)
    assert identity["gpu_board_revision"] == "b1"
    row={"identity":{**identity,"host_cpu":"core i5 12400"},"load_w":430}
    level,reason=observation_match_level(part,row)
    assert level == 0 and reason == "configuration_conflict:host_cpu"


def test_ram_topology_is_part_of_identity():
    part={"name":"32GB DDR4 2x16GB dual-channel","category":"memory","memory_capacity_gb":32,"configuration":{"memory_type":"DDR4"}}
    identity=hardware_power_identity(part)
    assert identity["ram_topology"]["module_count"] == 2
    assert identity["ram_topology"]["module_capacity_gb"] == 16
    assert identity["ram_topology"]["channels"] == 2


def test_mobile_soc_and_device_sku_are_preserved():
    part={"name":"Phone","category":"mobile_phone","sku":"SM-S948W","configuration":{"device_model":"Galaxy S26 Ultra","soc":"Snapdragon 8 Elite Gen 5","soc_variant":"for Galaxy"}}
    identity=hardware_power_identity(part)
    assert identity["device_sku"] == "sm s948w"
    assert identity["mobile_soc"] == "snapdragon 8 elite gen 5"
    assert identity["mobile_soc_variant"] == "for galaxy"


def test_add_observation_is_append_only_by_id():
    payload = {"schema_version": 1, "observations": []}
    row = {"id": "x", "source_type": "measured_local", "identity": {"category": "storage"}, "load_w": 5}
    once = add_power_observation(payload, row)
    twice = add_power_observation(once, row)
    assert len(once["observations"]) == 1
    assert len(twice["observations"]) == 1


def test_power_model_uses_exact_evidence_before_category(monkeypatch):
    monkeypatch.setattr(power_model, "aggregate_power_observations", lambda part: aggregate_power_observations(part, _payload()))
    result = power_model.estimate_device_power(_apple())
    assert result["basis"] == "power_evidence_distribution"
    assert result["load_w"] == 50.0
    assert result["distribution"]["match_basis"].startswith("hardware_specific:")


def test_direct_measurement_still_beats_learned_distribution(monkeypatch):
    monkeypatch.setattr(power_model, "aggregate_power_observations", lambda part: aggregate_power_observations(part, _payload()))
    part = _apple(); part["measured_idle_w"] = 4; part["measured_load_w"] = 41
    result = power_model.estimate_device_power(part)
    assert result["basis"] == "measured_power"
    assert result["load_w"] == 41
