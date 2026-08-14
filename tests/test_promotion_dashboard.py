from __future__ import annotations

import json
from pathlib import Path

from lowpower_llm_cluster.canonical_promotion import canonical_part
from lowpower_llm_cluster.live_discoveries import LIVE_DISCOVERIES_HTML
from lowpower_llm_cluster.promotion_state import build_promotion_snapshot, filter_promotion_items, project_promotion_records


def record(source_id: str, *, observed_at: str, title: str | None = None) -> dict:
    return {
        "source": "vendor", "source_id": source_id,
        "listing_url": f"https://vendor.example/products/{source_id}",
        "title": title or f"AI accelerator {source_id}", "manufacturer": "Example Vendor",
        "sku": source_id, "mpn": source_id, "price": 99.0, "currency": "USD", "in_stock": True,
        "observed_at": observed_at, "source_confidence": 0.95, "sku_confidence": 0.95,
        "raw_attributes": {"discovery_kind": "verified_manufacturer_product"},
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(payload), encoding="utf-8")


def test_snapshot_exposes_all_four_promotion_states(tmp_path: Path) -> None:
    canonical = record("canonical", observed_at="2026-08-13T20:00:00Z")
    held = record("held", observed_at="2026-08-13T20:00:00Z"); held["manufacturer"] = ""
    ready = record("ready", observed_at="2026-08-13T20:00:00Z")
    discovered = record("new", observed_at="2026-08-13T20:10:00Z")
    discovery = tmp_path / "discovery.json"; report = tmp_path / "promotion.json"; catalog = tmp_path / "catalog.json"
    write_json(discovery, {"observations": [canonical, held, ready, discovered]})
    write_json(report, {"generated_at": "2026-08-13T20:05:00Z", "held": [{"source": "vendor", "source_id": "held", "reasons": ["missing_manufacturer"]}]})
    write_json(catalog, {"parts": [canonical_part(canonical)]})
    snapshot = build_promotion_snapshot(discovery_path=discovery, report_path=report, catalog_path=catalog)
    by_id = {item["source_id"]: item for item in snapshot["items"]}
    assert by_id["canonical"]["promotion_state"] == "canonical"
    assert by_id["held"]["promotion_state"] == "held"
    assert by_id["held"]["promotion_reasons"] == ["missing_manufacturer"]
    assert by_id["ready"]["promotion_state"] == "promotion_ready"
    assert by_id["new"]["promotion_state"] == "discovered"
    assert snapshot["counts"] == {"discovered": 1, "held": 1, "promotion_ready": 1, "canonical": 1}


def test_active_projection_does_not_count_stale_promotion_records() -> None:
    current = record("current", observed_at="2026-08-13T20:00:00Z")
    stale = record("stale", observed_at="2026-08-13T20:00:00Z")
    catalog = {"parts": [canonical_part(stale)]}
    report = {"generated_at": "2026-08-13T20:05:00Z", "held": []}
    snapshot = project_promotion_records([current], report=report, catalog=catalog)
    assert snapshot["total"] == 1
    assert snapshot["counts"]["promotion_ready"] == 1
    assert snapshot["counts"]["canonical"] == 0


def test_promotion_filters_support_state_reason_source_and_text() -> None:
    items = [
        {"source": "a", "source_id": "1", "title": "Hailo accelerator", "promotion_state": "held", "promotion_reasons": ["missing_manufacturer"]},
        {"source": "b", "source_id": "2", "title": "GPU board", "promotion_state": "canonical", "promotion_reasons": []},
    ]
    assert len(filter_promotion_items(items, state="held")) == 1
    assert len(filter_promotion_items(items, reason="missing_manufacturer")) == 1
    assert len(filter_promotion_items(items, source="b")) == 1
    assert len(filter_promotion_items(items, query="hailo")) == 1


def test_live_page_is_a_promotion_review_surface() -> None:
    assert "Discovery → Held → Promotion Ready → Canonical" in LIVE_DISCOVERIES_HTML
    assert "/api/promotion-state" in LIVE_DISCOVERIES_HTML
    assert "All hold reasons" in LIVE_DISCOVERIES_HTML
