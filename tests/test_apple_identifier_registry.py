# tests/test_apple_identifier_registry.py
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "evidence" / "apple-identifiers.json"


def test_apple_identifier_registry_is_unique_and_authoritative():
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1

    seen_ids: set[str] = set()
    seen_patterns: set[str] = set()
    for record in payload["records"]:
        record_id = record["id"]
        assert record_id not in seen_ids
        seen_ids.add(record_id)

        source_url = record["source_url"]
        assert source_url.startswith("https://support.apple.com/")
        if record.get("a_number_source_url"):
            assert record["a_number_source_url"].startswith("https://support.apple.com/")

        assert record.get("model_identifiers") or record.get("part_number_patterns") or record.get("a_numbers")
        for pattern in record.get("part_number_patterns", []):
            normalized = pattern.upper()
            assert normalized.endswith("XX/A")
            assert normalized not in seen_patterns
            seen_patterns.add(normalized)


def test_registry_does_not_claim_build_to_order_capacity_from_part_family():
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    forbidden = {"memory_capacity_gb", "storage_gb", "gpu_cores", "cpu_cores"}
    for record in payload["records"]:
        assert forbidden.isdisjoint(record)
