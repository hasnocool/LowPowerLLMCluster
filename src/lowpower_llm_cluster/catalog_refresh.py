from __future__ import annotations

import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from .announcement_links import hydrate_announcement_links
from .config_loader import load_discovery_config
from .discovery import ProductObservation
from .history import CatalogHistory, ListingChange
from .http_runtime import AdaptiveConcurrency, AsyncHttpClient, DiscoveryCache
from .normalization import normalize_observation
from .resilience_runtime import AdaptiveBatchSizer, CircuitBreaker, peak_rss_mb
from .runtime import WorkerSettings, map_sync_bounded
from .source_expansion import AutoSourceExpander, SourceCandidate, source_config_from_record
from .source_runtime import build_source_adapter
from .source_store import SourceCandidateStore
from .streaming_discovery import StreamingDiscoveryPipeline


def _reset_spool(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _serialize_jsonl(observations: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(item, sort_keys=True, separators=(",", ":"), default=str) + "\n" for item in observations)


def _source_hosts(source: dict[str, Any]) -> set[str]:
    values: list[str] = []
    endpoint = source.get("endpoint")
    if endpoint:
        values.append(str(endpoint))
    values.extend(str(value) for value in source.get("seeds", ()))
    values.extend(str(value) for value in source.get("urls", ()))
    hosts: set[str] = set()
    for value in values:
        host = (urlparse(value).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if host:
            hosts.add(host)
    return hosts


class ObservationSpool:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.path = output_path.with_name(f".{output_path.name}.{os.getpid()}.observations.jsonl")
        self.count = 0

    async def reset(self) -> None:
        await asyncio.to_thread(_reset_spool, self.path)
        self.count = 0

    async def append(self, observations: list[dict[str, Any]]) -> None:
        if not observations:
            return
        lines = await asyncio.to_thread(_serialize_jsonl, observations)
        await asyncio.to_thread(self._append_sync, lines)
        self.count += len(observations)

    def _append_sync(self, lines: str) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(lines)

    async def finalize(self, metadata: dict[str, Any]) -> None:
        await asyncio.to_thread(self._finalize_sync, metadata)

    def _finalize_sync(self, metadata: dict[str, Any]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output_path.with_name(f".{self.output_path.name}.{os.getpid()}.tmp")
        with temporary.open("w", encoding="utf-8") as output:
            output.write("{\n")
            for key, value in metadata.items():
                output.write(f"  {json.dumps(key)}: {json.dumps(value, sort_keys=True, default=str)},\n")
            output.write('  "observations": [\n')
            first = True
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as source:
                    for line in source:
                        line = line.strip()
                        if not line:
                            continue
                        if not first:
                            output.write(",\n")
                        output.write("    " + line)
                        first = False
            output.write("\n  ]\n}\n")
        os.replace(temporary, self.output_path)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class CatalogRefreshEngine:
    def __init__(self, config_path: Path | str, *, history_path: Path | str, output_path: Path | str, cache_path: Path | str | None = None) -> None:
        self.config_path = Path(config_path)
        self.history_path = Path(history_path)
        self.output_path = Path(output_path)
        self.cache_path = Path(cache_path) if cache_path is not None else self.history_path.with_suffix(".http-cache.json")
        self.config: dict[str, Any] = {}
        self.settings: WorkerSettings | None = None
        self.client: AsyncHttpClient | None = None
        self.cache: DiscoveryCache | None = None
        self.history: CatalogHistory | None = None
        self.source_store: SourceCandidateStore | None = None
        self.adapters: list[Any] = []
        self.trusts: dict[str, float] = {}
        self.adaptive: dict[str, AdaptiveConcurrency] = {}
        self.circuits: dict[str, CircuitBreaker] = {}
        self.batch_sizers: dict[str, AdaptiveBatchSizer] = {}
        self._source_names: set[str] = set()
        self._known_hosts: set[str] = set()
        self._dynamic_source_count = 0
        self._expansion_adaptive: AdaptiveConcurrency | None = None
        self._normalize_executor: ThreadPoolExecutor | None = None
        self._started = False

    async def __aenter__(self) -> "CatalogRefreshEngine":
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    def _expansion_config(self) -> dict[str, Any]:
        value = self.config.get("auto_source_expansion", {})
        return dict(value) if isinstance(value, dict) else {}

    def _register_source(self, source: dict[str, Any], *, dynamic: bool = False) -> bool:
        assert self.settings and self.client and self.cache
        settings = self.settings
        name = str(source["name"])
        if name in self._source_names:
            return False
        source_type = str(source.get("type", "json"))
        self.trusts[name] = float(source.get("source_trust", 0.65))
        public_parallel_types = {"jsonld", "sitemap", "feed", "html_index", "announcement_index"}
        max_subworkers = int(source.get("subworkers", settings.subworkers_per_agent)) if source_type in public_parallel_types else 1
        adaptive = AdaptiveConcurrency(
            minimum=min(settings.adaptive_min_subworkers, max_subworkers), maximum=max_subworkers,
            initial=max_subworkers, success_window=settings.adaptive_success_window,
            latency_target_ms=settings.adaptive_latency_target_ms, enabled=settings.adaptive_concurrency,
        )
        circuit = CircuitBreaker(
            failure_threshold=settings.circuit_failure_threshold,
            recovery_timeout_s=settings.circuit_recovery_timeout_s,
            half_open_max_calls=settings.circuit_half_open_calls,
            enabled=settings.circuit_breaker,
        )
        initial_batch = min(
            settings.adaptive_batch_max,
            max(settings.adaptive_batch_min, int(source.get("batch_size", settings.adaptive_batch_initial))),
        )
        batch_sizer = AdaptiveBatchSizer(
            minimum=settings.adaptive_batch_min, maximum=settings.adaptive_batch_max,
            initial=initial_batch, target_latency_ms=settings.adaptive_batch_target_ms,
            rss_soft_limit_mb=settings.adaptive_batch_rss_soft_limit_mb,
            success_window=settings.adaptive_batch_success_window, enabled=settings.adaptive_batching,
        )
        self.adaptive[name] = adaptive
        self.circuits[name] = circuit
        self.batch_sizers[name] = batch_sizer
        self.adapters.append(build_source_adapter(
            source, settings=settings, client=self.client, cache=self.cache,
            adaptive=adaptive, circuit=circuit, batch_sizer=batch_sizer,
        ))
        self._source_names.add(name)
        self._known_hosts.update(_source_hosts(source))
        if dynamic:
            self._dynamic_source_count += 1
        return True

    async def _load_dynamic_sources(self) -> None:
        assert self.source_store
        expansion = self._expansion_config()
        if not bool(expansion.get("enabled", False)):
            return
        limit = max(1, int(expansion.get("max_dynamic_sources", 64)))
        min_score = float(expansion.get("min_dynamic_source_score", 0.72))
        max_pages = max(1, int(expansion.get("max_candidate_pages_per_dynamic_source", 24)))
        subworkers = max(1, int(expansion.get("dynamic_subworkers", 2)))
        for record in await self.source_store.active(limit=limit, min_score=min_score):
            config = source_config_from_record(record, max_candidate_pages=max_pages, subworkers=subworkers)
            if config is not None and self._dynamic_source_count < limit:
                self._register_source(config, dynamic=True)

    def _activate_new_candidates(self, candidates: Iterable[SourceCandidate]) -> int:
        expansion = self._expansion_config()
        limit = max(1, int(expansion.get("max_dynamic_sources", 64)))
        min_score = float(expansion.get("min_dynamic_source_score", 0.72))
        max_pages = max(1, int(expansion.get("max_candidate_pages_per_dynamic_source", 24)))
        subworkers = max(1, int(expansion.get("dynamic_subworkers", 2)))
        added = 0
        for candidate in candidates:
            if self._dynamic_source_count >= limit or candidate.score < min_score:
                continue
            config = candidate.as_source_config(max_candidate_pages=max_pages, subworkers=subworkers)
            if config is not None and self._register_source(config, dynamic=True):
                added += 1
        return added

    async def start(self) -> None:
        if self._started:
            return
        self.config = await asyncio.to_thread(load_discovery_config, self.config_path)
        self.settings = WorkerSettings.from_mapping(self.config)
        settings = self.settings
        self.cache = await DiscoveryCache.open(
            self.cache_path,
            max_observations_per_entry=int(self.config.get("cache_observation_limit", 5000)),
            ttl_s=settings.cache_ttl_s,
            max_entries=settings.cache_max_entries,
            compress=settings.cache_compress,
        )
        self.history = CatalogHistory(self.history_path)
        await self.history.initialize()
        self.source_store = SourceCandidateStore(self.history_path)
        await self.source_store.initialize()
        self.client = AsyncHttpClient(
            concurrency=settings.http_concurrency, per_host=settings.http_per_host,
            timeout_s=settings.timeout_s, max_response_bytes=settings.max_response_bytes,
            retry_attempts=settings.retry_attempts, retry_backoff_base_s=settings.retry_backoff_base_s,
            retry_backoff_max_s=settings.retry_backoff_max_s, retry_jitter_s=settings.retry_jitter_s,
        )
        await self.client.start()
        self._normalize_executor = ThreadPoolExecutor(max_workers=settings.normalize_workers, thread_name_prefix="lpllm-normalize")
        for source in list(self.config.get("sources", [])):
            self._register_source(dict(source))
        expansion = self._expansion_config()
        expansion_workers = max(1, int(expansion.get("probe_concurrency", 2)))
        self._expansion_adaptive = AdaptiveConcurrency(
            minimum=1, maximum=expansion_workers, initial=expansion_workers,
            success_window=settings.adaptive_success_window,
            latency_target_ms=settings.adaptive_latency_target_ms,
            enabled=settings.adaptive_concurrency,
        )
        await self._load_dynamic_sources()
        self._started = True

    async def close(self) -> None:
        if not self._started:
            return
        if self.cache is not None:
            await self.cache.flush()
        if self.client is not None:
            await self.client.close()
        if self.history is not None:
            await self.history.close()
        if self._normalize_executor is not None:
            self._normalize_executor.shutdown(wait=False, cancel_futures=True)
            self._normalize_executor = None
        self._started = False

    async def _persist_batch(self, run_id: str, observations: tuple[ProductObservation, ...], *, spool: ObservationSpool, source_trust: float | None = None) -> tuple[ListingChange, ...]:
        assert self.history and self.settings and self._normalize_executor
        if not observations:
            return ()
        def normalize(item: ProductObservation) -> dict[str, Any]:
            trust = source_trust if source_trust is not None else self.trusts.get(item.source, 0.65)
            return normalize_observation(item, source_trust=trust)
        async with asyncio.TaskGroup() as group:
            persist = group.create_task(self.history.record_batch(run_id, observations))
            normalized = group.create_task(map_sync_bounded(
                observations, normalize, workers=self.settings.normalize_workers,
                queue_size=self.settings.queue_size, thread_name_prefix="lpllm-normalize",
                executor=self._normalize_executor,
            ))
        await spool.append(normalized.result())
        return persist.result()

    async def _expand_announcements(self, run_id: str, announcements: list[ProductObservation], *, spool: ObservationSpool) -> tuple[list[ListingChange], dict[str, Any]]:
        assert self.client and self.source_store and self._expansion_adaptive
        expansion = self._expansion_config()
        if not bool(expansion.get("enabled", False)) or not announcements:
            return [], {"enabled": bool(expansion.get("enabled", False)), "announcements": len(announcements)}
        started = time.perf_counter()
        max_announcements = max(1, int(expansion.get("max_announcements_per_cycle", 16)))
        max_links = max(1, int(expansion.get("max_links_per_announcement", 8)))
        hydrated = await hydrate_announcement_links(
            announcements, client=self.client, adaptive=self._expansion_adaptive,
            max_announcements=max_announcements, max_links_per_announcement=max_links,
            workers=max(1, int(expansion.get("announcement_workers", 2))),
        )
        expander = AutoSourceExpander(
            client=self.client, adaptive=self._expansion_adaptive,
            max_announcements=max_announcements, max_links_per_announcement=max_links,
            max_domains_per_cycle=max(1, int(expansion.get("max_domains_per_cycle", 6))),
            max_surface_probes_per_domain=max(1, int(expansion.get("max_surface_probes_per_domain", 8))),
            max_products_per_cycle=max(1, int(expansion.get("max_verified_products_per_cycle", 24))),
        )
        result = await expander.expand(hydrated, known_hosts=self._known_hosts)
        stored = await self.source_store.upsert([item.as_record() for item in result.candidates])
        changes = list(await self._persist_batch(
            run_id, result.products, spool=spool,
            source_trust=float(expansion.get("verified_product_trust", 0.92)),
        ))
        added = self._activate_new_candidates(result.candidates)
        summary = await self.source_store.summary()
        return changes, {
            "enabled": True, "announcements": len(hydrated),
            "domains_considered": result.domains_considered, "domains_probed": result.domains_probed,
            "pages_probed": result.pages_probed, "verified_products": len(result.products),
            "candidates_seen": len(result.candidates), "candidates_persisted": stored,
            "dynamic_sources_added": added, "candidate_store": summary,
            "errors": dict(result.errors),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        }

    async def run_once(self) -> dict[str, Any]:
        await self.start()
        assert self.settings and self.client and self.cache and self.history and self._normalize_executor
        started = time.perf_counter()
        run_id = await self.history.begin_refresh()
        spool = ObservationSpool(self.output_path)
        await spool.reset()
        seen_by_source: dict[str, set[str]] = {}
        changes: list[ListingChange] = []
        announcement_seeds: list[ProductObservation] = []
        pipeline = StreamingDiscoveryPipeline(tuple(self.adapters), worker_count=self.settings.agent_workers, queue_size=self.settings.queue_size)
        try:
            discovery_started = time.perf_counter()
            async for batch in pipeline.stream():
                if batch.error:
                    continue
                observations = tuple(batch.observations)
                seen_by_source.setdefault(batch.source, set()).update(item.source_id for item in observations)
                announcement_seeds.extend(
                    item for item in observations
                    if str(item.attributes.get("discovery_kind", "")) in {"announcement", "vendor_release"}
                )
                batch_started = time.perf_counter()
                changes.extend(await self._persist_batch(run_id, observations, spool=spool))
                elapsed_ms = (time.perf_counter() - batch_started) * 1000
                self.batch_sizers[batch.source].observe(latency_ms=elapsed_ms, rss_mb=peak_rss_mb())
            discovery_ms = round((time.perf_counter() - discovery_started) * 1000, 3)
            expansion_changes, expansion_metrics = await self._expand_announcements(run_id, announcement_seeds, spool=spool)
            changes.extend(expansion_changes)
            successful = [adapter.name for adapter in pipeline.adapters if adapter.name not in pipeline.last_errors]
            changes.extend(await self.history.finish_refresh(
                run_id, source_names=successful, seen_by_source=seen_by_source,
                disappearance_after_runs=int(self.config.get("disappearance_after_runs", 2)),
            ))
            await self.cache.flush()
        except BaseException:
            await self.history.abort_refresh(run_id)
            raise
        metadata: dict[str, Any] = {
            "run_id": run_id,
            "observation_count": spool.count,
            "errors": dict(pipeline.last_errors),
            "changes": [{
                "source": change.source, "source_id": change.source_id,
                "change_type": change.change_type, "previous": change.previous, "current": change.current,
            } for change in changes],
            "runtime": {
                "workers": self.settings.to_dict(), "discovery_ms": discovery_ms,
                "total_ms": round((time.perf_counter() - started) * 1000, 3),
                "source_count": len(self.adapters), "dynamic_source_count": self._dynamic_source_count,
                "source_registry_files": list(self.config.get("source_registry_files", [])),
                "auto_source_expansion": expansion_metrics,
                "discovery": dict(pipeline.last_metrics), "http": self.client.metrics(),
                "conditional_cache": self.cache.metrics(),
                "adaptive_sources": {name: value.metrics() for name, value in self.adaptive.items()},
                "circuit_sources": {name: value.metrics() for name, value in self.circuits.items()},
                "adaptive_batches": {name: value.metrics() for name, value in self.batch_sizers.items()},
                "streaming": {"enabled": True, "spooled_observations": spool.count},
            },
        }
        await spool.finalize(metadata)
        return metadata


async def run_discovery_config(config_path: Path | str, *, history_path: Path | str, output_path: Path | str, cache_path: Path | str | None = None) -> dict[str, Any]:
    async with CatalogRefreshEngine(config_path, history_path=history_path, output_path=output_path, cache_path=cache_path) as engine:
        return await engine.run_once()


async def run_discovery_service(
    config_path: Path | str,
    *,
    history_path: Path | str,
    output_path: Path | str,
    cache_path: Path | str | None = None,
    interval_s: float = 300.0,
    cycles: int | None = None,
) -> list[dict[str, Any]]:
    """Compatibility helper for finite/repeated service cycles over the persistent engine."""
    if interval_s < 0:
        raise ValueError("interval_s must be >= 0")
    if cycles is not None and cycles < 1:
        raise ValueError("cycles must be >= 1 when supplied")
    summaries: list[dict[str, Any]] = []
    async with CatalogRefreshEngine(config_path, history_path=history_path, output_path=output_path, cache_path=cache_path) as engine:
        while cycles is None or len(summaries) < cycles:
            started = time.monotonic()
            summaries.append(await engine.run_once())
            if cycles is not None and len(summaries) >= cycles:
                break
            delay = max(0.0, interval_s - (time.monotonic() - started))
            if delay:
                await asyncio.sleep(delay)
    return summaries
