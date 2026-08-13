# src/lowpower_llm_cluster/runtime.py
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
    """Bounded hierarchy used by the end-to-end catalog pipeline."""

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

    def __post_init__(self) -> None:
        positive_ints = {
            "agent_workers": self.agent_workers,
            "subworkers_per_agent": self.subworkers_per_agent,
            "normalize_workers": self.normalize_workers,
            "queue_size": self.queue_size,
            "http_concurrency": self.http_concurrency,
            "http_per_host": self.http_per_host,
            "max_response_bytes": self.max_response_bytes,
            "retry_attempts": self.retry_attempts,
            "adaptive_min_subworkers": self.adaptive_min_subworkers,
            "adaptive_success_window": self.adaptive_success_window,
        }
        for name, value in positive_ints.items():
            if value < 1:
                raise ValueError(f"{name} must be >= 1")
        if self.timeout_s <= 0 or self.retry_backoff_base_s < 0 or self.retry_backoff_max_s < 0 or self.retry_jitter_s < 0:
            raise ValueError("timeouts/backoff/jitter must be non-negative and timeout must be positive")
        if self.adaptive_latency_target_ms <= 0:
            raise ValueError("adaptive_latency_target_ms must be > 0")
        if self.http_per_host > self.http_concurrency:
            raise ValueError("http_per_host cannot exceed http_concurrency")
        if self.adaptive_min_subworkers > self.subworkers_per_agent:
            raise ValueError("adaptive_min_subworkers cannot exceed subworkers_per_agent")

    @classmethod
    def from_mapping(cls, raw: dict[str, object]) -> "WorkerSettings":
        http_concurrency = int(raw.get("http_concurrency", raw.get("concurrency", 16)))
        http_per_host = int(raw.get("http_per_host", min(4, http_concurrency)))
        return cls(
            agent_workers=int(raw.get("agent_workers", 4)),
            subworkers_per_agent=int(raw.get("subworkers_per_agent", 4)),
            normalize_workers=int(raw.get("normalize_workers", _default_cpu_workers())),
            queue_size=int(raw.get("queue_size", 64)),
            http_concurrency=http_concurrency,
            http_per_host=http_per_host,
            timeout_s=float(raw.get("timeout_s", 20.0)),
            max_response_bytes=int(raw.get("max_response_bytes", 8 * 1024 * 1024)),
            retry_attempts=int(raw.get("retry_attempts", 3)),
            retry_backoff_base_s=float(raw.get("retry_backoff_base_s", 0.5)),
            retry_backoff_max_s=float(raw.get("retry_backoff_max_s", 15.0)),
            retry_jitter_s=float(raw.get("retry_jitter_s", 0.25)),
            adaptive_concurrency=bool(raw.get("adaptive_concurrency", True)),
            adaptive_min_subworkers=int(raw.get("adaptive_min_subworkers", 1)),
            adaptive_success_window=int(raw.get("adaptive_success_window", 8)),
            adaptive_latency_target_ms=float(raw.get("adaptive_latency_target_ms", 1500.0)),
        )

    def to_dict(self) -> dict[str, int | float | bool]:
        return {
            "agent_workers": self.agent_workers,
            "subworkers_per_agent": self.subworkers_per_agent,
            "normalize_workers": self.normalize_workers,
            "queue_size": self.queue_size,
            "http_concurrency": self.http_concurrency,
            "http_per_host": self.http_per_host,
            "timeout_s": self.timeout_s,
            "max_response_bytes": self.max_response_bytes,
            "retry_attempts": self.retry_attempts,
            "retry_backoff_base_s": self.retry_backoff_base_s,
            "retry_backoff_max_s": self.retry_backoff_max_s,
            "retry_jitter_s": self.retry_jitter_s,
            "adaptive_concurrency": self.adaptive_concurrency,
            "adaptive_min_subworkers": self.adaptive_min_subworkers,
            "adaptive_success_window": self.adaptive_success_window,
            "adaptive_latency_target_ms": self.adaptive_latency_target_ms,
        }


async def map_sync_bounded_iter(
    items: Iterable[T],
    func: Callable[[T], R],
    *,
    workers: int,
    queue_size: int = 64,
    thread_name_prefix: str = "lpllm-worker",
    executor: Executor | None = None,
) -> AsyncIterator[tuple[int, R]]:
    """Stream synchronous transforms off-loop with fixed workers/backpressure.

    Results are yielded as workers finish and include the input index so callers can
    restore ordering if required. The input iterable is not materialized.
    """
    if workers < 1 or queue_size < 1:
        raise ValueError("workers and queue_size must be >= 1")
    loop = asyncio.get_running_loop()
    owned_executor = executor is None
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
        for _ in range(workers):
            tasks.append(asyncio.create_task(worker()))
        finished_workers = 0
        while finished_workers < workers:
            value = await output_queue.get()
            if value is None:
                finished_workers += 1
                continue
            if isinstance(value, BaseException):
                raise value
            yield value
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if owned_executor and isinstance(executor, ThreadPoolExecutor):
            executor.shutdown(wait=False, cancel_futures=True)


async def map_sync_bounded(
    items: Iterable[T],
    func: Callable[[T], R],
    *,
    workers: int,
    queue_size: int = 64,
    thread_name_prefix: str = "lpllm-worker",
    executor: Executor | None = None,
) -> list[R]:
    """Ordered compatibility wrapper over the streaming bounded worker map."""
    indexed: list[tuple[int, R]] = []
    async for item in map_sync_bounded_iter(
        items,
        func,
        workers=workers,
        queue_size=queue_size,
        thread_name_prefix=thread_name_prefix,
        executor=executor,
    ):
        indexed.append(item)
    indexed.sort(key=lambda pair: pair[0])
    return [cast(R, value) for _, value in indexed]
