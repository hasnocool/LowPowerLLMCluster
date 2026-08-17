from __future__ import annotations

from lowpower_llm_cluster.canonical_promotion import canonical_part, evaluate
from lowpower_llm_cluster.secondary_accelerator_policy import (
    evaluate_secondary_accelerator,
    match_watch,
    promotion_snapshot,
)


def _record(title: str, **overrides):
    value = {
        "source": "ebay",
        "source_id": "listing-1",
        "listing_url": "https://example.com/listing-1",
        "title": title,
        "manufacturer": "Example Vendor",
        "sku": "SKU-1",
        "mpn": "MPN-1",
        "price": 300.0,
        "currency": "USD",
        "source_confidence": 0.95,
        "sku_confidence": 0.95,
        "in_stock": True,
        "observed_at": "2026-08-17T00:00:00+00:00",
        "form_factor": "pcie_card",
        "raw_attributes": {},
    }
    value.update(overrides)
    return value


def test_unmatched_products_keep_existing_promotion_behavior() -> None:
    record = _record("Example AI Mini PC")
    assert match_watch(record) is None
    assert evaluate_secondary_accelerator(record) == []
    assert evaluate(record) == []


def test_watched_accelerator_fails_closed_without_price_or_runtime() -> None:
    record = _record("AMD Alveo U250 64GB")
    reasons = evaluate(record)
    assert "accelerator_landed_cost_missing" in reasons
    assert "accelerator_transformer_runtime_unverified" in reasons


def test_watched_accelerator_holds_when_landed_cost_is_above_policy_ceiling() -> None:
    record = _record(
        "AMD Alveo U250 64GB",
        landed_cost_cad=601.0,
        raw_attributes={
            "memory_capacity_gb": 64,
            "transformer_runtime_verified": True,
            "demonstrated_transformer_runtime": "Vitis transformer prototype",
        },
    )
    reasons = evaluate_secondary_accelerator(record)
    assert "accelerator_landed_cost_above_threshold" in reasons
    assert "accelerator_transformer_runtime_unverified" not in reasons


def test_watched_accelerator_promotes_only_when_economic_and_runtime_gates_pass() -> None:
    record = _record(
        "Intel Gaudi2 HL-225 96GB",
        manufacturer="Intel",
        landed_cost_cad=1750.0,
        raw_attributes={
            "memory_capacity_gb": 96,
            "transformer_runtime_verified": True,
            "demonstrated_transformer_runtime": "Optimum-Habana",
            "software_stack": "Intel Gaudi software / Optimum-Habana",
            "llm_candidate": True,
        },
    )
    assert evaluate(record) == []
    snapshot = promotion_snapshot(record)
    assert snapshot is not None
    assert snapshot["watch_id"] == "intel-gaudi2-96g"
    assert snapshot["economic_eligible"] is True
    assert snapshot["transformer_runtime_verified"] is True
    assert snapshot["eligible"] is True

    part = canonical_part(record)
    audit = part["promotion_provenance"]["secondary_accelerator_policy"]
    assert audit["watch_id"] == "intel-gaudi2-96g"
    assert audit["landed_cad"] == 1750.0
    assert audit["max_landed_cad"] == 1800


def test_runtime_must_match_approved_family() -> None:
    record = _record(
        "Intel Gaudi2 HL-225 96GB",
        landed_cost_cad=1200.0,
        raw_attributes={
            "memory_capacity_gb": 96,
            "transformer_runtime_verified": True,
            "demonstrated_transformer_runtime": "Unknown proprietary runtime",
        },
    )
    assert "accelerator_runtime_not_in_approved_family" in evaluate_secondary_accelerator(record)


def test_memory_identity_mismatch_blocks_promotion() -> None:
    record = _record(
        "Tenstorrent Wormhole n300 24GB",
        landed_cost_cad=700.0,
        raw_attributes={
            "memory_capacity_gb": 12,
            "transformer_runtime_verified": True,
            "demonstrated_transformer_runtime": "tt-inference-server",
        },
    )
    assert "accelerator_memory_identity_mismatch" in evaluate_secondary_accelerator(record)


def test_gaudi_first_generation_does_not_match_gaudi2() -> None:
    first = match_watch(_record("Habana Gaudi 32GB HL-205"))
    second = match_watch(_record("Intel Gaudi2 HL-225 96GB"))
    assert first and first["id"] == "intel-gaudi-32g"
    assert second and second["id"] == "intel-gaudi2-96g"
