from __future__ import annotations

import json
from pathlib import Path

from lowpower_llm_cluster.intelligence import generate_change_intelligence


def write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_change_intelligence_detects_price_stock_and_benchmark_changes(tmp_path: Path):
    price = tmp_path / "prices.json"
    listing = tmp_path / "listing.json"
    perf = tmp_path / "perf.json"
    watches = tmp_path / "watch.json"
    state = tmp_path / "state.json"
    output = tmp_path / "out.json"

    write(price, {"observations": [
        {"source": "fixture", "source_id": "1", "part_id": "special-amd-bc250-16g", "title": "BC-250", "price": 200, "currency": "CAD", "observed_at": "2026-08-09T00:00:00+00:00"},
        {"source": "fixture", "source_id": "1", "part_id": "special-amd-bc250-16g", "title": "BC-250", "price": 150, "currency": "CAD", "observed_at": "2026-08-10T00:00:00+00:00"}
    ]})
    write(listing, {"events": [
        {"event": "reappeared", "source": "fixture", "source_id": "1", "observed_at": "2026-08-10T00:00:00+00:00", "url": "https://example.test/1"}
    ]})
    base = {"part_id": "special-amd-bc250-16g", "source_type": "community_measured", "source_url": "https://example.test/bench", "model": "Llama 3.2 3B", "quantization": "Q4_K_M", "runtime": "llama.cpp", "runtime_version": "b1", "backend": "Vulkan", "workload": "decode", "metric": "throughput", "unit": "tokens/s", "hardware_configuration": "stock"}
    write(perf, {"records": [
        {**base, "id": "a", "value": 70, "published_on": "2026-08-01"},
        {**base, "id": "b", "value": 84, "published_on": "2026-08-10"}
    ]})
    write(watches, {"watchlists": [{"id": "bc250", "enabled": True, "match": {"part_ids": ["special-amd-bc250-16g"]}, "alerts": {"price_drop_pct": 10, "stock_return": True, "benchmark_change_pct": 10}}]})

    summary = generate_change_intelligence(price_path=price, listing_state_path=listing, performance_path=perf, watchlists_path=watches, state_path=state, output_path=output)
    kinds = {row["type"] for row in summary["alerts"]}
    assert "price_drop" in kinds
    assert "stock_return" in kinds
    assert "benchmark_improvement" in kinds

    second = generate_change_intelligence(price_path=price, listing_state_path=listing, performance_path=perf, watchlists_path=watches, state_path=state, output_path=output)
    assert second["alert_count"] == 0


def test_deal_threshold_alerts_on_first_bargain_and_crossing(tmp_path: Path):
    price = tmp_path / "prices.json"
    listing = tmp_path / "listing.json"
    perf = tmp_path / "perf.json"
    watches = tmp_path / "watch.json"
    state = tmp_path / "state.json"
    output = tmp_path / "out.json"

    write(price, {"observations": [
        {"source": "fixture", "source_id": "a5000-1", "title": "NVIDIA RTX A5000 24GB", "price": 900, "shipping": 0, "currency": "CAD", "observed_at": "2026-08-09T00:00:00+00:00"},
        {"source": "fixture", "source_id": "a5000-1", "title": "NVIDIA RTX A5000 24GB", "price": 700, "shipping": 0, "currency": "CAD", "observed_at": "2026-08-10T00:00:00+00:00"},
        {"source": "fixture", "source_id": "p40-1", "title": "NVIDIA Tesla P40 24GB", "price": 250, "shipping": 20, "currency": "CAD", "observed_at": "2026-08-10T00:00:00+00:00"}
    ]})
    write(listing, {"events": []})
    write(perf, {"records": []})
    write(watches, {"watchlists": [
        {"id": "workstation-24gb", "enabled": True, "match": {"keywords": ["rtx a5000"]}, "alerts": {"max_landed_cad": 800}},
        {"id": "legacy-datacenter-24gb", "enabled": True, "match": {"keywords": ["tesla p40"]}, "alerts": {"max_landed_cad": 350, "deal_severity": "medium"}}
    ]})

    summary = generate_change_intelligence(
        price_path=price,
        listing_state_path=listing,
        performance_path=perf,
        watchlists_path=watches,
        state_path=state,
        output_path=output,
        tax_rate=0.0,
    )
    deals = [row for row in summary["alerts"] if row["type"] == "deal_threshold"]
    assert len(deals) == 2
    assert {row["watchlist"] for row in deals} == {"workstation-24gb", "legacy-datacenter-24gb"}
    a5000 = next(row for row in deals if row["watchlist"] == "workstation-24gb")
    assert a5000["old_landed_cad"] == 900.0
    assert a5000["new_landed_cad"] == 700.0
    assert a5000["threshold_cad"] == 800.0

    second = generate_change_intelligence(
        price_path=price,
        listing_state_path=listing,
        performance_path=perf,
        watchlists_path=watches,
        state_path=state,
        output_path=output,
        tax_rate=0.0,
    )
    assert second["alert_count"] == 0
