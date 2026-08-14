from __future__ import annotations

from . import catalog_refresh, service_cli
from .history_compaction import CompactingCatalogHistory
from .promotion_refresh import PromotionCatalogRefreshEngine
from .resilient_runtime import ResilientAsyncHttpClient


def main() -> int:
    # Keep the existing CLI/options and deployment tooling, but swap the concrete
    # runtime classes before the engine starts. This keeps one authoritative service
    # entrypoint while enabling bounded larger headers, compact history, adaptive
    # cooldowns, enrichment, and canonical promotion.
    catalog_refresh.AsyncHttpClient = ResilientAsyncHttpClient
    catalog_refresh.CatalogHistory = CompactingCatalogHistory
    service_cli.LearningCatalogRefreshEngine = PromotionCatalogRefreshEngine
    return service_cli.main()


if __name__ == "__main__":
    raise SystemExit(main())
