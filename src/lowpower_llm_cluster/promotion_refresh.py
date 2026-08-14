from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .canonical_promotion import promote, records_from_output
from .learning_refresh import LearningCatalogRefreshEngine, _adapter_inner
from .promotion_enrichment import enrich_held_records
from .source_cooldown import SourceCooldownStore


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class PromotionCatalogRefreshEngine(LearningCatalogRefreshEngine):
    """Learning refresh with source cooldown, enrichment and canonical promotion."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.cooldown_store: SourceCooldownStore | None = None

    def _promotion_config(self) -> dict[str, Any]:
        value = self.config.get("canonical_promotion", {})
        return dict(value) if isinstance(value, dict) else {}

    async def start(self) -> None:
        await super().start()
        if self.cooldown_store is None:
            self.cooldown_store = SourceCooldownStore(self.history_path)
            await self.cooldown_store.initialize()
        if self.debug_writer is not None:
            config = self._promotion_config()
            await self.debug_writer.emit(
                "promotion_engine_started",
                engine=type(self).__name__,
                canonical_promotion=bool(config.get("enabled", True)),
                catalog_path=str(config.get("catalog_path", "data/catalog/auto-promoted.json")),
                report_path=str(config.get("report_path", "results/promotion-latest.json")),
                enrichment_enabled=bool(config.get("enrichment_enabled", True)),
            )

    async def _scheduler_plan(self) -> tuple[list[Any], dict[str, Any]]:
        """Apply quality learning and failure cooldown to curated and learned sources."""
        assert self.quality_store is not None and self.cooldown_store is not None
        self._cycle_index += 1
        quality = self._quality_config()
        adaptive = bool(quality.get("enabled", True)) and bool(quality.get("adaptive_scheduling", True))
        names = [adapter.name for adapter in self.adapters]
        policies = await self.quality_store.policies(names)
        cooldowns = await self.cooldown_store.policies(names)
        selected: list[Any] = []
        skipped: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        cap = max(4, int(quality.get("max_candidate_pages_cap", 96)))
        adapt_curated = bool(quality.get("adapt_curated_sources", True))

        self._capture_base_budgets(self.adapters)
        for adapter in self.adapters:
            name = adapter.name
            learned = self._is_learned(name)
            policy = policies.get(name, {})
            cooldown = cooldowns.get(name, {})
            adaptive_for_source = adaptive and (learned or adapt_curated)
            every = max(1, int(policy.get("scan_every_cycles", 1))) if adaptive_for_source else 1
            multiplier = float(policy.get("budget_multiplier", 1.0)) if adaptive_for_source else 1.0
            cadence_due = not adaptive_for_source or ((self._cycle_index - 1) % every == 0)
            cooldown_until = int(cooldown.get("cooldown_until_cycle", 0) or 0)
            cooldown_due = self._cycle_index >= cooldown_until
            due = cadence_due and cooldown_due

            inner = _adapter_inner(adapter)
            base_pages = self._base_candidate_pages.get(name)
            applied_pages: int | None = None
            if base_pages is not None:
                applied_pages = max(4, min(cap, int(round(base_pages * multiplier))))
                setattr(inner, "max_candidate_pages", applied_pages)
            decision = {
                "source": name,
                "learned": learned,
                "quality_score": policy.get("quality_score"),
                "scan_every_cycles": every,
                "budget_multiplier": round(multiplier, 3),
                "candidate_page_budget": applied_pages,
                "failure_class": cooldown.get("failure_class") or None,
                "consecutive_failures": int(cooldown.get("consecutive_failures", 0) or 0),
                "cooldown_until_cycle": cooldown_until,
                "cadence_due": cadence_due,
                "cooldown_due": cooldown_due,
                "due": due,
            }
            decisions.append(decision)
            if due:
                selected.append(adapter)
            else:
                skipped.append(decision)
        return selected, {
            "cycle_index": self._cycle_index,
            "adaptive": adaptive,
            "adapt_curated_sources": adapt_curated,
            "selected_sources": len(selected),
            "skipped_sources": skipped,
            "decisions": decisions,
        }

    async def run_once(self) -> dict[str, Any]:
        await self.start()
        summary = await super().run_once()
        assert self.cooldown_store is not None
        runtime = summary.setdefault("runtime", {})
        scheduler = ((runtime.get("source_quality_learning") or {}).get("scheduler") or {})
        selected_names = [
            str(item.get("source"))
            for item in scheduler.get("decisions", [])
            if isinstance(item, dict) and item.get("due")
        ]
        await self.cooldown_store.record_cycle(
            cycle_index=self._cycle_index,
            selected_sources=selected_names,
            errors=summary.get("errors", {}) if isinstance(summary.get("errors"), dict) else {},
        )

        config = self._promotion_config()
        if config.get("enabled", True) is False:
            runtime["canonical_promotion"] = {"enabled": False}
            return summary

        catalog_path = Path(str(config.get("catalog_path", "data/catalog/auto-promoted.json"))).expanduser()
        report_path = Path(str(config.get("report_path", "results/promotion-latest.json"))).expanduser()
        enrichment_path = Path(str(config.get("enrichment_report_path", "results/promotion-enrichment-latest.json"))).expanduser()
        health_path = Path(str(config.get("health_path", "results/promotion-health.json"))).expanduser()
        min_source = float(config.get("min_source_confidence", 0.80))
        min_sku = float(config.get("min_sku_confidence", 0.55))
        records = await asyncio.to_thread(records_from_output, self.output_path)
        started_at = datetime.now(UTC).isoformat()

        try:
            if bool(config.get("enrichment_enabled", True)) and self.client is not None:
                enriched = await enrich_held_records(
                    records,
                    config=self.config,
                    client=self.client,
                    max_refetch=int(config.get("max_enrichment_refetch_per_cycle", 24)),
                    concurrency=int(config.get("enrichment_concurrency", 4)),
                    min_source_confidence=min_source,
                    min_sku_confidence=min_sku,
                )
                records = list(enriched.records)
                enrichment_report = {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "attempted": enriched.attempted,
                    "structured_products": enriched.structured_products,
                    "resolved_holds": enriched.resolved_holds,
                    "still_held": enriched.still_held,
                    "errors": enriched.errors,
                }
                await asyncio.to_thread(_atomic_json, enrichment_path, enrichment_report)
            else:
                enrichment_report = {"generated_at": datetime.now(UTC).isoformat(), "enabled": False}

            report = await asyncio.to_thread(
                promote,
                records,
                catalog_path=catalog_path,
                report_path=report_path,
                min_source_confidence=min_source,
                min_sku_confidence=min_sku,
            )
            completed_at = datetime.now(UTC).isoformat()
            health = {
                "status": "ok",
                "engine": type(self).__name__,
                "run_id": summary.get("run_id"),
                "discovery_completed_at": started_at,
                "promotion_completed_at": completed_at,
                "promotion_fresh": True,
                "catalog_path": str(catalog_path),
                "report_path": str(report_path),
                "canonical_total": report["canonical_total"],
                "promoted_count": report["promoted_count"],
                "updated_count": report["updated_count"],
                "held_count": report["held_count"],
                "by_source": report.get("by_source", {}),
                "enrichment": enrichment_report,
            }
            await asyncio.to_thread(_atomic_json, health_path, health)
            runtime["canonical_promotion"] = health
            if self.debug_writer is not None:
                await self.debug_writer.emit("canonical_promotion_complete", **health)
        except Exception as exc:
            health = {
                "status": "degraded",
                "engine": type(self).__name__,
                "run_id": summary.get("run_id"),
                "discovery_completed_at": started_at,
                "promotion_completed_at": None,
                "promotion_fresh": False,
                "error": f"{type(exc).__name__}: {exc}",
                "catalog_path": str(catalog_path),
                "report_path": str(report_path),
            }
            await asyncio.to_thread(_atomic_json, health_path, health)
            runtime["canonical_promotion"] = health
            if self.debug_writer is not None:
                await self.debug_writer.emit("canonical_promotion_failed", **health)
        return summary
