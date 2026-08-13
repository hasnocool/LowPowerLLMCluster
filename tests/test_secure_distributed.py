from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from lowpower_llm_cluster.content_store import ContentAddressedStore
from lowpower_llm_cluster.discovery import ProductObservation
from lowpower_llm_cluster.distributed_security import AuthRegistry, ReplayWindow, WorkerCredential, signed_worker_headers, verify_worker_request
from lowpower_llm_cluster.secure_distributed import SecureDistributedStore


def test_hmac_worker_auth_rejects_replay() -> None:
    registry = AuthRegistry({"node-a": WorkerCredential("node-a", "secret")}, admin_tokens=("admin",))
    replay = ReplayWindow(max_age_s=120)
    body = b'{"x":1}'
    headers = signed_worker_headers("node-a", "secret", method="POST", path_qs="/v2/tasks/lease", body=body, now=1000)
    worker = verify_worker_request(registry, replay, method="POST", path_qs="/v2/tasks/lease", body=body, headers=headers, now=1000)
    assert worker.worker_id == "node-a"
    try:
        verify_worker_request(registry, replay, method="POST", path_qs="/v2/tasks/lease", body=body, headers=headers, now=1000)
    except PermissionError as exc:
        assert "replayed" in str(exc)
    else:
        raise AssertionError("replay accepted")


def test_secure_store_capabilities_epoch_cas_and_failover(tmp_path: Path) -> None:
    async def scenario() -> None:
        artifacts = ContentAddressedStore(tmp_path / "artifacts")
        async with SecureDistributedStore(tmp_path / "tasks.sqlite3", artifacts) as store:
            leader = await store.acquire_leader("a", lease_s=0.05)
            assert leader.epoch == 1
            await store.register_worker("cpu", capabilities=["json"], labels={"region": "west"}, resources={"cpu_load_fraction": 0.1, "available_memory_mb": 4096})
            await store.register_worker("gpu", capabilities=["json", "gpu"], labels={"region": "west"}, resources={"cpu_load_fraction": 0.1, "available_memory_mb": 4096})
            await store.submit_cycle([
                {"name": "gpu-source", "type": "json", "worker_requirements": {"capabilities": ["gpu"], "labels": {"region": "west"}}}
            ], cycle_id="c1")
            assert await store.lease("cpu", epoch=leader.epoch, lease_s=1, capabilities=["json"], labels={"region": "west"}, resources={"cpu_load_fraction": 0.1}) is None
            task = await store.lease("gpu", epoch=leader.epoch, lease_s=1, capabilities=["json", "gpu"], labels={"region": "west"}, resources={"cpu_load_fraction": 0.1})
            assert task and task["epoch"] == 1
            obs = [ProductObservation("gpu-source", "1", "https://e/1", "One")]
            assert await store.add_batch(task["task_id"], "gpu", "b1", obs, epoch=1)
            assert not await store.add_batch(task["task_id"], "gpu", "b1", obs, epoch=1)
            assert await store.complete(task["task_id"], "gpu", epoch=1)
            refs = await store.result_refs("c1")
            assert refs[0]["observation_count"] == 1
            payload = await artifacts.get_json(refs[0]["sha256"])
            assert payload[0]["source_id"] == "1"
            await asyncio.sleep(0.06)
            next_leader = await store.acquire_leader("b", lease_s=1)
            assert next_leader.epoch == 2
            await store.submit_cycle([{"name":"s2","type":"json"}], cycle_id="c2")
            try:
                await store.lease("gpu", epoch=1, lease_s=1, capabilities=["json", "gpu"], labels={"region":"west"}, resources={})
            except PermissionError:
                pass
            else:
                raise AssertionError("stale epoch leased work")
            task2 = await store.lease("gpu", epoch=2, lease_s=1, capabilities=["json", "gpu"], labels={"region":"west"}, resources={})
            assert task2 and task2["epoch"] == 2
    asyncio.run(scenario())


def test_drain_cancel_backup_and_reclaim(tmp_path: Path) -> None:
    async def scenario() -> None:
        artifacts = ContentAddressedStore(tmp_path / "artifacts")
        path = tmp_path / "tasks.sqlite3"
        async with SecureDistributedStore(path, artifacts) as store:
            leader = await store.acquire_leader("a", lease_s=1)
            await store.register_worker("w", capabilities=["json"], labels={}, resources={})
            assert await store.set_worker_state("w", "draining")
            await store.submit_cycle([{"name":"s","type":"json"}], cycle_id="cancel")
            assert await store.lease("w", epoch=leader.epoch, lease_s=0.03, capabilities=["json"], labels={}, resources={}) is None
            await store.set_worker_state("w", "active")
            task = await store.lease("w", epoch=leader.epoch, lease_s=0.03, capabilities=["json"], labels={}, resources={})
            assert task
            assert await store.cancel_cycle("cancel")
            assert not await store.heartbeat(task["task_id"], "w", epoch=leader.epoch, lease_s=1, resources={})
            await store.submit_cycle([{"name":"r","type":"json"}], cycle_id="reclaim")
            task2 = await store.lease("w", epoch=leader.epoch, lease_s=0.02, capabilities=["json"], labels={}, resources={})
            assert task2
            await asyncio.sleep(0.03)
            task3 = await store.lease("w", epoch=leader.epoch, lease_s=1, capabilities=["json"], labels={}, resources={})
            assert task3 and task3["task_id"] == task2["task_id"] and task3["attempt"] == 2
            backup = await store.backup(tmp_path / "backup.sqlite3")
            assert backup.exists() and backup.stat().st_size > 0
    asyncio.run(scenario())


def test_resource_requirements_affinity_work_steal(tmp_path: Path) -> None:
    async def scenario() -> None:
        artifacts = ContentAddressedStore(tmp_path / "artifacts")
        async with SecureDistributedStore(tmp_path / "tasks.sqlite3", artifacts) as store:
            leader = await store.acquire_leader("a", lease_s=2)
            for wid in ("preferred", "other"):
                await store.register_worker(wid, capabilities=["json"], labels={}, resources={"cpu_load_fraction":0.1})
            await store.submit_cycle([{"name":"a","type":"json","worker_affinity":["preferred"]}], cycle_id="aff")
            assert await store.lease("other", epoch=leader.epoch, lease_s=1, capabilities=["json"], labels={}, resources={"cpu_load_fraction":0.1}, work_steal_after_s=999) is None
            task = await store.lease("preferred", epoch=leader.epoch, lease_s=1, capabilities=["json"], labels={}, resources={"cpu_load_fraction":0.1}, work_steal_after_s=999)
            assert task
    asyncio.run(scenario())


def test_secure_http_protocol_streams_results_and_enforces_identity(tmp_path: Path) -> None:
    from lowpower_llm_cluster.distributed_security import AuthRegistry
    from lowpower_llm_cluster.secure_distributed import SecureCoordinatorClient, SecureCoordinatorServer

    async def scenario() -> None:
        artifacts = ContentAddressedStore(tmp_path / "artifacts")
        auth = AuthRegistry({"node-a": WorkerCredential("node-a", "worker-secret")}, admin_tokens=("admin-secret",))
        async with SecureDistributedStore(tmp_path / "tasks.sqlite3", artifacts) as store:
            server = SecureCoordinatorServer(store, auth, host="127.0.0.1", port=0, node_id="primary", leader_lease_s=2)
            await server.start()
            base = f"http://127.0.0.1:{server.port}"
            try:
                async with SecureCoordinatorClient(base, admin_token="admin-secret") as admin, SecureCoordinatorClient(base, worker_id="node-a", worker_secret="worker-secret") as worker:
                    await admin.submit_cycle([{"name":"fixture","type":"json","worker_requirements":{"capabilities":["json"]}}], "http-cycle")
                    reg = await worker.register(capabilities=["json"], labels={"rack":"a"}, resources={"cpu_load_fraction":0.1})
                    assert reg["worker_id"] == "node-a"
                    task = await worker.lease(lease_s=1, capabilities=["json"], labels={"rack":"a"}, resources={"cpu_load_fraction":0.1})
                    assert task
                    assert await worker.add_batch(task["task_id"], epoch=task["epoch"], batch_id="b", observations=[ProductObservation("fixture","1","https://e/1","One")])
                    assert await worker.complete(task["task_id"], epoch=task["epoch"])
                    status = await admin.cycle_status("http-cycle")
                    assert status["done"]
                    rows = [row async for row in admin.iter_cycle_results("http-cycle")]
                    assert len(rows) == 1 and rows[0]["observations"][0]["title"] == "One"
                    assert await admin.set_drain("node-a", True)
                    workers = await admin.workers()
                    assert workers[0]["state"] == "draining"
                async with SecureCoordinatorClient(base, worker_id="node-a", worker_secret="wrong") as bad:
                    try:
                        await bad.register(capabilities=["json"], labels={}, resources={})
                    except RuntimeError as exc:
                        assert "401" in str(exc)
                    else:
                        raise AssertionError("bad worker secret accepted")
            finally:
                await server.close()
    asyncio.run(scenario())


def test_content_store_source_snapshot_and_gc(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = ContentAddressedStore(tmp_path / "cas")
        await store.initialize()
        keep = await store.put(b"keep")
        drop = await store.put(b"drop")
        await store.note_source_snapshot("https://example.test/feed", keep, headers={"etag":"v1"}, observed_at=time.time())
        entry = await store.source_snapshot("https://example.test/feed", max_age_s=10)
        assert entry and entry["sha256"] == keep.sha256
        drop_path = store.blob_path(drop.sha256)
        old = time.time() - 1000
        import os
        os.utime(drop_path, (old, old))
        result = await store.gc(referenced={keep.sha256}, grace_s=1)
        assert result["removed"] == 1
        assert await store.get(keep.sha256) == b"keep"
    asyncio.run(scenario())


def test_resource_requirements_enforce_thermal_memory_and_power() -> None:
    from lowpower_llm_cluster.resource_runtime import SchedulingRequirements
    req = SchedulingRequirements.from_source({"worker_requirements": {"capabilities":["json"], "max_cpu_load":0.8, "max_thermal_c":80, "min_available_memory_mb":1024, "min_power_budget_w":25}})
    ok, _, _ = req.matches(worker_id="w", capabilities={"json"}, labels={}, resources={"cpu_load_fraction":0.2,"thermal_c":60,"available_memory_mb":2048,"power_budget_w":30}, allow_steal=True)
    assert ok
    hot, _, reason = req.matches(worker_id="w", capabilities={"json"}, labels={}, resources={"cpu_load_fraction":0.2,"thermal_c":90,"available_memory_mb":2048,"power_budget_w":30}, allow_steal=True)
    assert not hot and "thermal" in reason


def test_distributed_daemon_engine_submit_wait_stream_collect(tmp_path: Path) -> None:
    from lowpower_llm_cluster.distributed_service import SecureDistributedCycleEngine
    from lowpower_llm_cluster.secure_distributed import SecureCoordinatorClient, SecureCoordinatorServer

    async def scenario() -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"sources":[{"name":"fixture","type":"json","source_trust":0.8}], "disappearance_after_runs":2}), encoding="utf-8")
        auth = AuthRegistry({"node-a": WorkerCredential("node-a", "worker-secret")}, admin_tokens=("admin-secret",))
        async with SecureDistributedStore(tmp_path / "tasks.sqlite3", ContentAddressedStore(tmp_path / "artifacts")) as store:
            server = SecureCoordinatorServer(store, auth, host="127.0.0.1", port=0, node_id="primary", leader_lease_s=2)
            await server.start(); base=f"http://127.0.0.1:{server.port}"
            async def worker_once() -> None:
                async with SecureCoordinatorClient(base, worker_id="node-a", worker_secret="worker-secret") as worker:
                    await worker.register(capabilities=["json"], labels={}, resources={"cpu_load_fraction":0.1})
                    for _ in range(100):
                        task = await worker.lease(lease_s=1, capabilities=["json"], labels={}, resources={"cpu_load_fraction":0.1})
                        if task:
                            await worker.add_batch(task["task_id"], epoch=task["epoch"], batch_id="one", observations=[ProductObservation("fixture","1","https://e/1","One")])
                            assert await worker.complete(task["task_id"], epoch=task["epoch"])
                            return
                        await asyncio.sleep(0.01)
                    raise AssertionError("worker never received daemon-submitted task")
            try:
                async with SecureDistributedCycleEngine(config_path, coordinator=base, admin_token="admin-secret", history_path=tmp_path/"history.sqlite3", output_path=tmp_path/"latest.json", poll_s=0.01, timeout_s=2) as engine:
                    task = asyncio.create_task(worker_once())
                    summary = await engine.run_once()
                    await task
                assert summary["observation_count"] == 1
                assert summary["runtime"]["secure_protocol"] == "v2"
                assert json.loads((tmp_path/"latest.json").read_text())["observations"][0]["source_id"] == "1"
            finally:
                await server.close()
    asyncio.run(scenario())


def test_shared_source_snapshot_can_be_reused_with_explicit_freshness(tmp_path: Path) -> None:
    from aiohttp import web
    from lowpower_llm_cluster.snapshot_http import SnapshottingHttpClient

    async def scenario() -> None:
        async def handler(_: web.Request) -> web.Response:
            return web.Response(body=b'{"value":1}', headers={"ETag":"v1"}, content_type="application/json")
        app=web.Application(); app.router.add_get('/feed',handler); runner=web.AppRunner(app); await runner.setup(); site=web.TCPSite(runner,'127.0.0.1',0); await site.start()
        port=site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
        url=f'http://127.0.0.1:{port}/feed'; store=ContentAddressedStore(tmp_path/'shared')
        async with SnapshottingHttpClient(snapshot_store=store) as live:
            first=await live.get_response(url); assert first.payload==b'{"value":1}'
        await runner.cleanup()
        async with SnapshottingHttpClient(snapshot_store=store, prefer_snapshot=True, snapshot_max_age_s=60) as cached:
            second=await cached.get_response(url); assert second.headers['x-lpllm-snapshot']=='1'; assert second.payload==first.payload
    asyncio.run(scenario())


def test_injected_network_partition_causes_safe_lease_reclaim(tmp_path: Path) -> None:
    from lowpower_llm_cluster.fault_injection import FaultInjectedClient, FaultPlan

    async def scenario() -> None:
        artifacts=ContentAddressedStore(tmp_path/'artifacts')
        async with SecureDistributedStore(tmp_path/'tasks.sqlite3', artifacts) as store:
            leader=await store.acquire_leader('leader', lease_s=1)
            for wid in ('w1','w2'):
                await store.register_worker(wid, capabilities=['json'], labels={}, resources={})
            await store.submit_cycle([{'name':'partitioned','type':'json'}], cycle_id='partition')
            task=await store.lease('w1', epoch=leader.epoch, lease_s=0.02, capabilities=['json'], labels={}, resources={})
            assert task
            class StoreClient:
                async def heartbeat(self, task_id: str, **kwargs):
                    return await store.heartbeat(task_id, 'w1', **kwargs)
            partitioned=FaultInjectedClient(StoreClient(), FaultPlan(failures={'heartbeat':{1}}))
            try:
                await partitioned.heartbeat(task['task_id'], epoch=leader.epoch, lease_s=0.02, resources={})
            except ConnectionError:
                pass
            else:
                raise AssertionError('network partition was not injected')
            await asyncio.sleep(0.03)
            reclaimed=await store.lease('w2', epoch=leader.epoch, lease_s=1, capabilities=['json'], labels={}, resources={})
            assert reclaimed and reclaimed['task_id']==task['task_id'] and reclaimed['attempt']==2
    asyncio.run(scenario())
