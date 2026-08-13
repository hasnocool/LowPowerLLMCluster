from __future__ import annotations

import argparse
import asyncio
import json
import signal
import time

from .catalog_refresh import CatalogRefreshEngine
from .service_runtime import RuntimeMetrics, ServiceHealth, ServiceHealthServer


def _summary_json(summary: dict[str, object]) -> str:
    return json.dumps({"run_id": summary["run_id"], "observation_count": summary["observation_count"], "errors": summary["errors"], "runtime": summary["runtime"]}, sort_keys=True)


async def serve(args: argparse.Namespace) -> int:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass
    cycles = 0
    health = ServiceHealth(readiness_max_age_s=args.readiness_max_age)
    metrics = RuntimeMetrics(labels={"service": "discovery"})
    server = ServiceHealthServer(health, metrics, host=args.health_host, port=args.health_port)
    async with CatalogRefreshEngine(args.config, history_path=args.history, output_path=args.output, cache_path=args.cache) as engine:
        health.mark_started()
        await server.start()
        try:
            while not stop.is_set() and (args.cycles is None or cycles < args.cycles):
                started = time.monotonic()
                try:
                    summary = await engine.run_once()
                    errors = summary.get("errors", {})
                    health.mark_cycle(ok=not bool(errors), error="; ".join(errors.values()))
                    metrics.update_cycle(summary)
                    print(await asyncio.to_thread(_summary_json, summary), flush=True)
                except Exception as exc:
                    health.mark_cycle(ok=False, error=f"{type(exc).__name__}: {exc}")
                    metrics.inc("refresh_cycle_exceptions_total")
                    raise
                cycles += 1
                if args.cycles is not None and cycles >= args.cycles:
                    break
                delay = max(0.0, args.interval - (time.monotonic() - started))
                try:
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                except TimeoutError:
                    pass
        finally:
            health.mark_stopping()
            await server.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Long-running LowPowerLLMCluster discovery refresh service")
    parser.add_argument("--config", required=True)
    parser.add_argument("--history", default="results/catalog-history.sqlite3")
    parser.add_argument("--output", default="results/discovery-latest.json")
    parser.add_argument("--cache", default="results/catalog-http-cache.json")
    parser.add_argument("--interval", type=float, default=300.0)
    parser.add_argument("--cycles", type=int)
    parser.add_argument("--health-host", default="127.0.0.1")
    parser.add_argument("--health-port", type=int, default=8787)
    parser.add_argument("--readiness-max-age", type=float, default=900.0)
    args = parser.parse_args()
    if args.interval <= 0 or args.health_port < 1 or args.readiness_max_age <= 0:
        parser.error("interval, health-port and readiness-max-age must be positive")
    if args.cycles is not None and args.cycles < 1:
        parser.error("--cycles must be >= 1")
    return asyncio.run(serve(args))


if __name__ == "__main__":
    raise SystemExit(main())
