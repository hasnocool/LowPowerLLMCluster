from __future__ import annotations

import json
import re
from pathlib import Path

from lowpower_llm_cluster.dashboard import _rows, render_catalog_dashboard


def _part(**overrides):
    part = {
        "id": "node-example",
        "category": "compute_node",
        "name": "Example Mini PC",
        "vendor": "Example",
        "price_min_usd": 180,
        "price_max_usd": 220,
        "price_status": "current_listing",
        "moq": 1,
        "url": "https://example.test/product",
        "source_url": "https://example.test/source",
        "verified_on": "2026-08-12",
        "listing_status": "available",
        "plain_language": "A compact low-power node with useful memory expansion for local-model experiments.",
        "hardware_class": "mini_pc",
        "memory_capacity_gb": 32,
        "memory_config_status": "fixed",
        "power_target_w": 35,
        "power_scope": "board_estimate",
        "risk_level": "low",
        "lifecycle_status": "current",
        "llm_candidate": True,
        "llm_support": "supported",
        "software_maturity": "mainstream_linux",
        "sku_confidence": 0.91,
        "performance_evidence": {
            "source_type": "community_measured",
            "confidence": "medium",
            "source_url": "https://example.test/perf",
            "notes": "Measured by an identifiable community source.",
        },
    }
    part.update(overrides)
    return part


def test_dashboard_view_model_keeps_decision_context() -> None:
    row = _rows([_part(max_memory_gb=64, max_memory_source_url="https://example.test/memory")])[0]
    assert row["price"] == 200
    assert row["memory"] == 32
    assert row["power"] == 35
    assert row["sku_confidence"] == 0.91
    assert row["performance_source"] == "community_measured"
    assert row["plain_language"].startswith("A compact")
    assert row["board_memory_source_url"] == "https://example.test/memory"


def test_dashboard_is_ground_up_information_hierarchy(tmp_path: Path) -> None:
    output = render_catalog_dashboard([_part()], tmp_path / "dashboard.html")
    html = output.read_text(encoding="utf-8")
    assert "Catalog overview" in html
    assert "Browse hardware" in html
    assert "Compare hardware" in html
    assert "Product details" in html
    assert "Data coverage" in html
    assert "Power and deployment" in html
    assert "Evidence and provenance" in html
    assert "lpllm-dashboard-state-v2" in html
    assert "Ctrl K" in html
    assert "aria-label=\"Catalog filters\"" in html


def test_embedded_catalog_json_cannot_close_its_script_tag(tmp_path: Path) -> None:
    attack = "Node </script><script>alert('x')</script>"
    output = render_catalog_dashboard([_part(name=attack)], tmp_path / "dashboard.html")
    html = output.read_text(encoding="utf-8")
    assert "</script><script>alert('x')</script>" not in html
    match = re.search(r'<script id="catalog-data" type="application/json">(.*?)</script>', html, re.DOTALL)
    assert match is not None
    payload = json.loads(match.group(1))
    assert payload[0]["name"] == attack
