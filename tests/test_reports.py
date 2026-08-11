from __future__ import annotations

import json
from pathlib import Path

from lowpower_llm_cluster.reports import build_report_rows, named_reports


def write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_reports_prefer_active_live_listing_and_use_cad_fx(tmp_path: Path):
    parts = [{
        "id": "p1", "name": "Example 32GB node", "category": "sbc", "llm_candidate": True,
        "price_min_usd": 200, "price_max_usd": 200, "memory_capacity_gb": 32,
        "memory_config_status": "fixed", "power_target_w": 15, "risk_level": "low", "lifecycle_status": "current",
    }]
    price_path = write(tmp_path / "prices.json", {"observations": [{
        "part_id": "p1", "source": "fixture", "source_id": "a", "observed_at": "2026-08-10T12:00:00Z",
        "price": 100, "currency": "USD", "shipping": 10, "shipping_currency": "USD",
        "configuration_confidence": {"score": 0.9}, "seller_confidence": {"score": 0.8},
    }]})
    state_path = write(tmp_path / "state.json", {"states": {"a": {"source": "fixture", "source_id": "a", "active": True}}})
    fx_path = write(tmp_path / "fx.json", {"rates_to_cad": {"CAD": 1.0, "USD": 1.35}})
    perf_path = write(tmp_path / "perf.json", {"records": []})
    rows = build_report_rows(parts, tax_rate=0.0, price_path=price_path, state_path=state_path, performance_path=perf_path, fx_path=fx_path)
    assert rows[0]["price_cad"] == 148.5
    assert rows[0]["price_basis"] == "live_listing+shipping+tax"
    assert rows[0]["market_confidence"] == 0.87
    assert named_reports(rows)["32gb-plus"][0]["id"] == "p1"


def test_reports_fall_back_to_catalog_price_but_label_it(tmp_path: Path):
    parts = [{
        "id": "p1", "name": "Catalog node", "category": "specialty_board", "llm_candidate": True,
        "price_min_usd": 100, "price_max_usd": 120, "memory_capacity_gb": 16,
        "memory_config_status": "fixed", "power_target_w": 20, "risk_level": "high", "lifecycle_status": "current",
    }]
    price_path = write(tmp_path / "prices.json", {"observations": []})
    state_path = tmp_path / "missing-state.json"
    fx_path = write(tmp_path / "fx.json", {"rates_to_cad": {"CAD": 1.0, "USD": 1.4}})
    perf_path = write(tmp_path / "perf.json", {"records": []})
    rows = build_report_rows(parts, tax_rate=0.0, price_path=price_path, state_path=state_path, performance_path=perf_path, fx_path=fx_path)
    assert rows[0]["price_cad"] == 154.0
    assert rows[0]["price_basis"] == "catalog_midpoint+tax"
    assert rows[0]["live_observation"] is False
    assert named_reports(rows)["weird-bargains"][0]["id"] == "p1"


def test_missing_fx_does_not_invent_cad_price(tmp_path: Path):
    parts = [{
        "id": "p1", "name": "USD node", "category": "sbc", "llm_candidate": True,
        "price_min_usd": 100, "price_max_usd": 100, "memory_capacity_gb": 8,
        "memory_config_status": "fixed", "power_target_w": 10,
    }]
    price_path = write(tmp_path / "prices.json", {"observations": []})
    fx_path = write(tmp_path / "fx.json", {"rates_to_cad": {"CAD": 1.0}})
    perf_path = write(tmp_path / "perf.json", {"records": []})
    rows = build_report_rows(parts, price_path=price_path, state_path=tmp_path / "none.json", performance_path=perf_path, fx_path=fx_path)
    assert rows[0]["price_cad"] is None
    assert rows[0]["price_basis"] == "unpriced"
    assert named_reports(rows)["under-500"] == []
