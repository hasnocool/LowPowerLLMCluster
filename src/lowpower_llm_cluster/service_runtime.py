from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from aiohttp import web


def _prom_name(name: str) -> str:
    return "lowpower_llmcluster_" + "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.lower())


@dataclass(slots=True)
class RuntimeMetrics:
    """Dependency-light Prometheus metrics; OTel Collectors can scrape this endpoint."""
    counters: dict[str, float] = field(default_factory=dict)
    gauges: dict[str, float] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)

    def inc(self, name: str, value: float = 1.0) -> None:
        self.counters[name] = self.counters.get(name, 0.0) + float(value)

    def set(self, name: str, value: float) -> None:
        self.gauges[name] = float(value)

    def update_cycle(self, summary: Mapping[str, Any]) -> None:
        runtime = summary.get("runtime", {}) if isinstance(summary, Mapping) else {}
        http = runtime.get("http", {}) if isinstance(runtime, Mapping) else {}
        self.inc("refresh_cycles_total")
        self.inc("refresh_errors_total", len(summary.get("errors", {})))
        self.set("last_observation_count", float(summary.get("observation_count", 0)))
        self.set("last_refresh_duration_ms", float(runtime.get("total_ms", 0)))
        self.set("http_requests_total_snapshot", float(http.get("requests", 0)))
        self.set("http_rate_limits_total_snapshot", float(http.get("rate_limits", 0)))
        self.set("http_retries_total_snapshot", float(http.get("retries", 0)))
        cache = runtime.get("conditional_cache", {}) if isinstance(runtime, Mapping) else {}
        circuits = runtime.get("circuit_sources", {}) if isinstance(runtime, Mapping) else {}
        batches = runtime.get("adaptive_batches", {}) if isinstance(runtime, Mapping) else {}
        self.set("cache_entries", float(cache.get("entries", 0)))
        self.set("cache_expired_entries_total_snapshot", float(cache.get("expired_entries", 0)))
        self.set("cache_evicted_entries_total_snapshot", float(cache.get("evicted_entries", 0)))
        self.set("circuits_open", float(sum(1 for value in circuits.values() if isinstance(value, Mapping) and value.get("state") == "open")))
        currents = [float(value.get("current", 0)) for value in batches.values() if isinstance(value, Mapping)]
        self.set("adaptive_batch_current_mean", sum(currents) / len(currents) if currents else 0.0)

    def snapshot(self) -> dict[str, Any]:
        return {"counters": dict(self.counters), "gauges": dict(self.gauges), "labels": dict(self.labels)}

    def prometheus(self) -> str:
        label_text = ""
        if self.labels:
            label_text = "{" + ",".join(f'{key}={json.dumps(value)}' for key, value in sorted(self.labels.items())) + "}"
        lines: list[str] = []
        for name, value in sorted(self.counters.items()):
            metric = _prom_name(name)
            lines.extend((f"# TYPE {metric} counter", f"{metric}{label_text} {value}"))
        for name, value in sorted(self.gauges.items()):
            metric = _prom_name(name)
            lines.extend((f"# TYPE {metric} gauge", f"{metric}{label_text} {value}"))
        return "\n".join(lines) + "\n"


@dataclass(slots=True)
class ServiceHealth:
    readiness_max_age_s: float = 900.0
    started: bool = False
    shutting_down: bool = False
    last_cycle_at: float | None = None
    last_cycle_ok: bool | None = None
    last_error: str = ""

    def mark_started(self) -> None:
        self.started = True
        self.shutting_down = False

    def mark_cycle(self, *, ok: bool, error: str = "") -> None:
        self.last_cycle_at = time.time()
        self.last_cycle_ok = ok
        self.last_error = error

    def mark_stopping(self) -> None:
        self.shutting_down = True

    def live(self) -> bool:
        return self.started and not self.shutting_down

    def ready(self) -> bool:
        if not self.live():
            return False
        if self.last_cycle_at is None:
            return True
        age = max(0.0, time.time() - self.last_cycle_at)
        return self.last_cycle_ok is not False and age <= self.readiness_max_age_s

    def snapshot(self) -> dict[str, Any]:
        age = None if self.last_cycle_at is None else max(0.0, time.time() - self.last_cycle_at)
        return {"live": self.live(), "ready": self.ready(), "last_cycle_age_s": age, "last_cycle_ok": self.last_cycle_ok, "last_error": self.last_error}


class ServiceHealthServer:
    def __init__(self, health: ServiceHealth, metrics: RuntimeMetrics, *, host: str = "127.0.0.1", port: int = 8787) -> None:
        self.health = health
        self.metrics = metrics
        self.host = host
        self.port = port
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        app.add_routes([web.get("/healthz", self._healthz), web.get("/readyz", self._readyz), web.get("/metrics", self._metrics), web.get("/v1/status", self._status)])
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, self.host, self.port).start()

    async def close(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _healthz(self, _: web.Request) -> web.Response:
        ok = self.health.live()
        return web.json_response(self.health.snapshot(), status=200 if ok else 503)

    async def _readyz(self, _: web.Request) -> web.Response:
        ok = self.health.ready()
        return web.json_response(self.health.snapshot(), status=200 if ok else 503)

    async def _metrics(self, _: web.Request) -> web.Response:
        return web.Response(text=self.metrics.prometheus(), content_type="text/plain")

    async def _status(self, _: web.Request) -> web.Response:
        return web.json_response({"health": self.health.snapshot(), "metrics": self.metrics.snapshot()})
