# tests/test_android_catalog.py
from __future__ import annotations

import json
from pathlib import Path

from lowpower_llm_cluster.mobile_platform import mobile_runtime_profile, model_fit_memory_budget


ROOT = Path(__file__).resolve().parents[1]
MOBILE_CATALOG = ROOT / "data" / "catalog" / "mobile-devices.json"
EXPECTED = {
    "mobile-oneplus-15-16g-512g": 16,
    "mobile-xiaomi-15-ultra-16g": 16,
    "mobile-redmagic-11-pro-24g-1t": 24,
    "mobile-asus-rog-phone-9-pro-edition-24g": 24,
    "tablet-samsung-galaxy-tab-s11-ultra-16g-1t": 16,
}


def _parts() -> dict[str, dict]:
    payload = json.loads(MOBILE_CATALOG.read_text(encoding="utf-8"))
    return {part["id"]: part for part in payload["parts"]}


def test_high_ram_android_entries_are_exact_fixed_memory_configs():
    parts = _parts()
    for part_id, capacity in EXPECTED.items():
        part = parts[part_id]
        assert part["memory_capacity_gb"] == capacity
        assert part["max_memory_gb"] == capacity
        assert part["memory_config_status"] == "fixed"
        assert part["price_min_usd"] is None
        assert part["price_max_usd"] is None
        assert "live_market" in part["price_status"] or "live_market" in part["listing_status"]
        assert part["source_url"].startswith("https://")


def test_high_ram_android_entries_keep_mobile_runtime_constraints():
    parts = _parts()
    for part_id in EXPECTED:
        part = parts[part_id]
        profile = mobile_runtime_profile(part)
        assert profile["host_class"] == "mobile_endpoint"
        assert profile["local_cli"] is True
        assert profile["persistent_daemon"] is False
        assert profile["headless_service"] is False
        budget = model_fit_memory_budget(part)
        assert budget["known"] is True
        assert budget["usable_gb"] < float(part["memory_capacity_gb"])
        assert budget["performance_claim"] is False


def test_catalog_does_not_relabel_charging_specs_as_inference_power():
    parts = _parts()
    for part_id in EXPECTED:
        part = parts[part_id]
        assert "power_target_w" not in part
        assert "power_scope" not in part
        assert "tokens/s" not in str(part.get("source_notes", "")).casefold()
