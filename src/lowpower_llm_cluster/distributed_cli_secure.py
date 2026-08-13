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
from .distributed_cli_common import RemoteExecutor, _labels, _pretty, _read_json, _read_secret

async def _client_ssl(args: argparse.Namespace) -> Any:
    if not (getattr(args, "tls_ca", None) or getattr(args, "tls_cert", None) or getattr(args, "tls_insecure_skip_verify", False)):
        return None
    return await asyncio.to_thread(build_client_ssl_context, ca=args.tls_ca, cert=args.tls_cert, key=args.tls_key, insecure_skip_verify=args.tls_insecure_skip_verify)


async def run_secure_coordinator(args: argparse.Namespace) -> int:
    if not args.auth_file:
        raise RuntimeError("secure coordinator requires --auth-file")
    auth = await asyncio.to_thread(AuthRegistry.load, args.auth_file)
    ssl_context = None
    if args.tls_cert or args.tls_key:
        if not args.tls_cert or not args.tls_key:
            raise RuntimeError("both --tls-cert and --tls-key are required")
        ssl_context = await asyncio.to_thread(build_server_ssl_context, cert=args.tls_cert, key=args.tls_key, client_ca=args.tls_client_ca, require_client_cert=args.require_client_cert)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try: loop.add_signal_handler(sig, stop.set)
        except (RuntimeError, NotImplementedError): pass
    artifacts = ContentAddressedStore(args.artifacts)
    async with SecureDistributedStore(args.state, artifacts) as store:
        server = SecureCoordinatorServer(store, auth, host=args.host, port=args.port, node_id=args.node_id, leader_lease_s=args.leader_lease_s, standby=args.standby, ssl_context=ssl_context)
        await server.start()
        print(await asyncio.to_thread(_pretty, {"secure": True, "node_id": args.node_id, "active": server.active, "epoch": server.epoch, "standby": args.standby}))
        try: await stop.wait()
        finally: await server.close()
    return 0


async def _secure_admin_client(args: argparse.Namespace) -> SecureCoordinatorClient:
    token = await asyncio.to_thread(_read_secret, getattr(args, "admin_token", None), getattr(args, "admin_token_file", None), "LPLLM_ADMIN_TOKEN")
    if not token: raise RuntimeError("secure admin operation requires token via --admin-token, --admin-token-file or LPLLM_ADMIN_TOKEN")
    client = SecureCoordinatorClient(args.coordinator, admin_token=token, ssl_context=await _client_ssl(args))
    await client.__aenter__()
    return client


async def run_secure_submit(args: argparse.Namespace) -> int:
    config = await asyncio.to_thread(_read_json, args.config)
    client = await _secure_admin_client(args)
    try: result = await client.submit_cycle(list(config.get("sources", ())), args.cycle_id)
    finally: await client.__aexit__(None, None, None)
    print(await asyncio.to_thread(_pretty, result)); return 0


async def run_secure_status(args: argparse.Namespace) -> int:
    client = await _secure_admin_client(args)
    try: result = await client.cycle_status(args.cycle_id)
    finally: await client.__aexit__(None, None, None)
    print(await asyncio.to_thread(_pretty, result)); return 0


async def _collect_rows(config: dict[str, Any], args: argparse.Namespace, status: dict[str, Any], rows: AsyncIterator[dict[str, Any]]) -> int:
    trusts = {str(source["name"]): float(source.get("source_trust", 0.65)) for source in config.get("sources", ())}
    states: dict[str, str] = {}; seen: dict[str, set[str]] = {}; changes = []; errors: dict[str, str] = {}
    spool = ObservationSpool(Path(args.output)); await spool.reset()
    async with CatalogHistory(args.history) as history:
        run_id = await history.begin_refresh()
        try:
            async for row in rows:
                source, state = str(row.get("source_name", "")), str(row.get("state", ""))
                if source: states[source] = state
                if state in {"failed", "canceled"}: errors[source] = str(row.get("error") or state)
                values = tuple(ProductObservation(**raw) for raw in row.get("observations", ()))
                if not values: continue
                seen.setdefault(source, set()).update(item.source_id for item in values)
                changes.extend(await history.record_batch(run_id, values))
                normalized = await asyncio.to_thread(lambda: [normalize_observation(item, source_trust=trusts.get(item.source, 0.65)) for item in values])
                await spool.append(normalized)
            successful = sorted(name for name, state in states.items() if state == "completed")
            changes.extend(await history.finish_refresh(run_id, source_names=successful, seen_by_source=seen, disappearance_after_runs=int(config.get("disappearance_after_runs", 2))))
        except BaseException:
            await history.abort_refresh(run_id); raise
    metadata = {
        "run_id": run_id, "distributed_cycle_id": args.cycle_id, "observation_count": spool.count, "errors": errors,
        "changes": [{"source": item.source, "source_id": item.source_id, "change_type": item.change_type, "previous": item.previous, "current": item.current} for item in changes],
        "runtime": {"distributed": True, "secure_protocol": "v2", "remote_tasks": status},
    }
    await spool.finalize(metadata)
    print(await asyncio.to_thread(_pretty, {key: metadata[key] for key in ("run_id", "distributed_cycle_id", "observation_count", "errors")})); return 0


async def run_secure_collect(args: argparse.Namespace) -> int:
    config = await asyncio.to_thread(_read_json, args.config)
    client = await _secure_admin_client(args)
    try:
        deadline = time.monotonic() + args.timeout_s
        while True:
            status = await client.cycle_status(args.cycle_id)
            if status.get("done"): break
            if not args.wait: raise RuntimeError(f"cycle {args.cycle_id} is not complete: {status}")
            if time.monotonic() >= deadline: raise TimeoutError(f"cycle {args.cycle_id} did not complete before timeout")
            await asyncio.sleep(args.poll_s)
        return await _collect_rows(config, args, status, client.iter_cycle_results(args.cycle_id))
    finally:
        await client.__aexit__(None, None, None)


async def _heartbeat_loop(client: SecureCoordinatorClient, task_id: str, epoch: int, args: argparse.Namespace, lost: asyncio.Event, stop: asyncio.Event) -> None:
    while not lost.is_set() and not stop.is_set():
        try: await asyncio.wait_for(lost.wait(), timeout=args.heartbeat_s)
        except TimeoutError: pass
        if lost.is_set() or stop.is_set(): return
        resources = await sample_resources(power_budget_w=args.power_budget_w, energy_budget_wh=args.energy_budget_wh)
        try: ok = await client.heartbeat(task_id, epoch=epoch, lease_s=args.lease_s, resources=resources.to_dict())
        except Exception: ok = False
        if not ok: lost.set(); return


async def run_secure_worker(args: argparse.Namespace) -> int:
    config = await asyncio.to_thread(_read_json, args.config)
    worker_id = args.worker_id or f"{socket.gethostname()}-{os.getpid()}"
    secret = await asyncio.to_thread(_read_secret, args.worker_secret, args.worker_secret_file, "LPLLM_WORKER_SECRET")
    if not secret: raise RuntimeError("secure worker requires --worker-secret, --worker-secret-file or LPLLM_WORKER_SECRET")
    capabilities = tuple(sorted(set(args.capability or [str(source.get("type", "json")) for source in config.get("sources", ())])))
    labels = _labels(args.label or ())
    stop = asyncio.Event(); loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try: loop.add_signal_handler(sig, stop.set)
        except (RuntimeError, NotImplementedError): pass
    client = SecureCoordinatorClient(args.coordinator, worker_id=worker_id, worker_secret=secret, ssl_context=await _client_ssl(args))
    await client.__aenter__()
    try:
        resources = await sample_resources(power_budget_w=args.power_budget_w, energy_budget_wh=args.energy_budget_wh)
        registration = await client.register(capabilities=capabilities, labels=labels, resources=resources.to_dict())
        if registration.get("state") != "active":
            print(await asyncio.to_thread(_pretty, registration)); return 0
        async with RemoteExecutor(config, args.cache, snapshot_dir=args.shared_snapshot_dir, snapshot_max_age_s=args.snapshot_max_age_s, prefer_snapshot=args.prefer_snapshot) as executor:
            while not stop.is_set():
                resources = await sample_resources(power_budget_w=args.power_budget_w, energy_budget_wh=args.energy_budget_wh)
                task = await client.lease(lease_s=args.lease_s, capabilities=capabilities, labels=labels, resources=resources.to_dict(), work_steal_after_s=args.work_steal_after_s)
                if task is None:
                    if args.once: return 0
                    try: await asyncio.wait_for(stop.wait(), timeout=args.poll_s)
                    except TimeoutError: pass
                    continue
                lost = asyncio.Event(); epoch = int(task["epoch"]); task_id = str(task["task_id"])
                heartbeat = asyncio.create_task(_heartbeat_loop(client, task_id, epoch, args, lost, stop))
                try:
                    batch_index = 0
                    async for batch in executor.execute(dict(task["payload"])):
                        if lost.is_set(): raise RuntimeError("task lease lost during execution")
                        batch_id = f"{task['task_key']}:{batch_index}"
                        await client.add_batch(task_id, epoch=epoch, batch_id=batch_id, observations=batch)
                        batch_index += 1
                    if lost.is_set() or not await client.complete(task_id, epoch=epoch):
                        raise RuntimeError("task lease lost before completion")
                except Exception as exc:
                    requeue = int(task.get("attempt", 1)) < args.max_attempts
                    try: await client.fail(task_id, epoch=epoch, error=f"{type(exc).__name__}: {exc}", requeue=requeue)
                    except Exception: pass
                finally:
                    lost.set(); heartbeat.cancel(); await asyncio.gather(heartbeat, return_exceptions=True)
                if args.once: return 0
            try: await client.self_drain()
            except Exception: pass
    finally:
        await client.__aexit__(None, None, None)
    return 0


async def run_workers(args: argparse.Namespace) -> int:
    client = await _secure_admin_client(args)
    try: result = {"workers": await client.workers()}
    finally: await client.__aexit__(None, None, None)
    print(await asyncio.to_thread(_pretty, result)); return 0


async def run_drain(args: argparse.Namespace) -> int:
    client = await _secure_admin_client(args)
    try: ok = await client.set_drain(args.worker_id, True)
    finally: await client.__aexit__(None, None, None)
    print(await asyncio.to_thread(_pretty, {"worker_id": args.worker_id, "draining": ok})); return 0


async def run_undrain(args: argparse.Namespace) -> int:
    client = await _secure_admin_client(args)
    try: ok = await client.set_drain(args.worker_id, False)
    finally: await client.__aexit__(None, None, None)
    print(await asyncio.to_thread(_pretty, {"worker_id": args.worker_id, "active": ok})); return 0


async def run_cancel(args: argparse.Namespace) -> int:
    client = await _secure_admin_client(args)
    try: ok = await client.cancel_cycle(args.cycle_id)
    finally: await client.__aexit__(None, None, None)
    print(await asyncio.to_thread(_pretty, {"cycle_id": args.cycle_id, "canceled": ok})); return 0


async def run_backup(args: argparse.Namespace) -> int:
    client = await _secure_admin_client(args)
    try: result = await client.backup(args.destination)
    finally: await client.__aexit__(None, None, None)
    print(await asyncio.to_thread(_pretty, result)); return 0


def _restore_sync(backup: str, state: str) -> None:
    source, destination = Path(backup), Path(state)
    if not source.is_file(): raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.restore")
    shutil.copy2(source, temporary); os.replace(temporary, destination)
    for suffix in ("-wal", "-shm"):
        try: Path(str(destination) + suffix).unlink()
        except FileNotFoundError: pass


async def run_restore(args: argparse.Namespace) -> int:
    await asyncio.to_thread(_restore_sync, args.backup, args.state)
    print(await asyncio.to_thread(_pretty, {"restored": args.state, "from": args.backup, "warning": "start coordinators only after offline restore completes"})); return 0



def _init_auth_sync(output: str, workers: Sequence[str]) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing credential file: {path}")
    payload = {
        "admin_tokens": [secrets.token_urlsafe(32)],
        "workers": {worker: {"secret": secrets.token_urlsafe(32), "roles": ["worker"]} for worker in sorted(set(workers))},
    }
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


async def run_init_auth(args: argparse.Namespace) -> int:
    await asyncio.to_thread(_init_auth_sync, args.output, args.worker)
    print(await asyncio.to_thread(_pretty, {"created": args.output, "workers": sorted(set(args.worker)), "mode": "0600", "note": "secrets are stored in the file and are not printed"}))
    return 0
