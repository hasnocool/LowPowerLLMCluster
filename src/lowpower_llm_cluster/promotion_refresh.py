from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .canonical_promotion import promote, records_from_output
from .learning_refresh import LearningCatalogRefreshEngine


class PromotionCatalogRefreshEngine(LearningCatalogRefreshEngine):
    """Learning refresh engine with gated discovery-to-canonical promotion."""

    def _promotion_config(self) -> dict[str, Any]:
        value = self.config.get("canonical_promotion", {})
        return dict(value) if isinstance(value, dict) else {}

    async def run_once(self) -> dict[str, Any]:
        summary = await super().run_once()
        config = self._promotion_config()
        if config.get("enabled", True) is False:
            summary.setdefault("runtime", {})["canonical_promotion"] = {"enabled": False}
            return summary

        catalog_path = Path(str(config.get("catalog_path", "data/catalog/auto-promoted.json"))).expanduser()
        report_path = Path(str(config.get("report_path", "results/promotion-latest.json"))).expanduser()
        records = await asyncio.to_thread(records_from_output, self.output_path)
        report = await asyncio.to_thread(
            promote,
            records,
            catalog_path=catalog_path,
            report_path=report_path,
            min_source_confidence=float(config.get("min_source_confidence", 0.80)),
            min_sku_confidence=float(config.get("min_sku_confidence", 0.55)),
        )
        runtime = summary.setdefault("runtime", {})
        runtime["canonical_promotion"] = {
            "enabled": True,
            "catalog_path": str(catalog_path),
            "report_path": str(report_path),
            "canonical_total": report["canonical_total"],
            "promoted_count": report["promoted_count"],
            "updated_count": report["updated_count"],
            "held_count": report["held_count"],
        }
        if self.debug_writer is not None:
            await self.debug_writer.emit("canonical_promotion_complete", **runtime["canonical_promotion"])
        return summary
