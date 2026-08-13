from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import Callable, TypeVar, cast

T = TypeVar("T")
R = TypeVar("R")


def _default_cpu_workers() -> int:
    return max(1, min(4, os.cpu_count() or 1))


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    agent_workers: int = 4
    subworkers_per_agent: int = 4
    normalize_workers: int = _default_cpu_workers()
    queue_size: int = 64
    http_concurrency: int = 16
    http_per_host: int = 4
    timeout_s: float = 20.0
    max_response_bytes: int = 8 * 1024 * 1024
    retry_attempts: int = 3
    retry_backoff_base_s: float = 0.5
    retry_backoff_max_s: float = 15.0
    retry_jitter_s: float = 0.25
    adaptive_concurrency: bool = True
    adaptive_min_subworkers: int = 1
    adaptive_success_window: int = 8
    adaptive_latency_target_ms: float = 1500.0
    circuit_breaker: bool = True
    circuit_failure_threshold: int = 4
    circuit_recovery_timeout_s: float = 120.0
    circuit_half_open_calls: int = 1
    adaptive_batching: bool = True
    adaptive_batch_min: int = 64
    adaptive_batch_max: int = 2048
    adaptive_batch_initial: int = 256
    adaptive_batch_target_ms: float = 250.0
    adaptive_batch_rss_soft_limit_mb: float = 1024.0
    adaptive_batch_success_window: int = 4
    cache_ttl_s: float = 604800.0
    cache_max_entries: int = 10000
    cache_compress: bool = False

    def __post_init__(self) -> None:
        positive = {
            "agent_workers": self.agent_workers, "subworkers_per_agent": self.subworkers_per_agent,
            "normalize_workers": self.normalize_workers, "queue_size": self.queue_size,
            "http_concurrency": self.http_concurrency, "http_per_host": self.http_per_host,
            "max_response_bytes": self.max_response_bytes, "retry_attempts": self.retry_attempts,
            "adaptive_min_subworkers": self.adaptive_min_subworkers,
            "adaptive_success_window": self.adaptive_success_window,
            "circuit_failure_threshold": self.circuit_failure_threshold,
            "circuit_half_open_calls": self.circuit_half_open_calls,
            "adaptive_batch_min": self.adaptive_batch_min, "adaptive_batch_max": self.adaptive_batch_max,
            "adaptive_batch_initial": self.adaptive_batch_initial,
            "adaptive_batch_success_window": self.adaptive_batch_success_window,
            "cache_max_entries": self.cache_max_entries,
        }
        for name, value in positive.items():
            if value < 1:
                raise ValueError(f"{name} must be >= 1")
        if self.timeout_s <= 0 or min(self.retry_backoff_base_s, self.retry_backoff_max_s, self.retry_jitter_s) < 0:
            raise ValueError("timeouts/backoff/jitter invalid")
        if min(self.adaptive_latency_target_ms, self.circuit_recovery_timeout_s, self.adaptive_batch_target_ms, self.adaptive_batch_rss_soft_limit_mb, self.cache_ttl_s) <= 0:
            raise ValueError("runtime targets must be positive")
        if self.http_per_host > self.http_concurrency:
            raise ValueError("http_per_host cannot exceed http_concurrency")
        if self.adaptive_min_subworkers > self.subworkers_per_agent:
            raise ValueError("adaptive_min_subworkers cannot exceed subworkers_per_agent")
        if not self.adaptive_batch_min <= self.adaptive_batch_initial <= self.adaptive_batch_max:
            raise ValueError("adaptive batch initial must lie within min/max")

    @classmethod
    def from_mapping(cls, raw: dict[str, object]) -> "WorkerSettings":
        http_concurrency = int(raw.get("http_concurrency", raw.get("concurrency", 16)))
        return cls(
            agent_workers=int(raw.get("agent_workers", 4)), subworkers_per_agent=int(raw.get("subworkers_per_agent", 4)),
            normalize_workers=int(raw.get("normalize_workers", _default_cpu_workers())), queue_size=int(raw.get("queue_size", 64)),
            http_concurrency=http_concurrency, http_per_host=int(raw.get("http_per_host", min(4, http_concurrency))),
            timeout_s=float(raw.get("timeout_s", 20)), max_response_bytes=int(raw.get("max_response_bytes", 8 * 1024 * 1024)),
            retry_attempts=int(raw.get("retry_attempts", 3)), retry_backoff_base_s=float(raw.get("retry_backoff_base_s", 0.5)),
            retry_backoff_max_s=float(raw.get("retry_backoff_max_s", 15)), retry_jitter_s=float(raw.get("retry_jitter_s", 0.25)),
            adaptive_concurrency=bool(raw.get("adaptive_concurrency", True)), adaptive_min_subworkers=int(raw.get("adaptive_min_subworkers", 1)),
            adaptive_success_window=int(raw.get("adaptive_success_window", 8)), adaptive_latency_target_ms=float(raw.get("adaptive_latency_target_ms", 1500)),
            circuit_breaker=bool(raw.get("circuit_breaker", True)), circuit_failure_threshold=int(raw.get("circuit_failure_threshold", 4)),
            circuit_recovery_timeout_s=float(raw.get("circuit_recovery_timeout_s", 120)), circuit_half_open_calls=int(raw.get("circuit_half_open_calls", 1)),
            adaptive_batching=bool(raw.get("adaptive_batching", True)), adaptive_batch_min=int(raw.get("adaptive_batch_min", 64)),
            adaptive_batch_max=int(raw.get("adaptive_batch_max", 2048)), adaptive_batch_initial=int(raw.get("adaptive_batch_initial", raw.get("stream_batch_size", 256))),
            adaptive_batch_target_ms=float(raw.get("adaptive_batch_target_ms", 250)), adaptive_batch_rss_soft_limit_mb=float(raw.get("adaptive_batch_rss_soft_limit_mb", 1024)),
            adaptive_batch_success_window=int(raw.get("adaptive_batch_success_window", 4)), cache_ttl_s=float(raw.get("cache_ttl_s", 604800)),
            cache_max_entries=int(raw.get("cache_max_entries", 10000)), cache_compress=bool(raw.get("cache_compress", False)),
        )

    def to_dict(self) -> dict[str, int | float | bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


async def map_sync_bounded_iter(items: Iterable[T], func: Callable[[T], R], *, workers: int, queue_size: int = 64, thread_name_prefix: str = "lpllm-worker", executor: Executor | None = None) -> AsyncIterator[tuple[int, R]]:
    if workers < 1 or queue_size < 1:
        raise ValueError("workers and queue_size must be >= 1")
    loop = asyncio.get_running_loop()
    owned = executor is None
    executor = executor or ThreadPoolExecutor(max_workers=workers, thread_name_prefix=thread_name_prefix)
    input_queue: asyncio.Queue[tuple[int, T] | None] = asyncio.Queue(maxsize=queue_size)
    output_queue: asyncio.Queue[tuple[int, R] | BaseException | None] = asyncio.Queue(maxsize=queue_size)

    async def producer() -> None:
        try:
            for index, item in enumerate(items):
                await input_queue.put((index, item))
        except BaseException as exc:
            await output_queue.put(exc)
        finally:
            for _ in range(workers):
                await input_queue.put(None)

    async def worker() -> None:
        while True:
            entry = await input_queue.get()
            try:
                if entry is None:
                    await output_queue.put(None)
                    return
                index, item = entry
                result = await loop.run_in_executor(executor, partial(func, item))
                await output_queue.put((index, result))
            except BaseException as exc:
                await output_queue.put(exc)
                return
            finally:
                input_queue.task_done()

    tasks: list[asyncio.Task[None]] = []
    try:
        tasks.append(asyncio.create_task(producer()))
        tasks.extend(asyncio.create_task(worker()) for _ in range(workers))
        finished = 0
        while finished < workers:
            value = await output_queue.get()
            if value is None:
                finished += 1
                continue
            if isinstance(value, BaseException):
                raise value
            yield value
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if owned and isinstance(executor, ThreadPoolExecutor):
            executor.shutdown(wait=False, cancel_futures=True)


async def map_sync_bounded(items: Iterable[T], func: Callable[[T], R], *, workers: int, queue_size: int = 64, thread_name_prefix: str = "lpllm-worker", executor: Executor | None = None) -> list[R]:
    indexed: list[tuple[int, R]] = []
    async for item in map_sync_bounded_iter(items, func, workers=workers, queue_size=queue_size, thread_name_prefix=thread_name_prefix, executor=executor):
        indexed.append(item)
    indexed.sort(key=lambda pair: pair[0])
    return [cast(R, value) for _, value in indexed]
