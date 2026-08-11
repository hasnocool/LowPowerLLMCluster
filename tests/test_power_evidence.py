from __future__ import annotations

from lowpower_llm_cluster.power_evidence import add_power_observation, aggregate_power_observations, observation_match_level
from lowpower_llm_cluster import power_model


def _apple():
    return {
        "id": "m1max",
        "name": "MacBook Pro M1 Max",
        "category": "apple_silicon_system",
        "configuration": {"apple_a_number": "A2485", "soc": "Apple M1 Max", "memory_capacity_gb": 64, "storage_gb": 2000},
    }


def _payload():
    return {
        "schema_version": 1,
        "observations": [
            {"id": "m1-a", "source_type": "community_measured", "identity": {"exact_id": "a2485", "model": "apple m1 max", "category": "apple_silicon_system", "memory_gb": 64, "storage_gb": 2000}, "idle_w": 5.0, "load_w": 52.0},
            {"id": "m1-b", "source_type": "vendor_measured", "identity": {"exact_id": "a2485", "model": "apple m1 max", "category": "apple_silicon_system", "memory_gb": 64, "storage_gb": 2000}, "idle_w": 6.0, "load_w": 48.0},
            {"id": "cat", "source_type": "derived_estimate", "identity": {"category": "apple_silicon_system"}, "idle_w": 8.0, "load_w": 45.0},
        ],
    }


def test_exact_configuration_evidence_beats_category():
    aggregate = aggregate_power_observations(_apple(), _payload())
    assert aggregate is not None
    assert aggregate["match_level"] == 4
    assert aggregate["sample_count"] == 2
    assert aggregate["load_w"] == 50.0
    assert aggregate["load_p25_w"] == 49.0
    assert aggregate["load_p75_w"] == 51.0


def test_configuration_conflict_blocks_exact_match():
    row = _payload()["observations"][0]
    mismatched = _apple(); mismatched["configuration"]["memory_capacity_gb"] = 32
    level, reason = observation_match_level(mismatched, row)
    assert level == 0
    assert reason == "configuration_conflict"


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
    assert result["distribution"]["match_basis"] == "exact_sku_or_model_identifier"


def test_direct_measurement_still_beats_learned_distribution(monkeypatch):
    monkeypatch.setattr(power_model, "aggregate_power_observations", lambda part: aggregate_power_observations(part, _payload()))
    part = _apple(); part["measured_idle_w"] = 4; part["measured_load_w"] = 41
    result = power_model.estimate_device_power(part)
    assert result["basis"] == "measured_power"
    assert result["load_w"] == 41
