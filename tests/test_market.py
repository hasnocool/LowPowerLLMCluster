# tests/test_market.py
from __future__ import annotations

from pathlib import Path

from lowpower_llm_cluster.market import (
    Listing,
    aggregate_compatible_performance,
    append_price_observations,
    configuration_confidence,
    ingest_performance,
    landed_cost_cad,
    price_history,
    seller_confidence,
    update_listing_presence,
)


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
    row = price_history("p1", target)[0]
    assert row["price"] == 500.0
    assert "seller_confidence" in row


def test_canadian_landed_cost_is_explicit_math():
    item = listing(shipping=25.0, shipping_currency="USD")
    result = landed_cost_cad(item, {"USD": 1.35, "CAD": 1.0}, tax_rate=0.12, duty_rate=0.0, brokerage_cad=10.0)
    assert result["item_cad"] == 675.0
    assert result["shipping_cad"] == 33.75
    assert result["landed_cad"] == 805.0


def test_marketplace_seller_confidence_uses_reputation_separately():
    weak = seller_confidence(listing(source_kind="structured_marketplace", seller_metrics={"feedback_percentage": 80, "feedback_score": 10}))
    strong = seller_confidence(listing(source_kind="structured_marketplace", seller_metrics={"feedback_percentage": 99.8, "feedback_score": 50000, "top_rated": True}))
    assert strong["score"] > weak["score"]
    assert strong["label"] in {"medium", "high", "exact"}
    manufacturer = seller_confidence(listing(source_kind="manufacturer", seller_metrics={"verified_source": True}))
    assert manufacturer["score"] > strong["score"]


def test_presence_tracks_disappearance_and_reappearance_in_same_scope(tmp_path: Path):
    target = tmp_path / "state.json"
    first = update_listing_presence([listing()], ["fixture"], ["8845HS"], target, observed_at="2026-08-10T10:00:00+00:00")
    missing = update_listing_presence([], ["fixture"], ["8845HS"], target, observed_at="2026-08-10T11:00:00+00:00")
    back = update_listing_presence([listing()], ["fixture"], ["8845HS"], target, observed_at="2026-08-10T12:00:00+00:00")
    assert first["discovered"] == 1
    assert missing["disappeared"] == 1
    assert back["reappeared"] == 1


def test_different_query_scope_does_not_create_false_disappearance(tmp_path: Path):
    target = tmp_path / "state.json"
    update_listing_presence([listing()], ["fixture"], ["8845HS"], target, observed_at="2026-08-10T10:00:00+00:00")
    other = update_listing_presence([], ["fixture"], ["BC-250"], target, observed_at="2026-08-10T11:00:00+00:00")
    assert other["disappeared"] == 0


def test_performance_ingestion_requires_provenance(tmp_path: Path):
    target = tmp_path / "performance.json"
    record = {"id": "r1", "part_id": "p1", "source_type": "community_measured", "source_url": "https://example.test/bench", "model": "Example-7B-Q4", "runtime": "llama.cpp", "workload": "decode", "metric": "throughput", "value": 10.0, "unit": "tokens/s", "reproducibility": 0.75}
    result = ingest_performance([record], target)
    assert result == {"added": 1, "total": 1}


def test_compatible_performance_is_not_mixed_across_quantizations(tmp_path: Path):
    target = tmp_path / "performance.json"
    common = {"part_id": "p1", "source_type": "community_measured", "runtime": "llama.cpp", "workload": "decode", "metric": "throughput", "unit": "tokens/s", "reproducibility": 1.0}
    records = [
        {**common, "id": "r1", "source_url": "https://example.test/a", "model": "Example-7B", "quantization": "Q4_K_M", "value": 10.0},
        {**common, "id": "r2", "source_url": "https://example.test/b", "model": "Example-7B", "quantization": "Q4_K_M", "value": 12.0},
        {**common, "id": "r3", "source_url": "https://example.test/c", "model": "Example-7B", "quantization": "Q8_0", "value": 7.0},
    ]
    ingest_performance(records, target)
    groups = aggregate_compatible_performance("p1", target)
    assert len(groups) == 2
    assert sorted(group["count"] for group in groups) == [1, 2]
    q4 = next(group for group in groups if group["count"] == 2)
    assert q4["median"] == 11.0
