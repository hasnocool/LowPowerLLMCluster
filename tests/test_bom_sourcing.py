from __future__ import annotations

from lowpower_llm_cluster.bom_sourcing import rank_bom_listing, select_bom_candidate
from lowpower_llm_cluster.market import Listing
from lowpower_llm_cluster.tco import infrastructure_cost


def listing(title: str, price: float, *, source_kind: str = "structured_marketplace", source: str = "ebay-ca") -> Listing:
    return Listing(source=source, source_id=title, url="https://example.test/item", title=title, price=price, currency="CAD", observed_at="2026-08-11T00:00:00+00:00", seller="seller", source_kind=source_kind, seller_metrics={"feedback_percentage": 99.9, "feedback_score": 10000, "top_rated": True})


def test_bom_matching_rejects_excluded_items():
    spec = {"required_terms_any": ["750w"], "exclude_terms": ["for parts"]}
    assert rank_bom_listing("psu_750w", listing("750W PSU for parts", 20), spec, {"CAD": 1.0}, tax_rate=0.12) is None


def test_bom_candidate_has_landed_cost_and_confidence():
    spec = {"required_terms_any": ["750w"], "exclude_terms": []}
    row = rank_bom_listing("psu_750w", listing("750W ATX Gold PSU", 100), spec, {"CAD": 1.0}, tax_rate=0.12)
    assert row is not None
    assert row["landed"]["landed_cad"] == 112.0
    assert row["seller_confidence"]["score"] > 0.45


def test_authorized_source_can_win_within_price_tolerance():
    spec = {"required_terms_any": ["1tb"], "exclude_terms": []}
    market = rank_bom_listing("storage_1tb", listing("1TB NVMe SSD", 100), spec, {"CAD": 1.0}, tax_rate=0)
    dist = rank_bom_listing("storage_1tb", listing("1TB NVMe SSD", 109, source_kind="authorized_distributor", source="digikey"), spec, {"CAD": 1.0}, tax_rate=0)
    selected = select_bom_candidate([market, dist], {"selection": {"minimum_seller_confidence": 0.4, "prefer_authorized_sources_within_pct": 12}})
    assert selected["listing"]["source"] == "digikey"


def test_tco_line_preserves_sourced_basis():
    gpu = {"category": "gpu_accelerator", "host_mode": "pcie_add_in_card", "memory_config_status": "fixed"}
    scenarios = {
        "component_costs_cad": {"cpu_host": 150, "motherboard": 120, "host_ram_32gb": 80, "storage_1tb": 70, "psu_750w": 110, "pcie_adapter": 40, "cooling": 40, "chassis": 80, "chassis_misc": 20},
        "component_cost_basis": {"psu_750w": {"basis": "sourced_live_listing_landed_cad", "source": "ebay-ca"}},
        "ownership_profiles": {"new-build": {"owned_components": []}},
    }
    result = infrastructure_cost(gpu, scenarios)
    psu = next(row for row in result["components"] if row["component"] == "psu_750w")
    assert psu["basis"] == "sourced_live_listing_landed_cad"
    assert result["sourced_component_count"] == 1
