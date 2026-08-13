# src/lowpower_llm_cluster/service_cli.py
from __future__ import annotations

import argparse
import asyncio
import json
import signal
import time

from .catalog_refresh import CatalogRefreshEngine


def _summary_json(summary: dict[str, object]) -> str:
    return json.dumps({
        "run_id": summary["run_id"],
        "observation_count": summary["observation_count"],
        "errors": summary["errors"],
        "runtime": summary["runtime"],
    }, sort_keys=True)


async def serve(args: argparse.Namespace) -> int:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass

    cycles = 0
    async with CatalogRefreshEngine(
        args.config,
        history_path=args.history,
        output_path=args.output,
        cache_path=args.cache,
    ) as engine:
        while not stop.is_set() and (args.cycles is None or cycles < args.cycles):
            started = time.monotonic()
            summary = await engine.run_once()
            print(await asyncio.to_thread(_summary_json, summary), flush=True)
            cycles += 1
            if args.cycles is not None and cycles >= args.cycles:
                break
            delay = max(0.0, args.interval - (time.monotonic() - started))
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except TimeoutError:
                pass
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Long-running LowPowerLLMCluster discovery refresh service")
    parser.add_argument("--config", required=True)
    parser.add_argument("--history", default="results/catalog-history.sqlite3")
    parser.add_argument("--output", default="results/discovery-latest.json")
    parser.add_argument("--cache", default="results/catalog-http-cache.json")
    parser.add_argument("--interval", type=float, default=300.0, help="seconds between cycle starts")
    parser.add_argument("--cycles", type=int, help="optional finite cycle count; omit to run until SIGINT/SIGTERM")
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    if args.cycles is not None and args.cycles < 1:
        parser.error("--cycles must be >= 1")
    return asyncio.run(serve(args))


if __name__ == "__main__":
    raise SystemExit(main())
