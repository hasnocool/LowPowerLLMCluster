from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .catalog_refresh import CatalogRefreshEngine
from .debug_artifacts import DebugArtifactWriter, sanitize
from .source_quality import SourceCycleAccumulator, SourceQualitySample, SourceQualityStore


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _normalized_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    records = payload.get("observations", []) if isinstance(payload, dict) else []
    return [dict(item) for item in records if isinstance(item, dict)]


def _adapter_inner(adapter: Any) -> Any:
    return getattr(adapter, "inner", adapter)


class LearningCatalogRefreshEngine(CatalogRefreshEngine):
    """Catalog refresh with persistent source-quality learning and repo-safe debug artifacts."""

    def __init__(self, *args: Any, debug_dir: str | Path | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.debug_dir = Path(debug_dir).expanduser().resolve() if debug_dir else self.output_path.parent / "debug"
        self.debug_writer: DebugArtifactWriter | None = None
        self.quality_store: SourceQualityStore | None = None
        self._learning_started = False
        self._cycle_index = 0
        self._base_candidate_pages: dict[str, int] = {}

    def _quality_config(self) -> dict[str, Any]:
        value = self.config.get("source_quality_learning", {})
        return dict(value) if isinstance(value, dict) else {}

    def _debug_config(self) -> dict[str, Any]:
        value = self.config.get("debug_artifacts", {})
        return dict(value) if isinstance(value, dict) else {}

    async def start(self) -> None:
        await super().start()
        if self._learning_started:
            return
        quality = self._quality_config()
        self.quality_store = SourceQualityStore(
            self.history_path,
            min_cycles_before_adaptation=int(quality.get("min_cycles_before_adaptation", 3)),
            max_scan_every_cycles=int(quality.get("max_scan_every_cycles", 4)),
            min_budget_multiplier=float(quality.get("min_budget_multiplier", 0.5)),
            max_budget_multiplier=float(quality.get("max_budget_multiplier", 1.5)),
        )
        await self.quality_store.initialize()
        debug = self._debug_config()
        root = Path(str(debug.get("root", self.debug_dir))).expanduser()
        if not root.is_absolute():
            root = self.debug_dir if "root" not in debug else Path.cwd() / root
        self.debug_writer = DebugArtifactWriter(
            root,
            max_log_bytes=int(debug.get("max_log_bytes", 8 * 1024 * 1024)),
            keep_runs=int(debug.get("keep_runs", 20)),
        )
        self._capture_base_budgets(self.adapters)
        self._learning_started = True
        await self.debug_writer.emit(
            "learning_engine_started",
            history=self.history_path,
            output=self.output_path,
            debug_dir=self.debug_writer.root,
            source_count=len(self.adapters),
        )

    def _capture_base_budgets(self, adapters: list[Any] | tuple[Any, ...]) -> None:
        for adapter in adapters:
            inner = _adapter_inner(adapter)
            if hasattr(inner, "max_candidate_pages"):
                self._base_candidate_pages.setdefault(adapter.name, int(getattr(inner, "max_candidate_pages")))

    def _is_learned(self, name: str) -> bool:
        return name.startswith("auto-")

    async def _scheduler_plan(self) -> tuple[list[Any], dict[str, Any]]:
        assert self.quality_store is not None
        self._cycle_index += 1
        quality = self._quality_config()
        adaptive = bool(quality.get("enabled", True)) and bool(quality.get("adaptive_scheduling", True))
        learned_names = [adapter.name for adapter in self.adapters if self._is_learned(adapter.name)]
        policies = await self.quality_store.policies(learned_names)
        selected: list[Any] = []
        skipped: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        cap = max(4, int(quality.get("max_candidate_pages_cap", 96)))

        self._capture_base_budgets(self.adapters)
        for adapter in self.adapters:
            name = adapter.name
            policy = policies.get(name, {})
            every = max(1, int(policy.get("scan_every_cycles", 1))) if adaptive and self._is_learned(name) else 1
            multiplier = float(policy.get("budget_multiplier", 1.0)) if adaptive and self._is_learned(name) else 1.0
            due = not self._is_learned(name) or not adaptive or ((self._cycle_index - 1) % every == 0)
            inner = _adapter_inner(adapter)
            base_pages = self._base_candidate_pages.get(name)
            applied_pages: int | None = None
            if base_pages is not None:
                applied_pages = max(4, min(cap, int(round(base_pages * multiplier))))
                setattr(inner, "max_candidate_pages", applied_pages)
            decision = {
                "source": name,
                "learned": self._is_learned(name),
                "quality_score": policy.get("quality_score"),
                "scan_every_cycles": every,
                "budget_multiplier": round(multiplier, 3),
                "candidate_page_budget": applied_pages,
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
            "selected_sources": len(selected),
            "skipped_sources": skipped,
            "decisions": decisions,
        }

    async def _learn_from_run(self, summary: dict[str, Any], selected_names: list[str]) -> list[dict[str, Any]]:
        assert self.quality_store is not None
        records = _normalized_records(self.output_path)
        by_source: dict[str, dict[tuple[str, str], dict[str, Any]]] = {name: {} for name in selected_names}
        for record in records:
            source = str(record.get("source", ""))
            if source not in by_source:
                continue
            identity = (source, str(record.get("source_id", "")))
            by_source[source][identity] = record

        runtime = summary.get("runtime", {}) if isinstance(summary.get("runtime"), dict) else {}
        discovery = runtime.get("discovery", {}) if isinstance(runtime.get("discovery"), dict) else {}
        raw_counts = discovery.get("source_raw_observations", {}) if isinstance(discovery.get("source_raw_observations"), dict) else {}
        durations = discovery.get("source_durations_ms", {}) if isinstance(discovery.get("source_durations_ms"), dict) else {}
        errors = summary.get("errors", {}) if isinstance(summary.get("errors"), dict) else {}
        samples: list[SourceQualitySample] = []
        for source in selected_names:
            accumulator = SourceCycleAccumulator(source)
            accumulator.add(by_source.get(source, {}).values())
            samples.append(SourceQualitySample(
                source=source,
                success=source not in errors,
                raw_observations=int(raw_counts.get(source, accumulator.unique_observations)),
                unique_observations=accumulator.unique_observations,
                priced_observations=accumulator.priced_observations,
                spec_score_sum=accumulator.spec_score_sum,
                freshness_score_sum=accumulator.freshness_score_sum,
                relevance_score_sum=accumulator.relevance_score_sum,
                latency_ms=float(durations.get(source, 0.0)),
                error=str(errors.get(source, "")),
            ))
        return await self.quality_store.record(samples)

    async def run_once(self) -> dict[str, Any]:
        await self.start()
        assert self.debug_writer is not None and self.quality_store is not None
        all_before = list(self.adapters)
        before_names = {adapter.name for adapter in all_before}
        selected, scheduler = await self._scheduler_plan()
        selected_names = [adapter.name for adapter in selected]
        await self.debug_writer.emit(
            "cycle_plan",
            cycle_index=self._cycle_index,
            selected_sources=selected_names,
            skipped_sources=[item["source"] for item in scheduler["skipped_sources"]],
            decisions=scheduler["decisions"],
        )
        self.adapters = selected
        try:
            summary = await super().run_once()
        except BaseException as exc:
            current = list(self.adapters)
            new = [adapter for adapter in current if adapter.name not in before_names]
            self.adapters = all_before + new
            await self.debug_writer.emit(
                "refresh_exception",
                cycle_index=self._cycle_index,
                error=f"{type(exc).__name__}: {exc}",
                selected_sources=selected_names,
            )
            raise

        current = list(self.adapters)
        new = [adapter for adapter in current if adapter.name not in before_names]
        self.adapters = all_before + new
        self._capture_base_budgets(new)

        learned = await self._learn_from_run(summary, selected_names)
        quality_snapshot = await self.quality_store.snapshot(limit=int(self._quality_config().get("debug_snapshot_limit", 500)))
        runtime = summary.setdefault("runtime", {})
        runtime["source_quality_learning"] = {
            "enabled": bool(self._quality_config().get("enabled", True)),
            "updated_sources": len(learned),
            "scheduler": scheduler,
            "source_quality": learned,
        }
        runtime["debug_artifacts"] = {
            "root": str(self.debug_writer.root),
            "runtime_log": str(self.debug_writer.log_path),
        }

        for item in learned:
            await self.debug_writer.emit("source_quality_updated", cycle_index=self._cycle_index, **item)
        for source, error in (summary.get("errors", {}) or {}).items():
            await self.debug_writer.emit("source_error", cycle_index=self._cycle_index, source=source, error=error)

        debug_files = await self.debug_writer.write_run(
            str(summary.get("run_id", f"cycle-{self._cycle_index}")),
            summary=summary,
            source_quality=quality_snapshot,
            scheduler=scheduler,
            effective_config=self.config,
        )
        runtime["debug_artifacts"]["run_files"] = debug_files
        await self.debug_writer.emit(
            "cycle_debug_complete",
            cycle_index=self._cycle_index,
            run_id=summary.get("run_id"),
            observations=summary.get("observation_count", 0),
            errors=summary.get("errors", {}),
            dynamic_sources=summary.get("runtime", {}).get("dynamic_source_count", 0),
        )

        try:
            payload = json.loads(self.output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            payload["runtime"] = sanitize(runtime)
            await asyncio.to_thread(_atomic_json, self.output_path, payload)
        return summary
