from pathlib import Path

from lowpower_llm_cluster.config_loader import load_discovery_config

ROOT = Path(__file__).resolve().parents[1]


def test_default_discovery_enables_curated_adaptation_and_promotion_enrichment() -> None:
    config = load_discovery_config(ROOT / "config" / "discovery.example.json")
    quality = config["source_quality_learning"]
    promotion = config["canonical_promotion"]
    assert quality["adapt_curated_sources"] is True
    assert promotion["enabled"] is True
    assert promotion["enrichment_enabled"] is True
    assert promotion["max_enrichment_refetch_per_cycle"] == 24
    assert promotion["catalog_path"].endswith("auto-promoted.json")
    assert promotion["health_path"].endswith("promotion-health.json")
