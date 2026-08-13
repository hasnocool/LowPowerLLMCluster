# scripts/benchmark_discovery_pipeline.py
from __future__ import annotations

import argparse
import asyncio
import json
import resource
import statistics
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from lowpower_llm_cluster.discovery import ProductObservation
from lowpower_llm_cluster.history import CatalogHistory
from lowpower_llm_cluster.normalization import normalize_observation
from lowpower_llm_cluster.runtime import map_sync_bounded
from lowpower_llm_cluster.streaming_discovery import StreamingDiscoveryPipeline


@dataclass(frozen=True, slots=True)
class PerfResult:
    observations: int
    elapsed_s: float
    observations_per_s: float
    peak_rss_mb: float
    max_event_loop_lag_ms: float
    p95_event_loop_lag_ms: float


class SyntheticBatchAdapter:
    def __init__(self, count: int, *, batch_size: int = 256) -> None:
        self.name = "synthetic"
        self.count = count
        self.batch_size = batch_size

    async def discover_batches(self):
        for start in range(0, self.count, self.batch_size):
            stop = min(self.count, start + self.batch_size)
            yield [
                ProductObservation(
                    source=self.name,
                    source_id=str(index),
                    listing_url=f"https://example.invalid/items/{index}",
                    title=f"Synthetic Ryzen mini PC {index}",
                    price=100.0 + (index % 500),
                    manufacturer="Synthetic",
                    sku=f"SKU-{index}",
                    attributes={"cpu": "Ryzen", "memory_capacity_gb": 32, "form_factor": "mini pc"},
                )
                for index in range(start, stop)
            ]
            await asyncio.sleep(0)

    async def discover(self):
        result = []
        async for batch in self.discover_batches():
            result.extend(batch)
        return result


async def _lag_monitor(stop: asyncio.Event, samples: list[float], interval_s: float = 0.01) -> None:
    expected = time.perf_counter() + interval_s
    while not stop.is_set():
        await asyncio.sleep(interval_s)
        now = time.perf_counter()
        samples.append(max(0.0, (now - expected) * 1000.0))
        expected = now + interval_s


async def benchmark(count: int, *, batch_size: int, workers: int) -> PerfResult:
    lag_samples: list[float] = []
    stop = asyncio.Event()
    lag_task = asyncio.create_task(_lag_monitor(stop, lag_samples))
    started = time.perf_counter()
    seen: dict[str, set[str]] = {"synthetic": set()}
    adapter = SyntheticBatchAdapter(count, batch_size=batch_size)
    pipeline = StreamingDiscoveryPipeline([adapter], worker_count=1, queue_size=8)
    with tempfile.TemporaryDirectory(prefix="lpllm-perf-") as tmp:
        async with CatalogHistory(Path(tmp) / "history.sqlite3") as history:
            run_id = await history.begin_refresh()
            processed = 0
            async for batch in pipeline.stream():
                if batch.error:
                    raise RuntimeError(batch.error)
                seen["synthetic"].update(item.source_id for item in batch.observations)
                async with asyncio.TaskGroup() as group:
                    persist = group.create_task(history.record_batch(run_id, batch.observations))
                    normalize = group.create_task(map_sync_bounded(
                        batch.observations,
                        normalize_observation,
                        workers=workers,
                        queue_size=32,
                    ))
                await persist
                processed += len(normalize.result())
            await history.finish_refresh(run_id, source_names=["synthetic"], seen_by_source=seen)
            if processed != count:
                raise RuntimeError(f"processed {processed}, expected {count}")
    elapsed = time.perf_counter() - started
    stop.set()
    await lag_task
    peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mb = peak_kb / 1024.0
    ordered = sorted(lag_samples)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] if ordered else 0.0
    return PerfResult(
        observations=count,
        elapsed_s=round(elapsed, 4),
        observations_per_s=round(count / max(elapsed, 1e-9), 2),
        peak_rss_mb=round(peak_mb, 2),
        max_event_loop_lag_ms=round(max(lag_samples, default=0.0), 3),
        p95_event_loop_lag_ms=round(p95, 3),
    )


async def main_async(args: argparse.Namespace) -> int:
    results = [await benchmark(count, batch_size=args.batch_size, workers=args.workers) for count in args.counts]
    payload = {
        "results": [asdict(result) for result in results],
        "summary": {
            "median_observations_per_s": round(statistics.median(result.observations_per_s for result in results), 2),
            "max_event_loop_lag_ms": max(result.max_event_loop_lag_ms for result in results),
        },
    }
    text = json.dumps(payload, indent=2) + "\n"
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_text, text, encoding="utf-8")
    print(text, end="")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic E2E catalog refresh load benchmark")
    parser.add_argument("--counts", type=int, nargs="+", default=[100, 1000, 10000])
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output")
    args = parser.parse_args()
    if any(count < 1 for count in args.counts) or args.batch_size < 1 or args.workers < 1:
        parser.error("counts, batch-size and workers must be positive")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
