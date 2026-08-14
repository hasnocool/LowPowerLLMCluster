from __future__ import annotations

import json
from pathlib import Path

from lowpower_llm_cluster.canonical_promotion import evaluate, promote


def _record(**overrides):
    value = {
        "source":"manufacturer-pages", "source_id":"ABC-123", "listing_url":"https://vendor.example/products/abc-123",
        "title":"Example AI Mini PC", "manufacturer":"Example Vendor", "sku":"ABC-123", "mpn":"ABC-123",
        "price":499.0, "currency":"USD", "source_confidence":0.95, "sku_confidence":0.92,
        "in_stock":True, "observed_at":"2026-08-14T00:00:00+00:00", "form_factor":"mini_pc",
        "raw_attributes":{"cpu":"Example CPU", "memory_capacity_gb":32},
    }
    value.update(overrides); return value


def test_verified_product_promotes_and_is_idempotent(tmp_path: Path) -> None:
    catalog = tmp_path / "auto.json"; report = tmp_path / "report.json"
    first = promote([_record()], catalog_path=catalog, report_path=report)
    second = promote([_record(price=479.0)], catalog_path=catalog, report_path=report)
    payload = json.loads(catalog.read_text())
    assert first["promoted_count"] == 1
    assert second["updated_count"] == 1
    assert len(payload["parts"]) == 1
    assert payload["parts"][0]["price_min_usd"] == 479.0


def test_announcements_and_low_confidence_records_are_held() -> None:
    announcement = _record(raw_attributes={"discovery_kind":"announcement"})
    low = _record(source_confidence=0.4)
    assert "announcement_not_product" in evaluate(announcement)
    assert "source_confidence_below_threshold" in evaluate(low)
