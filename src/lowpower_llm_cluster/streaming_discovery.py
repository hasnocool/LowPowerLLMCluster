from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Iterable, Sequence

from .discovery import ProductObservation
from .http_runtime import AdaptiveConcurrency, AsyncHttpClient, DiscoveryCache
from .resilience_runtime import AdaptiveBatchSizer, CircuitBreaker

JsonParser = Callable[[Any], Iterable[ProductObservation]]
ItemParser = Callable[[Any], ProductObservation]


@dataclass(slots=True)
class CachedJsonFeedAdapter:
    name: str
    endpoint: str
    parser: JsonParser
    client: AsyncHttpClient
    cache: DiscoveryCache
    adaptive: AdaptiveConcurrency
    batch_size: int = 256
    queue_size: int = 8
    batch_sizer: AdaptiveBatchSizer | None = None

    async def discover_batches(self) -> AsyncIterator[Sequence[ProductObservation]]:
        response = await self.client.get_response(self.endpoint, validators=self.cache.validators(self.endpoint), source=self.name, adaptive=self.adaptive)
        if response.not_modified:
            cached = self.cache.observations(self.endpoint) or ()
            if cached:
                self.cache.note_hit(self.endpoint)
            size = self.batch_sizer.current if self.batch_sizer else self.batch_size
            for start in range(0, len(cached), max(1, size)):
                yield cached[start:start + max(1, size)]
            return
        text = await asyncio.to_thread(response.payload.decode, "utf-8", "replace")
        payload = await asyncio.to_thread(json.loads, text)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[ProductObservation, ...] | BaseException | None] = asyncio.Queue(maxsize=self.queue_size)
        cache_limit = self.cache.max_observations_per_entry
        cached_records: list[ProductObservation] = []

        def parse_worker() -> None:
            batch: list[ProductObservation] = []
            cacheable = True
            try:
                for record in self.parser(payload):
                    batch.append(record)
                    if cacheable:
                        if len(cached_records) < cache_limit:
                            cached_records.append(record)
                        else:
                            cached_records.clear()
                            cacheable = False
                    target = self.batch_sizer.current if self.batch_sizer else self.batch_size
                    if len(batch) >= target:
                        asyncio.run_coroutine_threadsafe(queue.put(tuple(batch)), loop).result()
                        batch = []
                if batch:
                    asyncio.run_coroutine_threadsafe(queue.put(tuple(batch)), loop).result()
            except BaseException as exc:
                asyncio.run_coroutine_threadsafe(queue.put(exc), loop).result()
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

        task = asyncio.create_task(asyncio.to_thread(parse_worker))
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
            await task
            await self.cache.store(self.endpoint, response, cached_records)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def discover(self) -> Sequence[ProductObservation]:
        result: list[ProductObservation] = []
        async for batch in self.discover_batches():
            result.extend(batch)
        return result


@dataclass(slots=True)
class StreamingJsonFeedAdapter:
    name: str
    endpoint: str
    items_prefix: str
    item_parser: ItemParser
    client: AsyncHttpClient
    adaptive: AdaptiveConcurrency
    batch_size: int = 256
    batch_sizer: AdaptiveBatchSizer | None = None

    async def discover_batches(self) -> AsyncIterator[Sequence[ProductObservation]]:
        batch: list[Any] = []
        async for raw in self.client.iter_json_items(self.endpoint, prefix=self.items_prefix, source=self.name, adaptive=self.adaptive):
            batch.append(raw)
            target = self.batch_sizer.current if self.batch_sizer else self.batch_size
            if len(batch) >= target:
                ready = tuple(batch)
                batch = []
                yield await asyncio.to_thread(lambda: tuple(self.item_parser(item) for item in ready))
        if batch:
            ready = tuple(batch)
            yield await asyncio.to_thread(lambda: tuple(self.item_parser(item) for item in ready))

    async def discover(self) -> Sequence[ProductObservation]:
        result: list[ProductObservation] = []
        async for batch in self.discover_batches():
            result.extend(batch)
        return result


@dataclass(slots=True)
class CachedJsonLdProductAdapter:
    name: str
    urls: Sequence[str]
    client: AsyncHttpClient
    cache: DiscoveryCache
    adaptive: AdaptiveConcurrency
    subworkers: int = 4
    queue_size: int = 64
    batch_sizer: AdaptiveBatchSizer | None = None

    async def _one(self, url: str) -> list[ProductObservation]:
        from .discovery import _parse_jsonld_page
        response = await self.client.get_response(url, validators=self.cache.validators(url), source=self.name, adaptive=self.adaptive)
        if response.not_modified:
            cached = self.cache.observations(url)
            if cached is not None:
                self.cache.note_hit(url)
                return list(cached)
        text = await asyncio.to_thread(response.payload.decode, "utf-8", "replace")
        records = await asyncio.to_thread(_parse_jsonld_page, self.name, url, text)
        await self.cache.store(url, response, records)
        return records

    async def discover_batches(self) -> AsyncIterator[Sequence[ProductObservation]]:
        workers = min(self.subworkers, max(1, len(self.urls)))
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=self.queue_size)
        output: asyncio.Queue[list[ProductObservation] | BaseException | None] = asyncio.Queue(maxsize=self.queue_size)

        async def producer() -> None:
            for url in self.urls:
                await queue.put(url)
            for _ in range(workers):
                await queue.put(None)

        async def worker() -> None:
            while True:
                url = await queue.get()
                try:
                    if url is None:
                        await output.put(None)
                        return
                    try:
                        await output.put(await self._one(url))
                    except BaseException as exc:
                        await output.put(exc)
                finally:
                    queue.task_done()

        async with asyncio.TaskGroup() as group:
            group.create_task(producer())
            for _ in range(workers):
                group.create_task(worker())
            done = 0
            first_error: BaseException | None = None
            while done < workers:
                item = await output.get()
                if item is None:
                    done += 1
                elif isinstance(item, BaseException):
                    first_error = first_error or item
                elif item:
                    size = self.batch_sizer.current if self.batch_sizer else len(item)
                    for start in range(0, len(item), max(1, size)):
                        yield item[start:start + max(1, size)]
            if first_error:
                raise first_error

    async def discover(self) -> Sequence[ProductObservation]:
        result: list[ProductObservation] = []
        async for batch in self.discover_batches():
            result.extend(batch)
        return result


@dataclass(slots=True)
class CircuitProtectedAdapter:
    name: str
    inner: Any
    circuit: CircuitBreaker

    async def discover_batches(self) -> AsyncIterator[Sequence[ProductObservation]]:
        await self.circuit.acquire()
        try:
            async for batch in self.inner.discover_batches():
                yield batch
        except asyncio.CancelledError:
            await self.circuit.cancel()
            raise
        except Exception:
            await self.circuit.failure()
            raise
        else:
            await self.circuit.success()

    async def discover(self) -> Sequence[ProductObservation]:
        result: list[ProductObservation] = []
        async for batch in self.discover_batches():
            result.extend(batch)
        return result


@dataclass(frozen=True, slots=True)
class DiscoveryBatch:
    source: str
    observations: tuple[ProductObservation, ...] = ()
    error: str = ""


class StreamingDiscoveryPipeline:
    def __init__(self, adapters: Sequence[Any], *, worker_count: int = 4, queue_size: int = 64) -> None:
        if worker_count < 1 or queue_size < 1:
            raise ValueError("worker_count and queue_size must be >= 1")
        self.adapters = tuple(adapters)
        self.worker_count = worker_count
        self.queue_size = queue_size
        self.last_errors: dict[str, str] = {}
        self.last_metrics: dict[str, Any] = {}

    async def stream(self) -> AsyncIterator[DiscoveryBatch]:
        started = time.perf_counter()
        workers = min(self.worker_count, max(1, len(self.adapters)))
        queue: asyncio.Queue[Any | None] = asyncio.Queue(maxsize=self.queue_size)
        output: asyncio.Queue[DiscoveryBatch | tuple[str, float] | None] = asyncio.Queue(maxsize=self.queue_size)
        seen: dict[str, set[tuple[str, str]]] = {}
        raw_counts: dict[str, int] = {}
        unique_counts: dict[str, int] = {}
        errors: dict[str, str] = {}
        durations: dict[str, float] = {}

        async def producer() -> None:
            for adapter in self.adapters:
                await queue.put(adapter)
            for _ in range(workers):
                await queue.put(None)

        async def agent() -> None:
            while True:
                adapter = await queue.get()
                try:
                    if adapter is None:
                        await output.put(None)
                        return
                    source_started = time.perf_counter()
                    try:
                        async for batch in adapter.discover_batches():
                            await output.put(DiscoveryBatch(adapter.name, tuple(batch)))
                    except Exception as exc:
                        await output.put(DiscoveryBatch(adapter.name, (), f"{type(exc).__name__}: {exc}"))
                    finally:
                        await output.put((adapter.name, round((time.perf_counter() - source_started) * 1000, 3)))
                finally:
                    queue.task_done()

        async with asyncio.TaskGroup() as group:
            group.create_task(producer())
            for _ in range(workers):
                group.create_task(agent())
            finished = 0
            while finished < workers:
                item = await output.get()
                if item is None:
                    finished += 1
                    continue
                if isinstance(item, tuple):
                    durations[item[0]] = item[1]
                    continue
                if item.error:
                    errors[item.source] = item.error
                    yield item
                    continue
                raw_counts[item.source] = raw_counts.get(item.source, 0) + len(item.observations)
                source_seen = seen.setdefault(item.source, set())
                unique: list[ProductObservation] = []
                for observation in item.observations:
                    if observation.identity not in source_seen:
                        source_seen.add(observation.identity)
                        unique.append(observation)
                unique_counts[item.source] = unique_counts.get(item.source, 0) + len(unique)
                if unique:
                    yield DiscoveryBatch(item.source, tuple(unique))
        self.last_errors = errors
        duplicate_rates = {
            source: round(1.0 - (unique_counts.get(source, 0) / max(1, raw)), 6)
            for source, raw in raw_counts.items()
        }
        self.last_metrics = {
            "agent_workers": self.worker_count,
            "source_count": len(self.adapters),
            "sources_succeeded": len(self.adapters) - len(errors),
            "sources_failed": len(errors),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "source_durations_ms": durations,
            "source_raw_observations": raw_counts,
            "source_unique_observations": unique_counts,
            "source_duplicate_rates": duplicate_rates,
            "streamed_identity_count": sum(map(len, seen.values())),
        }
