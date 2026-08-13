from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from .distributed_security import build_client_ssl_context
from .distributed_service import SecureDistributedCycleEngine
from .event_log import EventJournal
from .learning_refresh import LearningCatalogRefreshEngine
from .service_runtime import RuntimeMetrics, ServiceHealth, ServiceHealthServer
from .telemetry_runtime import OtelRuntime


def _summary_json(summary: dict[str, object]) -> str:
    return json.dumps({"run_id": summary["run_id"], "observation_count": summary["observation_count"], "errors": summary["errors"], "runtime": summary["runtime"]}, sort_keys=True)


def _read_secret(value: str | None, path: str | None, env_name: str) -> str:
    if value: return value
    if path: return Path(path).read_text(encoding="utf-8").strip()
    return os.environ.get(env_name, "").strip()


@asynccontextmanager
async def _engine(args: argparse.Namespace, telemetry: OtelRuntime) -> AsyncIterator[Any]:
    if args.distributed_coordinator:
        token = await asyncio.to_thread(_read_secret, args.distributed_admin_token, args.distributed_admin_token_file, "LPLLM_ADMIN_TOKEN")
        if not token:
            raise RuntimeError("distributed service mode requires --distributed-admin-token, --distributed-admin-token-file or LPLLM_ADMIN_TOKEN")
        ssl_context = None
        if args.distributed_tls_ca or args.distributed_tls_cert or args.distributed_tls_insecure_skip_verify:
            ssl_context = await asyncio.to_thread(build_client_ssl_context, ca=args.distributed_tls_ca, cert=args.distributed_tls_cert, key=args.distributed_tls_key, insecure_skip_verify=args.distributed_tls_insecure_skip_verify)
        async with SecureDistributedCycleEngine(args.config, coordinator=args.distributed_coordinator, admin_token=token, history_path=args.history, output_path=args.output, poll_s=args.distributed_poll_s, timeout_s=args.distributed_timeout_s, ssl_context=ssl_context, telemetry=telemetry) as engine:
            yield engine
    else:
        telemetry.start()
        try:
            async with LearningCatalogRefreshEngine(args.config, history_path=args.history, output_path=args.output, cache_path=args.cache, debug_dir=args.debug_dir) as engine:
                yield engine
        finally:
            telemetry.shutdown()


async def serve(args: argparse.Namespace) -> int:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try: loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError): pass
    cycles = 0
    health = ServiceHealth(readiness_max_age_s=args.readiness_max_age)
    metrics = RuntimeMetrics(labels={"service": "discovery", "mode": "distributed" if args.distributed_coordinator else "local"})
    server = ServiceHealthServer(health, metrics, host=args.health_host, port=args.health_port)
    telemetry = OtelRuntime(endpoint=args.otlp_endpoint, service_name="lowpower-llm-cluster-discovery")
    events = EventJournal(args.event_log)
    mode = "scheduled" if args.interval is not None else "continuous"
    await events.emit("service_starting", mode=mode, config=str(args.config), history=str(args.history), debug_dir=str(args.debug_dir))
    async with _engine(args, telemetry) as engine:
        health.mark_started(); await server.start()
        await events.emit("service_started", mode=mode, health_port=args.health_port, debug_dir=str(args.debug_dir))
        try:
            while not stop.is_set() and (args.cycles is None or cycles < args.cycles):
                started = time.monotonic()
                await events.emit("cycle_started", cycle=cycles + 1, mode=mode)
                try:
                    with telemetry.span("service.refresh", {"refresh.mode": "distributed" if args.distributed_coordinator else "local"}):
                        summary = await engine.run_once()
                    errors = summary.get("errors", {})
                    health.mark_cycle(ok=not bool(errors), error="; ".join(str(value) for value in errors.values()))
                    metrics.update_cycle(summary)
                    telemetry.counter_add("refresh_cycles", 1, {"ok": str(not bool(errors)).lower()})
                    print(await asyncio.to_thread(_summary_json, summary), flush=True)
                    runtime = summary.get("runtime", {}) if isinstance(summary.get("runtime"), dict) else {}
                    quality = runtime.get("source_quality_learning", {}) if isinstance(runtime.get("source_quality_learning"), dict) else {}
                    scheduler = quality.get("scheduler", {}) if isinstance(quality.get("scheduler"), dict) else {}
                    await events.emit(
                        "cycle_completed",
                        cycle=cycles + 1,
                        run_id=summary.get("run_id"),
                        observation_count=summary.get("observation_count", 0),
                        change_count=len(summary.get("changes", [])),
                        errors=errors,
                        selected_sources=scheduler.get("selected_sources"),
                        skipped_source_count=len(scheduler.get("skipped_sources", [])) if isinstance(scheduler.get("skipped_sources"), list) else 0,
                        duration_ms=round((time.monotonic() - started) * 1000, 3),
                    )
                except Exception as exc:
                    health.mark_cycle(ok=False, error=f"{type(exc).__name__}: {exc}")
                    metrics.inc("refresh_cycle_exceptions_total")
                    telemetry.counter_add("refresh_cycle_exceptions", 1, {"type": type(exc).__name__})
                    await events.emit("cycle_error", cycle=cycles + 1, error=f"{type(exc).__name__}: {exc}")
                    raise
                cycles += 1
                if args.cycles is not None and cycles >= args.cycles: break
                if args.interval is None:
                    await asyncio.sleep(0)
                    continue
                delay = max(0.0, args.interval - (time.monotonic() - started))
                if delay:
                    await events.emit("cycle_waiting", cycle=cycles, delay_s=round(delay, 3))
                    try: await asyncio.wait_for(stop.wait(), timeout=delay)
                    except TimeoutError: pass
        finally:
            await events.emit("service_stopping", cycles=cycles)
            health.mark_stopping(); await server.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Long-running LowPowerLLMCluster discovery service; continuous scanning is the default")
    parser.add_argument("--config", required=True); parser.add_argument("--history", default="results/catalog-history.sqlite3"); parser.add_argument("--output", default="results/discovery-latest.json"); parser.add_argument("--cache", default="results/catalog-http-cache.json")
    parser.add_argument("--debug-dir", default="results/debug", help="structured sanitized runtime logs and per-run debug artifacts")
    parser.add_argument("--interval", type=float, default=None, help="optional seconds between scan starts; omit for continuous back-to-back scanning")
    parser.add_argument("--cycles", type=int); parser.add_argument("--event-log", default="results/events.jsonl"); parser.add_argument("--health-host", default="127.0.0.1"); parser.add_argument("--health-port", type=int, default=8787); parser.add_argument("--readiness-max-age", type=float, default=900.0)
    parser.add_argument("--distributed-coordinator", help="use authenticated v2 remote source workers instead of local source execution")
    parser.add_argument("--distributed-admin-token"); parser.add_argument("--distributed-admin-token-file")
    parser.add_argument("--distributed-poll-s", type=float, default=1.0); parser.add_argument("--distributed-timeout-s", type=float, default=3600.0)
    parser.add_argument("--distributed-tls-ca"); parser.add_argument("--distributed-tls-cert"); parser.add_argument("--distributed-tls-key"); parser.add_argument("--distributed-tls-insecure-skip-verify", action="store_true")
    parser.add_argument("--otlp-endpoint", help="optional OTLP/HTTP base endpoint; requires the telemetry extra")
    args = parser.parse_args()
    timing_values = [args.readiness_max_age, args.distributed_poll_s, args.distributed_timeout_s]
    if args.interval is not None: timing_values.append(args.interval)
    if min(timing_values) <= 0 or args.health_port < 1:
        parser.error("interval (when supplied), readiness, distributed timing and health-port values must be positive")
    if args.cycles is not None and args.cycles < 1: parser.error("--cycles must be >= 1")
    return asyncio.run(serve(args))


if __name__ == "__main__": raise SystemExit(main())
