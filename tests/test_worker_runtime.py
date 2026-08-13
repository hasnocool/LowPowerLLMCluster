# tests/test_worker_runtime.py
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from lowpower_llm_cluster.discovery import DiscoveryPipeline, ProductObservation, StaticSourceAdapter
from lowpower_llm_cluster.history import CatalogHistory
from lowpower_llm_cluster.runtime import WorkerSettings, map_sync_bounded


def test_worker_settings_backward_compatibility_and_bounds() -> None:
    settings = WorkerSettings.from_mapping({"concurrency": 8, "timeout_s": 9})
    assert settings.http_concurrency == 8
    assert settings.http_per_host == 4
    assert settings.timeout_s == 9


def test_bounded_sync_map_preserves_order() -> None:
    async def scenario() -> list[int]:
        return await map_sync_bounded(range(20), lambda value: value * value, workers=3, queue_size=2)

    assert asyncio.run(scenario()) == [value * value for value in range(20)]


def test_discovery_uses_multiple_agent_workers() -> None:
    class Adapter:
        def __init__(self, name: str, state: dict[str, int]) -> None:
            self.name = name
            self.state = state

        async def discover(self):
            self.state["in_flight"] += 1
            self.state["max_in_flight"] = max(self.state["max_in_flight"], self.state["in_flight"])
            await asyncio.sleep(0.03)
            self.state["in_flight"] -= 1
            return [ProductObservation(source=self.name, source_id=self.name, listing_url=f"https://example.com/{self.name}", title=self.name)]

    state = {"in_flight": 0, "max_in_flight": 0}
    adapters = [Adapter(str(index), state) for index in range(6)]
    result = asyncio.run(DiscoveryPipeline(adapters, worker_count=3, queue_size=2).run())
    assert len(result.observations) == 6
    assert 2 <= state["max_in_flight"] <= 3
    assert result.metrics["agent_workers"] == 3


def test_history_single_writer_handles_concurrent_callers(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with CatalogHistory(tmp_path / "history.sqlite3") as history:
            first = ProductObservation(source="fixture", source_id="a", listing_url="https://example.com/a", title="A", price=1)
            await history.record_refresh([first], source_names=["fixture"])
            rows = await asyncio.gather(*(history.price_history("fixture", "a") for _ in range(8)))
            assert all(row[0]["price"] == 1 for row in rows)

    asyncio.run(scenario())


def test_worker_counts_above_available_work_do_not_deadlock() -> None:
    async def scenario() -> None:
        adapter = StaticSourceAdapter(
            "only",
            [ProductObservation(source="only", source_id="1", listing_url="https://example.test/1", title="One")],
        )
        result = await asyncio.wait_for(
            DiscoveryPipeline([adapter], worker_count=8, queue_size=1).run(),
            timeout=1.0,
        )
        assert len(result.observations) == 1

    asyncio.run(scenario())


def test_jsonld_subworkers_above_url_count_do_not_deadlock() -> None:
    from lowpower_llm_cluster.discovery import JsonLdProductAdapter

    class FakeClient:
        async def get_text(self, url: str) -> str:
            return (
                '<script type="application/ld+json">'
                '{"@type":"Product","name":"One","sku":"ONE",'
                '"offers":{"price":"1","priceCurrency":"USD"}}'
                '</script>'
            )

    async def scenario() -> None:
        adapter = JsonLdProductAdapter(
            "vendor", ["https://example.test/one"], FakeClient(), subworkers=8, queue_size=1
        )  # type: ignore[arg-type]
        records = await asyncio.wait_for(adapter.discover(), timeout=1.0)
        assert len(records) == 1

    asyncio.run(scenario())
