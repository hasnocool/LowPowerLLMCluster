# src/lowpower_llm_cluster/catalog_refresh.py
from __future__ import annotations

import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable

from .discovery import ProductObservation
from .http_runtime import AdaptiveConcurrency, AsyncHttpClient, DiscoveryCache
from .streaming_discovery import (
    CachedJsonFeedAdapter,
    CachedJsonLdProductAdapter,
    StreamingDiscoveryPipeline,
)
from .history import CatalogHistory, ListingChange
from .normalization import normalize_observation
from .runtime import WorkerSettings, map_sync_bounded


def _dig(value: Any, path: str) -> Any:
    current = value
    for token in path.split(".") if path else ():
        if isinstance(current, list):
            current = current[int(token)]
        else:
            current = current[token]
    return current


def _mapped_parser(source: dict[str, Any]):
    items_path = str(source.get("items_path", ""))
    fields: dict[str, str] = dict(source.get("fields", {}))
    constants: dict[str, Any] = dict(source.get("constants", {}))
    attribute_fields: dict[str, str] = dict(source.get("attribute_fields", {}))
    source_name = str(source["name"])

    def parse(payload: Any) -> Iterable[ProductObservation]:
        items = _dig(payload, items_path) if items_path else payload
        if isinstance(items, dict):
            items = items.values()
        for raw in items:
            values = {target: _dig(raw, path) for target, path in fields.items() if path}
            values.update(constants)
            attrs = {target: _dig(raw, path) for target, path in attribute_fields.items() if path}
            listing_url = str(values.get("listing_url", ""))
            source_id = str(values.get("source_id", "")) or listing_url
            yield ProductObservation(
                source=source_name,
                source_id=source_id,
                listing_url=listing_url,
                title=str(values.get("title", "")),
                price=float(values["price"]) if values.get("price") not in (None, "") else None,
                currency=str(values.get("currency", "USD")),
                shipping=float(values["shipping"]) if values.get("shipping") not in (None, "") else None,
                seller=str(values.get("seller", "")),
                seller_rating=float(values["seller_rating"]) if values.get("seller_rating") not in (None, "") else None,
                seller_review_count=int(values["seller_review_count"]) if values.get("seller_review_count") not in (None, "") else None,
                seller_verified=bool(values["seller_verified"]) if values.get("seller_verified") is not None else None,
                manufacturer=str(values.get("manufacturer", "")),
                sku=str(values.get("sku", "")),
                mpn=str(values.get("mpn", "")),
                in_stock=bool(values["in_stock"]) if values.get("in_stock") is not None else None,
                attributes=attrs,
            )

    return parse


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _reset_spool(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _serialize_jsonl(observations: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(item, sort_keys=True, separators=(",", ":"), default=str) + "\n" for item in observations)


class ObservationSpool:
    """Append-only normalized-observation spool used to bound refresh memory."""

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
    """Reusable refresh runtime that keeps HTTP/DNS/cache/SQLite pools warm."""

    def __init__(
        self,
        config_path: Path | str,
        *,
        history_path: Path | str,
        output_path: Path | str,
        cache_path: Path | str | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.history_path = Path(history_path)
        self.output_path = Path(output_path)
        self.cache_path = Path(cache_path) if cache_path is not None else self.history_path.with_suffix(".http-cache.json")
        self.config: dict[str, Any] = {}
        self.settings: WorkerSettings | None = None
        self.client: AsyncHttpClient | None = None
        self.cache: DiscoveryCache | None = None
        self.history: CatalogHistory | None = None
        self.adapters: list[Any] = []
        self.trusts: dict[str, float] = {}
        self.adaptive: dict[str, AdaptiveConcurrency] = {}
        self._normalize_executor: ThreadPoolExecutor | None = None
        self._started = False

    async def __aenter__(self) -> "CatalogRefreshEngine":
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._started:
            return
        self.config = await asyncio.to_thread(_read_json, self.config_path)
        self.settings = WorkerSettings.from_mapping(self.config)
        self.cache = await DiscoveryCache.open(
            self.cache_path,
            max_observations_per_entry=int(self.config.get("cache_observation_limit", 5000)),
        )
        self.history = CatalogHistory(self.history_path)
        await self.history.initialize()
        self.client = AsyncHttpClient(
            concurrency=self.settings.http_concurrency,
            per_host=self.settings.http_per_host,
            timeout_s=self.settings.timeout_s,
            max_response_bytes=self.settings.max_response_bytes,
            retry_attempts=self.settings.retry_attempts,
            retry_backoff_base_s=self.settings.retry_backoff_base_s,
            retry_backoff_max_s=self.settings.retry_backoff_max_s,
            retry_jitter_s=self.settings.retry_jitter_s,
        )
        await self.client.start()
        self._normalize_executor = ThreadPoolExecutor(
            max_workers=self.settings.normalize_workers,
            thread_name_prefix="lpllm-normalize",
        )
        self.adapters = []
        self.trusts = {}
        self.adaptive = {}
        for source in list(self.config.get("sources", [])):
            source_type = str(source.get("type", "json"))
            name = str(source["name"])
            self.trusts[name] = float(source.get("source_trust", 0.65))
            max_subworkers = int(source.get("subworkers", self.settings.subworkers_per_agent)) if source_type == "jsonld" else 1
            controller = AdaptiveConcurrency(
                minimum=min(self.settings.adaptive_min_subworkers, max_subworkers),
                maximum=max_subworkers,
                initial=max_subworkers,
                success_window=self.settings.adaptive_success_window,
                latency_target_ms=self.settings.adaptive_latency_target_ms,
                enabled=self.settings.adaptive_concurrency,
            )
            self.adaptive[name] = controller
            if source_type == "json":
                self.adapters.append(
                    CachedJsonFeedAdapter(
                        name=name,
                        endpoint=str(source["endpoint"]),
                        parser=_mapped_parser(source),
                        client=self.client,
                        cache=self.cache,
                        adaptive=controller,
                        batch_size=int(source.get("batch_size", self.config.get("stream_batch_size", 256))),
                        queue_size=max(1, min(self.settings.queue_size, 32)),
                    )
                )
            elif source_type == "jsonld":
                urls = tuple(str(url) for url in source.get("urls", ()))
                if not urls:
                    raise ValueError(f"jsonld source {name!r} requires urls")
                self.adapters.append(
                    CachedJsonLdProductAdapter(
                        name=name,
                        urls=urls,
                        client=self.client,
                        subworkers=max_subworkers,
                        queue_size=self.settings.queue_size,
                        cache=self.cache,
                        adaptive=controller,
                    )
                )
            else:
                raise ValueError(f"unsupported source type {source_type!r}; built-ins are json and jsonld")
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

    async def run_once(self) -> dict[str, Any]:
        await self.start()
        assert self.settings is not None and self.client is not None and self.cache is not None and self.history is not None and self._normalize_executor is not None
        pipeline_started = time.perf_counter()
        run_id = await self.history.begin_refresh()
        spool = ObservationSpool(self.output_path)
        await spool.reset()
        seen_by_source: dict[str, set[str]] = {}
        changes: list[ListingChange] = []
        normalize_ms = 0.0
        persist_ms = 0.0
        pipeline = StreamingDiscoveryPipeline(
            self.adapters,
            worker_count=self.settings.agent_workers,
            queue_size=self.settings.queue_size,
        )

        try:
            discovery_started = time.perf_counter()
            async for batch in pipeline.stream():
                if batch.error:
                    continue
                seen = seen_by_source.setdefault(batch.source, set())
                for item in batch.observations:
                    seen.add(item.source_id)

                def normalize(item: ProductObservation) -> dict[str, Any]:
                    return normalize_observation(item, source_trust=self.trusts.get(item.source, 0.65))

                batch_started = time.perf_counter()
                async with asyncio.TaskGroup() as group:
                    persist_task = group.create_task(self.history.record_batch(run_id, batch.observations))
                    normalize_task = group.create_task(
                        map_sync_bounded(
                            batch.observations,
                            normalize,
                            workers=self.settings.normalize_workers,
                            queue_size=self.settings.queue_size,
                            thread_name_prefix="lpllm-normalize",
                            executor=self._normalize_executor,
                        )
                    )
                elapsed = (time.perf_counter() - batch_started) * 1000.0
                normalize_ms += elapsed
                persist_ms += elapsed
                changes.extend(persist_task.result())
                await spool.append(normalize_task.result())

            discovery_ms = round((time.perf_counter() - discovery_started) * 1000.0, 3)
            successful_sources = [adapter.name for adapter in self.adapters if adapter.name not in pipeline.last_errors]
            changes.extend(
                await self.history.finish_refresh(
                    run_id,
                    source_names=successful_sources,
                    seen_by_source=seen_by_source,
                    disappearance_after_runs=int(self.config.get("disappearance_after_runs", 2)),
                )
            )
            await self.cache.flush()
        except BaseException:
            await self.history.abort_refresh(run_id)
            raise

        metadata: dict[str, Any] = {
            "run_id": run_id,
            "observation_count": spool.count,
            "errors": dict(pipeline.last_errors),
            "changes": [
                {
                    "source": change.source,
                    "source_id": change.source_id,
                    "change_type": change.change_type,
                    "previous": change.previous,
                    "current": change.current,
                }
                for change in changes
            ],
            "runtime": {
                "workers": self.settings.to_dict(),
                "discovery_ms": discovery_ms,
                "normalize_wall_ms": round(normalize_ms, 3),
                "persist_wall_ms": round(persist_ms, 3),
                "total_ms": round((time.perf_counter() - pipeline_started) * 1000.0, 3),
                "discovery": dict(pipeline.last_metrics),
                "http": self.client.metrics(),
                "conditional_cache": self.cache.metrics(),
                "adaptive_sources": {name: limiter.metrics() for name, limiter in self.adaptive.items()},
                "streaming": {"enabled": True, "spooled_observations": spool.count},
            },
        }
        await spool.finalize(metadata)
        return metadata


async def run_discovery_config(
    config_path: Path | str,
    *,
    history_path: Path | str,
    output_path: Path | str,
    cache_path: Path | str | None = None,
) -> dict[str, Any]:
    async with CatalogRefreshEngine(
        config_path,
        history_path=history_path,
        output_path=output_path,
        cache_path=cache_path,
    ) as engine:
        return await engine.run_once()


async def run_discovery_service(
    config_path: Path | str,
    *,
    history_path: Path | str,
    output_path: Path | str,
    cache_path: Path | str | None = None,
    interval_s: float = 300.0,
    cycles: int | None = None,
    stop_event: asyncio.Event | None = None,
) -> list[dict[str, Any]]:
    """Run repeated refreshes while reusing HTTP/DNS/cache/SQLite resources."""
    if interval_s <= 0:
        raise ValueError("interval_s must be > 0")
    if cycles is not None and cycles < 1:
        raise ValueError("cycles must be >= 1 when supplied")
    summaries: list[dict[str, Any]] = []
    async with CatalogRefreshEngine(
        config_path,
        history_path=history_path,
        output_path=output_path,
        cache_path=cache_path,
    ) as engine:
        completed = 0
        while cycles is None or completed < cycles:
            cycle_started = time.monotonic()
            summaries.append(await engine.run_once())
            if len(summaries) > 100:
                del summaries[:-100]
            completed += 1
            if cycles is not None and completed >= cycles:
                break
            delay = max(0.0, interval_s - (time.monotonic() - cycle_started))
            if stop_event is None:
                await asyncio.sleep(delay)
            else:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=delay)
                    break
                except TimeoutError:
                    pass
    return summaries
