# src/lowpower_llm_cluster/runtime.py
from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import Callable, Iterable, TypeVar, cast

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

    def __post_init__(self) -> None:
        positive_ints = {
            "agent_workers": self.agent_workers,
            "subworkers_per_agent": self.subworkers_per_agent,
            "normalize_workers": self.normalize_workers,
            "queue_size": self.queue_size,
            "http_concurrency": self.http_concurrency,
            "http_per_host": self.http_per_host,
            "max_response_bytes": self.max_response_bytes,
        }
        for name, value in positive_ints.items():
            if value < 1:
                raise ValueError(f"{name} must be >= 1")
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be > 0")
        if self.http_per_host > self.http_concurrency:
            raise ValueError("http_per_host cannot exceed http_concurrency")

    @classmethod
    def from_mapping(cls, raw: dict[str, object]) -> "WorkerSettings":
        # Backwards compatible with the v0.5 `concurrency`/`timeout_s` keys.
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
        )

    def to_dict(self) -> dict[str, int | float]:
        return {
            "agent_workers": self.agent_workers,
            "subworkers_per_agent": self.subworkers_per_agent,
            "normalize_workers": self.normalize_workers,
            "queue_size": self.queue_size,
            "http_concurrency": self.http_concurrency,
            "http_per_host": self.http_per_host,
            "timeout_s": self.timeout_s,
            "max_response_bytes": self.max_response_bytes,
        }


async def map_sync_bounded(
    items: Iterable[T],
    func: Callable[[T], R],
    *,
    workers: int,
    queue_size: int = 64,
    thread_name_prefix: str = "lpllm-worker",
) -> list[R]:
    """Run synchronous CPU/file transforms off-loop with fixed workers/backpressure.

    Unlike creating one task per item, this keeps task count and memory bounded. The
    dedicated executor also prevents parser/normalizer work from starving asyncio's
    global executor, which may be needed by DNS or unrelated application code.
    """
    if workers < 1 or queue_size < 1:
        raise ValueError("workers and queue_size must be >= 1")
    materialized = tuple(items)
    if not materialized:
        return []

    loop = asyncio.get_running_loop()
    worker_count = min(workers, len(materialized))
    executor = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix=thread_name_prefix)
    queue: asyncio.Queue[tuple[int, T] | None] = asyncio.Queue(maxsize=queue_size)
    missing = object()
    results: list[object] = [missing] * len(materialized)

    async def producer() -> None:
        for index, item in enumerate(materialized):
            await queue.put((index, item))
        for _ in range(worker_count):
            await queue.put(None)

    async def worker() -> None:
        while True:
            entry = await queue.get()
            try:
                if entry is None:
                    return
                index, item = entry
                results[index] = await loop.run_in_executor(executor, partial(func, item))
            finally:
                queue.task_done()

    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(producer())
            for _ in range(worker_count):
                group.create_task(worker())
    finally:
        # All submitted work is complete before this point, so non-waiting shutdown is
        # immediate and does not stall the event loop.
        executor.shutdown(wait=False, cancel_futures=True)

    if any(item is missing for item in results):
        raise RuntimeError("bounded worker map completed with missing results")
    return [cast(R, item) for item in results]
