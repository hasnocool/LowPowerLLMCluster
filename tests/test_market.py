# tests/test_market.py
from __future__ import annotations

from pathlib import Path

from lowpower_llm_cluster.market import Listing, append_price_observations, configuration_confidence, ingest_performance, landed_cost_cad, price_history


def listing(**overrides):
    values = dict(source="fixture", source_id="1", url="https://example.test/1", title="Example Ryzen 8845HS 32GB", price=500.0, currency="USD", observed_at="2026-08-10T12:00:00+00:00", sku="ABC-32", configuration={"memory_capacity_gb": 32})
    values.update(overrides)
    return Listing(**values)


def test_exact_sku_and_memory_is_high_confidence():
    part = {"id": "p1", "name": "Example Ryzen 8845HS", "sku": "ABC-32", "memory_capacity_gb": 32}
    result = configuration_confidence(part, listing())
    assert result["score"] >= 0.9
    assert result["label"] == "exact"


def test_cpu_theoretical_memory_is_not_used_for_configuration_match():
    part = {"id": "p1", "name": "Example Ryzen 8845HS", "cpu_max_memory_gb": 256}
    result = configuration_confidence(part, listing(configuration={"memory_capacity_gb": 32}))
    assert result["configuration_score"] == 0.5


def test_price_history_deduplicates_observations(tmp_path: Path):
    target = tmp_path / "history.json"
    part = {"id": "p1", "name": "Example Ryzen 8845HS", "sku": "ABC-32", "memory_capacity_gb": 32}
    first = append_price_observations([listing()], [part], target)
    second = append_price_observations([listing()], [part], target)
    assert first == {"added": 1, "total": 1}
    assert second == {"added": 0, "total": 1}
    assert price_history("p1", target)[0]["price"] == 500.0


def test_canadian_landed_cost_is_explicit_math():
    item = listing(shipping=25.0, shipping_currency="USD")
    result = landed_cost_cad(item, {"USD": 1.35, "CAD": 1.0}, tax_rate=0.12, duty_rate=0.0, brokerage_cad=10.0)
    assert result["item_cad"] == 675.0
    assert result["shipping_cad"] == 33.75
    assert result["landed_cad"] == 805.0


def test_performance_ingestion_requires_provenance(tmp_path: Path):
    target = tmp_path / "performance.json"
    record = {"id": "r1", "part_id": "p1", "source_type": "community_measured", "source_url": "https://example.test/bench", "model": "Example-7B-Q4", "runtime": "llama.cpp", "workload": "decode", "metric": "throughput", "value": 10.0, "unit": "tokens/s", "reproducibility": 0.75}
    result = ingest_performance([record], target)
    assert result == {"added": 1, "total": 1}
