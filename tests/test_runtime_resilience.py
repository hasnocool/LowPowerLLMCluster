from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from lowpower_llm_cluster.discovery import ProductObservation
from lowpower_llm_cluster.distributed_runtime import DistributedTaskStore
from lowpower_llm_cluster.http_runtime import AdaptiveConcurrency, AsyncHttpClient, DiscoveryCache, HttpResponse
from lowpower_llm_cluster.process_adapter import ProcessAdapter
from lowpower_llm_cluster.resilience_runtime import AdaptiveBatchSizer, CircuitBreaker, CircuitOpenError, CircuitState
from lowpower_llm_cluster.service_install import render_systemd_unit
from lowpower_llm_cluster.service_runtime import RuntimeMetrics, ServiceHealth


def test_circuit_breaker_opens_half_opens_and_recovers() -> None:
    async def scenario() -> None:
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout_s=0.01)
        await breaker.acquire()
        await breaker.failure()
        await breaker.acquire()
        await breaker.failure()
        assert breaker.state is CircuitState.OPEN
        with pytest.raises(CircuitOpenError):
            await breaker.acquire()
        await asyncio.sleep(0.02)
        await breaker.acquire()
        assert breaker.state is CircuitState.HALF_OPEN
        await breaker.success()
        assert breaker.state is CircuitState.CLOSED
        assert breaker.metrics()["recoveries"] == 1

    asyncio.run(scenario())


def test_adaptive_batch_sizer_reacts_to_latency_and_rss() -> None:
    sizer = AdaptiveBatchSizer(
        minimum=10,
        maximum=100,
        initial=40,
        target_latency_ms=100,
        rss_soft_limit_mb=1000,
        success_window=2,
    )
    assert sizer.observe(latency_ms=200, rss_mb=100) == 20
    sizer.observe(latency_ms=20, rss_mb=100)
    assert sizer.observe(latency_ms=20, rss_mb=100) > 20
    assert sizer.observe(latency_ms=20, rss_mb=1200) <= 20


def test_cache_ttl_prune_and_gzip_storage(tmp_path: Path) -> None:
    async def scenario() -> None:
        path = tmp_path / "cache.bin"
        response = HttpResponse(200, b"abc", {"etag": "x"}, 1, 1.0)
        cache = await DiscoveryCache.open(path, ttl_s=0.01, max_entries=1, compress=True)
        await cache.store(
            "https://example.test/a",
            response,
            [ProductObservation("source", "a", "https://example.test/a", "A")],
        )
        await cache.store(
            "https://example.test/b",
            response,
            [ProductObservation("source", "b", "https://example.test/b", "B")],
        )
        await cache.flush()
        assert path.read_bytes()[:2] == b"\x1f\x8b"
        reopened = await DiscoveryCache.open(path, ttl_s=0.01, max_entries=1, compress=True)
        assert reopened.metrics()["entries"] == 1
        await asyncio.sleep(0.02)
        assert reopened.observations("https://example.test/b") is None
        assert reopened.metrics()["expired_entries"] >= 1

    asyncio.run(scenario())


def test_distributed_leases_heartbeats_and_idempotent_batches(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with DistributedTaskStore(tmp_path / "distributed.sqlite3") as store:
            cycle = await store.submit_cycle(
                [{"name": "source-a", "type": "json", "endpoint": "https://example.test/feed"}],
                cycle_id="cycle-1",
            )
            assert cycle["cycle_id"] == "cycle-1"
            task = await store.lease("worker-1", lease_s=0.2)
            assert task is not None
            assert await store.heartbeat(task["task_id"], "worker-1", lease_s=0.2)
            observation = ProductObservation("source-a", "1", "https://example.test/1", "One")
            assert await store.add_batch(task["task_id"], "worker-1", "batch-0", [observation])
            assert not await store.add_batch(task["task_id"], "worker-1", "batch-0", [observation])
            await asyncio.sleep(0.25)
            task2 = await store.lease("worker-2", lease_s=1.0)
            assert task2 is not None and task2["task_id"] == task["task_id"]
            assert task2["attempt"] == 2
            assert await store.complete(task2["task_id"], "worker-2")
            status = await store.cycle_status("cycle-1")
            assert status["done"] is True
            results = await store.cycle_results("cycle-1")
            assert len([row for row in results if row["batch_id"] == "batch-0"]) == 1

    asyncio.run(scenario())


def test_prometheus_health_and_systemd_restart_policy() -> None:
    metrics = RuntimeMetrics(labels={"node": "a"})
    metrics.inc("refresh_cycles_total")
    metrics.set("ready", 1)
    text = metrics.prometheus()
    assert "lowpower_llmcluster_refresh_cycles_total" in text
    assert 'node="a"' in text

    health = ServiceHealth()
    assert not health.ready()
    health.mark_started()
    assert health.ready()
    health.mark_cycle(ok=False, error="failure")
    assert not health.ready()

    unit = render_systemd_unit(
        service_command="/usr/bin/llm-cluster-service",
        config="/srv/lpllm/config.json",
        history="/srv/lpllm/history.sqlite3",
        output="/srv/lpllm/latest.json",
        cache="/srv/lpllm/cache.json.gz",
        interval=30,
    )
    assert "Restart=on-failure" in unit
    assert "NoNewPrivileges=true" in unit
    assert "UMask=0077" in unit


def test_process_adapter_jsonl_isolation() -> None:
    code = (
        "import json,sys; c=json.loads(sys.stdin.readline()); "
        "print(json.dumps({'source':c['name'],'source_id':'1','listing_url':'u','title':'x'}))"
    )

    async def scenario() -> None:
        adapter = ProcessAdapter(
            "isolated",
            [sys.executable, "-c", code],
            {"name": "isolated"},
            timeout_s=5,
            batch_size=1,
        )
        records = await adapter.discover()
        assert len(records) == 1
        assert records[0].source == "isolated"

    asyncio.run(scenario())


def test_true_streaming_json_items() -> None:
    pytest.importorskip("ijson")
    from aiohttp import web

    async def scenario() -> None:
        async def feed(_: web.Request) -> web.Response:
            return web.json_response({"products": [{"id": index} for index in range(25)]})

        app = web.Application()
        app.router.add_get("/feed", feed)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        assert site._server is not None
        port = site._server.sockets[0].getsockname()[1]
        limiter = AdaptiveConcurrency(minimum=1, maximum=2)
        try:
            async with AsyncHttpClient(concurrency=2, per_host=2) as client:
                ids: list[int] = []
                async for item in client.iter_json_items(
                    f"http://127.0.0.1:{port}/feed",
                    prefix="products.item",
                    source="fixture",
                    adaptive=limiter,
                ):
                    ids.append(int(item["id"]))
                assert ids == list(range(25))
        finally:
            await runner.cleanup()

    asyncio.run(scenario())


def test_perf_gate_accepts_reasonable_shared_runner_variance(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    current = tmp_path / "current.json"
    baseline.write_text(
        json.dumps({"results": [{"observations": 1000, "observations_per_s": 2000, "peak_rss_mb": 100, "p95_event_loop_lag_ms": 5}]}),
        encoding="utf-8",
    )
    current.write_text(
        json.dumps({"results": [{"observations": 1000, "observations_per_s": 1200, "peak_rss_mb": 150, "p95_event_loop_lag_ms": 20}]}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "scripts" / "check_perf_regression.py"),
            "--baseline",
            str(baseline),
            "--current",
            str(current),
        ],
        check=False,
    )
    assert result.returncode == 0
