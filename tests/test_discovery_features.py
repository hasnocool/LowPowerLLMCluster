# tests/test_discovery_features.py
from __future__ import annotations

import asyncio
from pathlib import Path

from lowpower_llm_cluster.discovery import DiscoveryPipeline, ProductObservation, StaticSourceAdapter
from lowpower_llm_cluster.history import CatalogHistory
from lowpower_llm_cluster.normalization import normalize_observation, seller_confidence, sku_confidence


def test_discovery_pipeline_deduplicates_without_blocking() -> None:
    first = ProductObservation(source="fixture", source_id="abc", listing_url="https://example.com/p/abc", title="Mini PC", price=100)
    newer = ProductObservation(source="fixture", source_id="abc", listing_url="https://example.com/p/abc", title="Mini PC exact", price=95)
    result = asyncio.run(DiscoveryPipeline([StaticSourceAdapter("one", [first]), StaticSourceAdapter("two", [newer])]).run())
    assert len(result.observations) == 1
    assert result.observations[0].price == 95
    assert not result.errors


def test_normalization_scores_exact_sku_and_board_memory() -> None:
    observation = ProductObservation(
        source="vendor", source_id="sku-1", listing_url="https://vendor.example/item", title="Example Mini PC 32GB",
        price=300, seller="Vendor", seller_rating=4.9, seller_review_count=500, seller_verified=True,
        manufacturer="Example", sku="SKU-1", mpn="MPN-1",
        attributes={"cpu": "Ryzen", "memory_capacity_gb": 32, "storage": "1TB", "form_factor": "mini pc", "board_max_memory_gb": 96, "board_max_memory_source_url": "https://vendor.example/spec", "dc_input_v": 19},
    )
    normalized = normalize_observation(observation, source_trust=0.9)
    assert normalized["seller_confidence"] > 0.8
    assert normalized["sku_confidence"] > 0.8
    assert normalized["board_memory_verified"] is True
    assert normalized["board_max_memory_gb"] == 96
    assert normalized["form_factor"] == "mini_pc"
    assert seller_confidence(observation, source_trust=0.9) > 0.8
    assert sku_confidence(observation) > 0.8


def test_history_detects_price_change_and_disappearance(tmp_path: Path) -> None:
    history = CatalogHistory(tmp_path / "history.sqlite3")
    first = ProductObservation(source="fixture", source_id="x", listing_url="https://example.com/x", title="X", price=100, in_stock=True)
    second = ProductObservation(source="fixture", source_id="x", listing_url="https://example.com/x", title="X", price=90, in_stock=True)

    async def scenario() -> None:
        await history.initialize()
        _, changes = await history.record_refresh([first], source_names=["fixture"])
        assert changes == ()
        _, changes = await history.record_refresh([second], source_names=["fixture"])
        assert any(change.change_type == "price_changed" and change.previous == 100 and change.current == 90 for change in changes)
        _, changes = await history.record_refresh([], source_names=["fixture"], disappearance_after_runs=2)
        assert not any(change.change_type == "disappeared" for change in changes)
        _, changes = await history.record_refresh([], source_names=["fixture"], disappearance_after_runs=2)
        assert any(change.change_type == "disappeared" for change in changes)
        rows = await history.price_history("fixture", "x")
        assert [row["price"] for row in rows[:2]] == [90, 100]

    asyncio.run(scenario())


def test_jsonld_product_adapter_extracts_exact_product() -> None:
    from lowpower_llm_cluster.discovery import JsonLdProductAdapter

    class FakeClient:
        async def get_text(self, url: str) -> str:
            assert url == "https://vendor.example/product"
            return '''<html><head><script type="application/ld+json">{
              "@context":"https://schema.org", "@type":"Product", "name":"Example 96GB Mini PC",
              "sku":"EX-96", "mpn":"MPN-96", "brand":{"@type":"Brand","name":"Example"},
              "offers":{"@type":"Offer","price":"499.00","priceCurrency":"USD","availability":"https://schema.org/InStock","url":"https://vendor.example/product"}
            }</script></head></html>'''

    adapter = JsonLdProductAdapter("vendor", ["https://vendor.example/product"], FakeClient())  # type: ignore[arg-type]
    records = asyncio.run(adapter.discover())
    assert len(records) == 1
    assert records[0].sku == "EX-96"
    assert records[0].manufacturer == "Example"
    assert records[0].price == 499.0
    assert records[0].in_stock is True
