from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import secrets
import signal
import socket
import time
from pathlib import Path
from typing import Any, AsyncIterator, Mapping, Sequence

from .catalog_refresh import ObservationSpool
from .content_store import ContentAddressedStore
from .discovery import ProductObservation
from .distributed_runtime import CoordinatorClient, CoordinatorHttpServer, DistributedTaskStore, DistributedWorker
from .distributed_security import AuthRegistry, build_client_ssl_context, build_server_ssl_context
from .history import CatalogHistory
from .http_runtime import AdaptiveConcurrency, AsyncHttpClient, DiscoveryCache
from .normalization import normalize_observation
from .resilience_runtime import AdaptiveBatchSizer, CircuitBreaker
from .resource_runtime import sample_resources
from .runtime import WorkerSettings
from .secure_distributed import SecureCoordinatorClient, SecureCoordinatorServer, SecureDistributedStore
from .snapshot_http import SnapshottingHttpClient
from .source_runtime import build_source_adapter


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_secret(value: str | None, path: str | None, env_name: str) -> str:
    if value:
        return value
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    return os.environ.get(env_name, "").strip()


def _pretty(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def _labels(values: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"label must be KEY=VALUE: {item!r}")
        key, value = item.split("=", 1)
        if not key:
            raise ValueError("label key may not be empty")
        result[key] = value
    return result


class RemoteExecutor:
    def __init__(self, config: dict[str, Any], cache_path: str, *, snapshot_dir: str | None = None, snapshot_max_age_s: float | None = None, prefer_snapshot: bool = False) -> None:
        self.config = config
        self.settings = WorkerSettings.from_mapping(config)
        self.cache_path = cache_path
        self.snapshot_dir = snapshot_dir
        self.snapshot_max_age_s = snapshot_max_age_s
        self.prefer_snapshot = prefer_snapshot
        self.client: AsyncHttpClient | None = None
        self.cache: DiscoveryCache | None = None

    async def __aenter__(self) -> "RemoteExecutor":
        settings = self.settings
        snapshot_store = ContentAddressedStore(self.snapshot_dir) if self.snapshot_dir else None
        client_type = SnapshottingHttpClient if snapshot_store is not None else AsyncHttpClient
        kwargs: dict[str, Any] = {
            "concurrency": settings.http_concurrency, "per_host": settings.http_per_host,
            "timeout_s": settings.timeout_s, "max_response_bytes": settings.max_response_bytes,
            "retry_attempts": settings.retry_attempts, "retry_backoff_base_s": settings.retry_backoff_base_s,
            "retry_backoff_max_s": settings.retry_backoff_max_s, "retry_jitter_s": settings.retry_jitter_s,
        }
        if snapshot_store is not None:
            kwargs.update(snapshot_store=snapshot_store, snapshot_max_age_s=self.snapshot_max_age_s, prefer_snapshot=self.prefer_snapshot)
        self.client = client_type(**kwargs)
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
    if args.auth_file:
        from .distributed_cli_secure import run_secure_coordinator
        return await run_secure_coordinator(args)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try: loop.add_signal_handler(sig, stop.set)
        except (RuntimeError, NotImplementedError): pass
    async with DistributedTaskStore(args.state) as store:
        server = CoordinatorHttpServer(store, host=args.host, port=args.port)
        await server.start()
        try: await stop.wait()
        finally: await server.close()
    return 0


async def run_submit(args: argparse.Namespace) -> int:
    if args.admin_token or args.admin_token_file or os.environ.get("LPLLM_ADMIN_TOKEN"):
        from .distributed_cli_secure import run_secure_submit
        return await run_secure_submit(args)
    config = await asyncio.to_thread(_read_json, args.config)
    async with CoordinatorClient(args.coordinator) as client:
        result = await client.submit_cycle(list(config.get("sources", [])), args.cycle_id)
    print(await asyncio.to_thread(_pretty, result)); return 0


async def run_status(args: argparse.Namespace) -> int:
    if args.admin_token or args.admin_token_file or os.environ.get("LPLLM_ADMIN_TOKEN"):
        from .distributed_cli_secure import run_secure_status
        return await run_secure_status(args)
    async with CoordinatorClient(args.coordinator) as client:
        result = await client.cycle_status(args.cycle_id)
    print(await asyncio.to_thread(_pretty, result)); return 0


async def run_collect(args: argparse.Namespace) -> int:
    if args.admin_token or args.admin_token_file or os.environ.get("LPLLM_ADMIN_TOKEN"):
        from .distributed_cli_secure import run_secure_collect
        return await run_secure_collect(args)
    config = await asyncio.to_thread(_read_json, args.config)
    deadline = time.monotonic() + args.timeout_s
    async with CoordinatorClient(args.coordinator) as client:
        while True:
            status = await client.cycle_status(args.cycle_id)
            if status.get("done"): break
            if not args.wait: raise RuntimeError(f"cycle {args.cycle_id} is not complete: {status}")
            if time.monotonic() >= deadline: raise TimeoutError(f"cycle {args.cycle_id} did not complete before timeout")
            await asyncio.sleep(args.poll_s)
        results = await client.cycle_results(args.cycle_id)
    from .distributed_cli_secure import _collect_rows
    return await _collect_rows(config, args, status, _list_rows(results))


async def _list_rows(rows: Sequence[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
    for row in rows:
        yield row


async def run_worker(args: argparse.Namespace) -> int:
    if args.worker_secret or args.worker_secret_file or os.environ.get("LPLLM_WORKER_SECRET"):
        from .distributed_cli_secure import run_secure_worker
        return await run_secure_worker(args)
    config = await asyncio.to_thread(_read_json, args.config)
    worker_id = args.worker_id or f"{socket.gethostname()}-{os.getpid()}"
    async with CoordinatorClient(args.coordinator) as client, RemoteExecutor(config, args.cache) as executor:
        worker = DistributedWorker(client, worker_id, executor.execute, lease_s=args.lease_s, heartbeat_s=args.heartbeat_s, poll_s=args.poll_s, max_attempts=args.max_attempts)
        while True:
            did_work = await worker.run_one()
            if args.once: return 0
            if not did_work: await asyncio.sleep(args.poll_s)
