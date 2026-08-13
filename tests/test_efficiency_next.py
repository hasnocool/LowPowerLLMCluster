# tests/test_efficiency_next.py
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from aiohttp import web

from lowpower_llm_cluster.catalog_refresh import run_discovery_service
from lowpower_llm_cluster.discovery import ProductObservation
from lowpower_llm_cluster.history import CatalogHistory
from lowpower_llm_cluster.http_runtime import AdaptiveConcurrency, AsyncHttpClient, DiscoveryCache
from lowpower_llm_cluster.runtime import map_sync_bounded_iter
from lowpower_llm_cluster.streaming_discovery import CachedJsonLdProductAdapter


async def _start_server(handler):
    app = web.Application()
    app.router.add_get("/product", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    return runner, f"http://127.0.0.1:{port}/product"


def test_conditional_get_reuses_cached_parsed_observations(tmp_path: Path) -> None:
    async def scenario() -> None:
        state = {"hits": 0}

        async def handler(request: web.Request) -> web.Response:
            state["hits"] += 1
            if request.headers.get("If-None-Match") == '"v1"':
                return web.Response(status=304, headers={"ETag": '"v1"'})
            body = '<script type="application/ld+json">{"@type":"Product","name":"Cached","sku":"C1","offers":{"price":"10","priceCurrency":"USD"}}</script>'
            return web.Response(text=body, headers={"ETag": '"v1"'})

        runner, url = await _start_server(handler)
        try:
            cache = await DiscoveryCache.open(tmp_path / "cache.json")
            async with AsyncHttpClient(concurrency=2, per_host=2, retry_jitter_s=0) as client:
                adapter = CachedJsonLdProductAdapter(
                    "vendor", [url], client, cache=cache,
                    adaptive=AdaptiveConcurrency(minimum=1, maximum=1),
                )
                first = await adapter.discover()
                second = await adapter.discover()
                assert first[0].sku == "C1" and second[0].sku == "C1"
                assert client.metrics()["not_modified"] == 1
                assert cache.metrics()["not_modified_hits"] == 1
                assert cache.metrics()["estimated_bytes_saved"] > 0
            await cache.flush()
            reopened = await DiscoveryCache.open(tmp_path / "cache.json")
            assert reopened.observations(url)[0].title == "Cached"  # type: ignore[index]
            assert state["hits"] == 2
        finally:
            await runner.cleanup()

    asyncio.run(scenario())


def test_retry_after_and_rate_limit_telemetry() -> None:
    async def scenario() -> None:
        state = {"hits": 0}

        async def handler(request: web.Request) -> web.Response:
            state["hits"] += 1
            if state["hits"] == 1:
                return web.Response(status=429, headers={"Retry-After": "0"})
            return web.Response(text="ok")

        runner, url = await _start_server(handler)
        try:
            async with AsyncHttpClient(
                concurrency=1,
                per_host=1,
                retry_attempts=2,
                retry_backoff_base_s=0,
                retry_backoff_max_s=0,
                retry_jitter_s=0,
            ) as client:
                response = await client.get_response(url, source="fixture")
                assert response.payload == b"ok"
                metrics = client.metrics()
                assert metrics["attempts"] == 2
                assert metrics["retries"] == 1
                assert metrics["rate_limits"] == 1
                assert metrics["sources"]["fixture"]["rate_limits"] == 1
        finally:
            await runner.cleanup()

    asyncio.run(scenario())


def test_adaptive_concurrency_decreases_then_recovers() -> None:
    async def scenario() -> None:
        limiter = AdaptiveConcurrency(minimum=1, maximum=4, initial=4, success_window=2, latency_target_ms=100)
        await limiter.observe(latency_ms=1000, success=False, rate_limited=True)
        assert limiter.current == 2
        await limiter.observe(latency_ms=1000, success=False, rate_limited=True)
        assert limiter.current == 1
        await limiter.observe(latency_ms=10, success=True)
        await limiter.observe(latency_ms=10, success=True)
        for _ in range(20):
            await limiter.observe(latency_ms=10, success=True)
        assert limiter.current > 1
        assert limiter.metrics()["decreases"] == 2

    asyncio.run(scenario())


def test_incremental_history_batches_complete_refresh(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with CatalogHistory(tmp_path / "history.sqlite3") as history:
            run_id = await history.begin_refresh()
            seen: dict[str, set[str]] = {"fixture": set()}
            for offset in range(0, 300, 50):
                batch = [
                    ProductObservation(
                        source="fixture",
                        source_id=str(index),
                        listing_url=f"https://example.test/{index}",
                        title=f"Item {index}",
                        price=float(index + 1),
                    )
                    for index in range(offset, offset + 50)
                ]
                seen["fixture"].update(item.source_id for item in batch)
                await history.record_batch(run_id, batch)
            changes = await history.finish_refresh(run_id, source_names=["fixture"], seen_by_source=seen)
            assert changes == ()
            rows = await history.price_history("fixture", "299")
            assert rows[0]["price"] == 300.0

    asyncio.run(scenario())


def test_streaming_sync_map_does_not_require_materialized_input() -> None:
    async def scenario() -> None:
        produced = 0

        def values():
            nonlocal produced
            for value in range(100):
                produced += 1
                yield value

        results = []
        async for _, result in map_sync_bounded_iter(values(), lambda value: value + 1, workers=3, queue_size=2):
            results.append(result)
        assert produced == 100
        assert sorted(results) == list(range(1, 101))

    asyncio.run(scenario())


def test_service_reuses_cache_across_refresh_cycles(tmp_path: Path) -> None:
    async def scenario() -> None:
        state = {"hits": 0}

        async def handler(request: web.Request) -> web.Response:
            state["hits"] += 1
            if request.headers.get("If-None-Match") == '"stable"':
                return web.Response(status=304, headers={"ETag": '"stable"'})
            body = '<script type="application/ld+json">{"@type":"Product","name":"Stable","sku":"S1","offers":{"price":"99","priceCurrency":"USD"}}</script>'
            return web.Response(text=body, headers={"ETag": '"stable"'})

        runner, url = await _start_server(handler)
        try:
            config = {
                "agent_workers": 2,
                "subworkers_per_agent": 2,
                "normalize_workers": 2,
                "queue_size": 4,
                "http_concurrency": 4,
                "http_per_host": 2,
                "retry_jitter_s": 0,
                "sources": [{"name": "vendor", "type": "jsonld", "urls": [url]}],
            }
            config_path = tmp_path / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            summaries = await run_discovery_service(
                config_path,
                history_path=tmp_path / "history.sqlite3",
                output_path=tmp_path / "latest.json",
                cache_path=tmp_path / "cache.json",
                interval_s=0.01,
                cycles=2,
            )
            assert len(summaries) == 2
            assert summaries[0]["observation_count"] == 1
            assert summaries[1]["observation_count"] == 1
            assert summaries[1]["runtime"]["http"]["not_modified"] >= 1
            payload = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
            assert payload["observations"][0]["sku"] == "S1"
            assert state["hits"] == 2
        finally:
            await runner.cleanup()

    asyncio.run(scenario())
