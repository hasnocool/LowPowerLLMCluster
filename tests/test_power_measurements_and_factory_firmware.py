# tests/test_power_measurements_and_factory_firmware.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lowpower_llm_cluster.factory_firmware import resolve_factory_firmware
from lowpower_llm_cluster.firmware_readiness import boot_readiness_score
from lowpower_llm_cluster.power_measurements import normalize_sourced_power_record, sourced_power_observations


def test_sourced_power_measurement_requires_scope_identity_and_https() -> None:
    row = {
        "id": "exact-node-1",
        "source_type": "community_measured",
        "source_url": "https://example.com/exact-node",
        "power_scope": "complete_node_input",
        "identity": {"gpu_board_mpn": "RTX3090-FE", "host_cpu": "Ryzen 5 5600"},
        "idle_w": 61.0,
        "load_w": 432.0,
    }
    normalized = normalize_sourced_power_record(row)
    assert normalized["eligible_for_device_power"] is True
    assert normalized["identity"]["host_cpu"] == "Ryzen 5 5600"
    with pytest.raises(ValueError):
        normalize_sourced_power_record({**row, "source_url": "http://example.com"})
    with pytest.raises(ValueError):
        normalize_sourced_power_record({**row, "identity": {}})


def test_internal_rail_measurement_is_retained_but_research_only() -> None:
    row = normalize_sourced_power_record({
        "id": "rail-1",
        "source_type": "vendor_measured",
        "source_url": "https://example.com/rail",
        "power_scope": "internal_rail",
        "identity": {"device_sku": "EXACT-1"},
        "load_w": 7.2,
    })
    assert row["eligible_for_device_power"] is False


def test_sourced_power_feed_loads_records(tmp_path: Path) -> None:
    path = tmp_path / "power.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "records": [{
            "id": "node-a",
            "source_type": "measured_local",
            "source_url": "https://example.com/node-a",
            "power_scope": "measured_device_input",
            "identity": {"exact_id": "node-a"},
            "load_w": 18.5,
        }],
    }), encoding="utf-8")
    rows = sourced_power_observations(path)
    assert len(rows) == 1
    assert rows[0]["load_w"] == 18.5


def test_factory_firmware_never_decodes_unpublished_serial_pattern() -> None:
    listing = {
        "title": "ASRock board",
        "configuration": {"manufacturer": "ASRock", "serial_number": "ABC12345"},
    }
    result = resolve_factory_firmware(listing, required_bios="P1.40", rules={"schema_version": 1, "rules": []})
    assert result["status"] == "unresolved"
    assert result["serial_number_present"] is True
    assert result["manufacturer_authority"] is False


def test_vendor_published_serial_rule_can_resolve_factory_bios() -> None:
    listing = {
        "title": "Gigabyte Example",
        "configuration": {"manufacturer": "Gigabyte", "serial_number": "SN2026A123"},
    }
    rules = {
        "schema_version": 1,
        "rules": [{
            "id": "gigabyte-example-batch",
            "enabled": True,
            "manufacturer": "Gigabyte",
            "match_kind": "serial_regex",
            "serial_pattern": r"SN2026A\d{3}",
            "factory_bios_version": "F14",
            "source_url": "https://www.gigabyte.com/example/factory-firmware-map",
        }],
    }
    result = resolve_factory_firmware(
        listing,
        required_bios="F12",
        source_url="https://www.gigabyte.com/example/support",
        rules=rules,
    )
    assert result["status"] == "verified_factory_firmware"
    assert result["factory_bios_version"] == "F14"
    assert result["meets_minimum"] is True
    assert result["manufacturer_authority"] is True


def test_documented_factory_bios_sticker_method_uses_observed_label() -> None:
    listing = {
        "title": "ASRock Example",
        "configuration": {"manufacturer": "ASRock", "factory_bios_label": "P1.40"},
    }
    rules = {
        "schema_version": 1,
        "rules": [{
            "id": "asrock-sticker",
            "enabled": True,
            "manufacturer": "ASRock",
            "match_kind": "factory_bios_label",
            "observed_label_is_factory_bios": True,
            "source_url": "https://www.asrock.com/support/index.asp?cat=FindBIOS",
        }],
    }
    result = resolve_factory_firmware(listing, required_bios="P1.20", source_url="https://www.asrock.com/support", rules=rules)
    assert result["factory_bios_version"] == "P1.40"
    assert result["meets_minimum"] is True
    assert result["confidence"] == "exact"


def test_boot_readiness_prioritizes_verified_factory_firmware(monkeypatch: pytest.MonkeyPatch) -> None:
    import lowpower_llm_cluster.seller_firmware as seller_module

    monkeypatch.setattr(seller_module, "resolve_factory_firmware", lambda *args, **kwargs: {
        "status": "verified_factory_firmware",
        "factory_bios_version": "F14",
        "meets_minimum": True,
        "confidence": "exact",
        "manufacturer_authority": True,
        "reason": "test manufacturer mapping",
    })
    result = boot_readiness_score(
        {"status": "supported", "minimum_bios_version": "F12", "source_url": "https://www.gigabyte.com/support", "matrix_complete": True},
        {"status": "unknown", "seller_firmware_evidence": {"serial_number": "SN2026A123", "source_type": "seller_listing_text"}},
    )
    assert result["readiness"] == "ready_with_verified_factory_firmware"
    assert result["score"] == 98
    assert result["factory_firmware"]["manufacturer_authority"] is True
