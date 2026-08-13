# tests/test_pricing_performance_reports.py
from __future__ import annotations

import pytest

from lowpower_llm_cluster.estimates import model_fit_preset
from lowpower_llm_cluster.performance import PerformanceRecord, confidence_aware_range, separate_workload_records
from lowpower_llm_cluster.pricing import FxTable, estimate_canada_landed_cost
from lowpower_llm_cluster.reports import named_reports, published_power_boundary


def test_cad_landed_cost_uses_explicit_fx_and_scope() -> None:
    fx = FxTable(target_currency="CAD", rates={"USD": 1.35}, as_of="fixture")
    estimate = estimate_canada_landed_cost(item_price=100, source_currency="USD", fx=fx, province="BC", shipping=10, duty_rate=0.05, brokerage_cad=5)
    assert estimate.item_cad == 135.00
    assert estimate.shipping_cad == 13.50
    assert estimate.duty_cad == 6.75
    assert estimate.total_cad > 160


def test_performance_range_requires_independent_compatible_measured_sources() -> None:
    base = dict(hardware_id="node", source_type="community_measured", model="model", runtime="llama.cpp", runtime_version="1", workload_class="llm_decode", metric_name="tokens_per_second", unit="tok/s", quantization="Q4", context_tokens=2048)
    one = PerformanceRecord(source_url="https://a.example/result", source_name="a", value=10, **base)
    assert confidence_aware_range([one]) is None
    two = PerformanceRecord(source_url="https://b.example/result", source_name="b", value=12, **base)
    result = confidence_aware_range([one, two])
    assert result is not None
    assert result["low"] == 10
    assert result["high"] == 12
    assert result["confidence"] == "medium"
    specialist = PerformanceRecord(source_url="https://c.example/result", source_name="c", value=30, **{**base, "workload_class": "vision", "metric_name": "fps", "unit": "fps"})
    buckets = separate_workload_records([one, specialist])
    assert buckets["llm"] == [one]
    assert buckets["specialist"] == [specialist]
    with pytest.raises(ValueError):
        confidence_aware_range([one, specialist])


def test_model_preset_and_power_boundaries_do_not_turn_tdp_into_node_watts() -> None:
    part = {"id": "p", "memory_capacity_gb": 16, "memory_config_status": "fixed", "default_tdp_w": 45}
    fit = model_fit_preset(part, "14b-q4")
    assert fit["status"] == "reasonable_capacity_candidate"
    power, scope = published_power_boundary(part)
    assert power == 45
    assert scope == "processor_tdp_not_complete_node"


def test_named_reports_cover_requested_views() -> None:
    parts = [
        {"id": "cheap", "name": "Cheap", "category": "compute_node", "llm_candidate": True, "price_min_usd": 90, "price_max_usd": 90, "memory_capacity_gb": 16, "memory_config_status": "fixed", "power_target_w": 15, "power_scope": "board_estimate", "software_maturity": "mainstream_linux", "risk_level": "low", "listing_status": "available", "lifecycle_status": "current"},
        {"id": "memory", "name": "Memory", "category": "compute_node", "llm_candidate": True, "price_min_usd": 450, "price_max_usd": 450, "memory_capacity_gb": 64, "memory_config_status": "fixed", "power_target_w": 30, "software_maturity": "mainstream_linux", "risk_level": "low", "listing_status": "available", "lifecycle_status": "current"},
    ]
    reports = named_reports(parts)
    assert "best_under_100" in reports and reports["best_under_100"][0]["id"] == "cheap"
    assert reports["high_memory_bargains"][0]["id"] == "memory"
    assert reports["low_power_nodes"][0]["id"] == "cheap"
