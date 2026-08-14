from __future__ import annotations

from . import service_cli
from .promotion_refresh import PromotionCatalogRefreshEngine


def main() -> int:
    # Keep the existing service CLI/options and deployment tooling, but swap in the
    # promotion-aware engine so every successful local refresh can update canonical.
    service_cli.LearningCatalogRefreshEngine = PromotionCatalogRefreshEngine
    return service_cli.main()


if __name__ == "__main__": raise SystemExit(main())
