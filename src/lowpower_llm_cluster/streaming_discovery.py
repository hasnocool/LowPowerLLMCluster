# src/lowpower_llm_cluster/streaming_discovery.py
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Iterable, Sequence

from .discovery import ProductObservation, _parse_jsonld_page
from .http_runtime import AdaptiveConcurrency, AsyncHttpClient, DiscoveryCache

JsonParser = Callable[[Any], Iterable[ProductObservation]]


@dataclass(slots=True)
class CachedJsonFeedAdapter:
    """JSON feed adapter that streams parsed observation batches with backpressure."""

    name: str
    endpoint: str
    parser: JsonParser
    client: AsyncHttpClient
    cache: DiscoveryCache
    adaptive: AdaptiveConcurrency
    batch_size: int = 256
    queue_size: int = 8

    async def discover_batches(self) -> AsyncIterator[Sequence[ProductObservation]]:
        if self.batch_size < 1 or self.queue_size < 1:
            raise ValueError("batch_size and queue_size must be >= 1")
        response = await self.client.get_response(
            self.endpoint,
            validators=self.cache.validators(self.endpoint),
            source=self.name,
            adaptive=self.adaptive,
        )
        if response.not_modified:
            cached = self.cache.observations(self.endpoint) or ()
            if cached:
                self.cache.note_hit(self.endpoint)
            for start in range(0, len(cached), self.batch_size):
                yield cached[start : start + self.batch_size]
            return

        text = await asyncio.to_thread(response.payload.decode, "utf-8", "replace")
        payload = await asyncio.to_thread(json.loads, text)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[ProductObservation, ...] | BaseException | None] = asyncio.Queue(
            maxsize=self.queue_size
        )
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
                    if len(batch) >= self.batch_size:
                        asyncio.run_coroutine_threadsafe(queue.put(tuple(batch)), loop).result()
                        batch = []
                if batch:
                    asyncio.run_coroutine_threadsafe(queue.put(tuple(batch)), loop).result()
            except BaseException as exc:
                asyncio.run_coroutine_threadsafe(queue.put(exc), loop).result()
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

        worker_task = asyncio.create_task(asyncio.to_thread(parse_worker))
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
            await worker_task
            await self.cache.store(self.endpoint, response, cached_records)
        finally:
            if not worker_task.done():
                worker_task.cancel()
            await asyncio.gather(worker_task, return_exceptions=True)

    async def discover(self) -> Sequence[ProductObservation]:
        result: list[ProductObservation] = []
        async for batch in self.discover_batches():
            result.extend(batch)
        return result


@dataclass(slots=True)
class CachedJsonLdProductAdapter:
    """JSON-LD adapter with conditional cache reuse and bounded URL subworkers."""

    name: str
    urls: Sequence[str]
    client: AsyncHttpClient
    cache: DiscoveryCache
    adaptive: AdaptiveConcurrency
    subworkers: int = 4
    queue_size: int = 64

    async def _one(self, url: str) -> list[ProductObservation]:
        response = await self.client.get_response(
            url,
            validators=self.cache.validators(url),
            source=self.name,
            adaptive=self.adaptive,
        )
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
        if self.subworkers < 1 or self.queue_size < 1:
            raise ValueError("subworkers and queue_size must be >= 1")
        workers = min(self.subworkers, max(1, len(self.urls)))
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=self.queue_size)
        out: asyncio.Queue[list[ProductObservation] | BaseException | None] = asyncio.Queue(
            maxsize=self.queue_size
        )

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
                        await out.put(None)
                        return
                    try:
                        await out.put(await self._one(url))
                    except BaseException as exc:
                        await out.put(exc)
                finally:
                    queue.task_done()

        async with asyncio.TaskGroup() as group:
            group.create_task(producer())
            for _ in range(workers):
                group.create_task(worker())
            done = 0
            first_error: BaseException | None = None
            while done < workers:
                item = await out.get()
                if item is None:
                    done += 1
                elif isinstance(item, BaseException):
                    first_error = first_error or item
                elif item:
                    yield item
            if first_error:
                raise first_error

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
    """Source-agent pool that streams deduplicated batches instead of whole refreshes."""

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
        out: asyncio.Queue[DiscoveryBatch | tuple[str, float] | None] = asyncio.Queue(
            maxsize=self.queue_size
        )
        seen: dict[str, set[tuple[str, str]]] = {}
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
                        await out.put(None)
                        return
                    source_started = time.perf_counter()
                    try:
                        async for batch in adapter.discover_batches():
                            await out.put(DiscoveryBatch(adapter.name, tuple(batch)))
                    except Exception as exc:
                        await out.put(
                            DiscoveryBatch(adapter.name, (), f"{type(exc).__name__}: {exc}")
                        )
                    finally:
                        await out.put(
                            (
                                adapter.name,
                                round((time.perf_counter() - source_started) * 1000.0, 3),
                            )
                        )
                finally:
                    queue.task_done()

        async with asyncio.TaskGroup() as group:
            group.create_task(producer())
            for _ in range(workers):
                group.create_task(agent())
            finished = 0
            while finished < workers:
                item = await out.get()
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
                source_seen = seen.setdefault(item.source, set())
                unique: list[ProductObservation] = []
                for observation in item.observations:
                    if observation.identity not in source_seen:
                        source_seen.add(observation.identity)
                        unique.append(observation)
                if unique:
                    yield DiscoveryBatch(item.source, tuple(unique))

        self.last_errors = errors
        self.last_metrics = {
            "agent_workers": self.worker_count,
            "source_count": len(self.adapters),
            "sources_succeeded": len(self.adapters) - len(errors),
            "sources_failed": len(errors),
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "source_durations_ms": durations,
            "streamed_identity_count": sum(map(len, seen.values())),
        }
