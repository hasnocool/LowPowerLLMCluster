from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import socket
import time
from pathlib import Path
from typing import Any, AsyncIterator, Sequence

from .catalog_refresh import ObservationSpool
from .discovery import ProductObservation
from .distributed_runtime import CoordinatorClient, CoordinatorHttpServer, DistributedTaskStore, DistributedWorker
from .history import CatalogHistory
from .http_runtime import AdaptiveConcurrency, AsyncHttpClient, DiscoveryCache
from .normalization import normalize_observation
from .resilience_runtime import AdaptiveBatchSizer, CircuitBreaker
from .runtime import WorkerSettings
from .source_runtime import build_source_adapter


def _read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _pretty(value: Any) -> str:
    return json.dumps(value, indent=2)


class RemoteExecutor:
    def __init__(self, config: dict[str, Any], cache_path: str) -> None:
        self.config = config
        self.settings = WorkerSettings.from_mapping(config)
        self.cache_path = cache_path
        self.client: AsyncHttpClient | None = None
        self.cache: DiscoveryCache | None = None

    async def __aenter__(self) -> "RemoteExecutor":
        settings = self.settings
        self.client = AsyncHttpClient(
            concurrency=settings.http_concurrency, per_host=settings.http_per_host,
            timeout_s=settings.timeout_s, max_response_bytes=settings.max_response_bytes,
            retry_attempts=settings.retry_attempts, retry_backoff_base_s=settings.retry_backoff_base_s,
            retry_backoff_max_s=settings.retry_backoff_max_s, retry_jitter_s=settings.retry_jitter_s,
        )
        await self.client.start()
        self.cache = await DiscoveryCache.open(self.cache_path, ttl_s=settings.cache_ttl_s, max_entries=settings.cache_max_entries, compress=settings.cache_compress)
        return self

    async def __aexit__(self, *_: object) -> None:
        assert self.client and self.cache
        await self.cache.flush()
        await self.client.close()

    async def execute(self, source: dict[str, Any]) -> AsyncIterator[Sequence[ProductObservation]]:
        assert self.client and self.cache
        settings = self.settings
        name = str(source["name"])
        max_subworkers = int(source.get("subworkers", settings.subworkers_per_agent)) if source.get("type") == "jsonld" else 1
        adaptive = AdaptiveConcurrency(minimum=min(settings.adaptive_min_subworkers, max_subworkers), maximum=max_subworkers, enabled=settings.adaptive_concurrency)
        circuit = CircuitBreaker(failure_threshold=settings.circuit_failure_threshold, recovery_timeout_s=settings.circuit_recovery_timeout_s, half_open_max_calls=settings.circuit_half_open_calls, enabled=settings.circuit_breaker)
        initial = min(settings.adaptive_batch_max, max(settings.adaptive_batch_min, int(source.get("batch_size", settings.adaptive_batch_initial))))
        batch_sizer = AdaptiveBatchSizer(minimum=settings.adaptive_batch_min, maximum=settings.adaptive_batch_max, initial=initial, target_latency_ms=settings.adaptive_batch_target_ms, rss_soft_limit_mb=settings.adaptive_batch_rss_soft_limit_mb, success_window=settings.adaptive_batch_success_window, enabled=settings.adaptive_batching)
        adapter = build_source_adapter(source, settings=settings, client=self.client, cache=self.cache, adaptive=adaptive, circuit=circuit, batch_sizer=batch_sizer)
        async for batch in adapter.discover_batches():
            yield batch


async def run_coordinator(args: argparse.Namespace) -> int:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (RuntimeError, NotImplementedError):
            pass
    async with DistributedTaskStore(args.state) as store:
        server = CoordinatorHttpServer(store, host=args.host, port=args.port)
        await server.start()
        try:
            await stop.wait()
        finally:
            await server.close()
    return 0


async def run_submit(args: argparse.Namespace) -> int:
    config = await asyncio.to_thread(_read_json, args.config)
    async with CoordinatorClient(args.coordinator) as client:
        result = await client.submit_cycle(list(config.get("sources", [])), args.cycle_id)
    print(await asyncio.to_thread(_pretty, result))
    return 0


async def run_status(args: argparse.Namespace) -> int:
    async with CoordinatorClient(args.coordinator) as client:
        result = await client.cycle_status(args.cycle_id)
    print(await asyncio.to_thread(_pretty, result))
    return 0


async def run_collect(args: argparse.Namespace) -> int:
    config = await asyncio.to_thread(_read_json, args.config)
    deadline = time.monotonic() + args.timeout_s
    async with CoordinatorClient(args.coordinator) as client:
        while True:
            status = await client.cycle_status(args.cycle_id)
            if status.get("done"):
                break
            if not args.wait:
                raise RuntimeError(f"cycle {args.cycle_id} is not complete: {status}")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"cycle {args.cycle_id} did not complete before timeout")
            await asyncio.sleep(args.poll_s)
        results = await client.cycle_results(args.cycle_id)
    trusts = {str(source["name"]): float(source.get("source_trust", 0.65)) for source in config.get("sources", [])}
    states = {row["source_name"]: row["state"] for row in results}
    successful = sorted(name for name, state in states.items() if state == "completed")
    seen: dict[str, set[str]] = {}
    changes = []
    spool = ObservationSpool(Path(args.output))
    await spool.reset()
    async with CatalogHistory(args.history) as history:
        run_id = await history.begin_refresh()
        try:
            for row in results:
                values = tuple(ProductObservation(**raw) for raw in row.get("observations", []))
                if not values:
                    continue
                source = str(row["source_name"])
                seen.setdefault(source, set()).update(item.source_id for item in values)
                changes.extend(await history.record_batch(run_id, values))
                normalized = await asyncio.to_thread(lambda: [normalize_observation(item, source_trust=trusts.get(item.source, 0.65)) for item in values])
                await spool.append(normalized)
            changes.extend(await history.finish_refresh(run_id, source_names=successful, seen_by_source=seen, disappearance_after_runs=int(config.get("disappearance_after_runs", 2))))
        except BaseException:
            await history.abort_refresh(run_id)
            raise
    metadata = {
        "run_id": run_id, "distributed_cycle_id": args.cycle_id, "observation_count": spool.count,
        "errors": {name: "remote task failed" for name, state in states.items() if state == "failed"},
        "changes": [{"source": item.source, "source_id": item.source_id, "change_type": item.change_type, "previous": item.previous, "current": item.current} for item in changes],
        "runtime": {"distributed": True, "remote_tasks": status},
    }
    await spool.finalize(metadata)
    print(await asyncio.to_thread(_pretty, {key: metadata[key] for key in ("run_id", "distributed_cycle_id", "observation_count", "errors")}))
    return 0


async def run_worker(args: argparse.Namespace) -> int:
    config = await asyncio.to_thread(_read_json, args.config)
    worker_id = args.worker_id or f"{socket.gethostname()}-{os.getpid()}"
    async with CoordinatorClient(args.coordinator) as client, RemoteExecutor(config, args.cache) as executor:
        worker = DistributedWorker(client, worker_id, executor.execute, lease_s=args.lease_s, heartbeat_s=args.heartbeat_s, poll_s=args.poll_s, max_attempts=args.max_attempts)
        while True:
            did_work = await worker.run_one()
            if args.once:
                return 0
            if not did_work:
                await asyncio.sleep(args.poll_s)


def main() -> int:
    parser = argparse.ArgumentParser(description="Distributed LowPowerLLMCluster source-worker backend")
    sub = parser.add_subparsers(dest="command", required=True)
    coordinator = sub.add_parser("coordinator")
    coordinator.add_argument("--state", default="results/distributed-tasks.sqlite3")
    coordinator.add_argument("--host", default="0.0.0.0")
    coordinator.add_argument("--port", type=int, default=8788)
    submit = sub.add_parser("submit")
    submit.add_argument("--coordinator", required=True)
    submit.add_argument("--config", required=True)
    submit.add_argument("--cycle-id")
    status = sub.add_parser("status")
    status.add_argument("--coordinator", required=True)
    status.add_argument("--cycle-id", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--coordinator", required=True)
    collect.add_argument("--cycle-id", required=True)
    collect.add_argument("--config", required=True)
    collect.add_argument("--history", default="results/catalog-history.sqlite3")
    collect.add_argument("--output", default="results/discovery-latest.json")
    collect.add_argument("--wait", action="store_true")
    collect.add_argument("--timeout-s", type=float, default=3600)
    collect.add_argument("--poll-s", type=float, default=2)
    worker = sub.add_parser("worker")
    worker.add_argument("--coordinator", required=True)
    worker.add_argument("--config", required=True)
    worker.add_argument("--cache", default="results/worker-http-cache.json")
    worker.add_argument("--worker-id")
    worker.add_argument("--lease-s", type=float, default=60)
    worker.add_argument("--heartbeat-s", type=float, default=20)
    worker.add_argument("--poll-s", type=float, default=2)
    worker.add_argument("--max-attempts", type=int, default=5)
    worker.add_argument("--once", action="store_true")
    args = parser.parse_args()
    functions = {"coordinator": run_coordinator, "submit": run_submit, "status": run_status, "collect": run_collect, "worker": run_worker}
    return asyncio.run(functions[args.command](args))


if __name__ == "__main__":
    raise SystemExit(main())
