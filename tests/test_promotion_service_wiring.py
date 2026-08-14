from __future__ import annotations

from lowpower_llm_cluster.promotion_refresh import PromotionCatalogRefreshEngine
from lowpower_llm_cluster import promotion_service_cli


def test_service_entrypoint_uses_promotion_engine() -> None:
    assert PromotionCatalogRefreshEngine.__name__ == "PromotionCatalogRefreshEngine"
    assert callable(promotion_service_cli.main)
