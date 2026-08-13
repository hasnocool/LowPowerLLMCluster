from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

from .catalog_refresh import ObservationSpool
from .discovery import ProductObservation
from .history import CatalogHistory
from .normalization import normalize_observation
from .secure_distributed import SecureCoordinatorClient
from .telemetry_runtime import OtelRuntime


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_batch(values: tuple[ProductObservation, ...], trusts: dict[str, float]) -> list[dict[str, Any]]:
    return [normalize_observation(item, source_trust=trusts.get(item.source, 0.65)) for item in values]


class SecureDistributedCycleEngine:
    """Daemon-friendly submit/wait/stream/collect engine for secure v2 coordinators."""

    def __init__(
        self,
        config_path: Path | str,
        *,
        coordinator: str,
        admin_token: str,
        history_path: Path | str,
        output_path: Path | str,
        poll_s: float = 1.0,
        timeout_s: float = 3600.0,
        ssl_context: Any = None,
        telemetry: OtelRuntime | None = None,
    ) -> None:
        if poll_s <= 0 or timeout_s <= 0:
            raise ValueError("poll_s and timeout_s must be positive")
        self.config_path = Path(config_path)
        self.coordinator = coordinator
        self.admin_token = admin_token
        self.history_path = Path(history_path)
        self.output_path = Path(output_path)
        self.poll_s = poll_s
        self.timeout_s = timeout_s
        self.ssl_context = ssl_context
        self.telemetry = telemetry or OtelRuntime()
        self.config: dict[str, Any] = {}
        self.client: SecureCoordinatorClient | None = None
        self._started = False

    async def __aenter__(self) -> "SecureDistributedCycleEngine":
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._started:
            return
        self.config = await asyncio.to_thread(_read_json, self.config_path)
        self.telemetry.start()
        self.client = SecureCoordinatorClient(self.coordinator, admin_token=self.admin_token, ssl_context=self.ssl_context)
        try:
            await self.client.__aenter__()
        except BaseException:
            self.client = None
            self.telemetry.shutdown()
            raise
        self._started = True

    async def close(self) -> None:
        if not self._started:
            return
        if self.client is not None:
            await self.client.__aexit__(None, None, None)
            self.client = None
        self.telemetry.shutdown()
        self._started = False

    async def run_once(self) -> dict[str, Any]:
        await self.start()
        assert self.client is not None
        cycle_id = f"service-{int(time.time())}-{uuid.uuid4().hex[:10]}"
        started = time.perf_counter()
        sources = list(self.config.get("sources", ()))
        trusts = {str(source["name"]): float(source.get("source_trust", 0.65)) for source in sources}
        with self.telemetry.span("distributed.refresh", {"cycle.id": cycle_id, "source.count": len(sources)}):
            await self.client.submit_cycle(sources, cycle_id)
            deadline = time.monotonic() + self.timeout_s
            while True:
                status = await self.client.cycle_status(cycle_id)
                if status.get("done"):
                    break
                if time.monotonic() >= deadline:
                    await self.client.cancel_cycle(cycle_id)
                    raise TimeoutError(f"distributed cycle {cycle_id} exceeded {self.timeout_s:g}s")
                await asyncio.sleep(self.poll_s)

            spool = ObservationSpool(self.output_path)
            await spool.reset()
            seen: dict[str, set[str]] = {}
            states: dict[str, str] = {}
            errors: dict[str, str] = {}
            changes = []
            batch_count = 0
            async with CatalogHistory(self.history_path) as history:
                run_id = await history.begin_refresh()
                try:
                    async for row in self.client.iter_cycle_results(cycle_id):
                        source = str(row.get("source_name", ""))
                        state = str(row.get("state", ""))
                        if source:
                            states[source] = state
                        if state in {"failed", "canceled"}:
                            errors[source] = str(row.get("error") or state)
                        raw_observations = row.get("observations", ())
                        if not raw_observations:
                            continue
                        values = tuple(ProductObservation(**raw) for raw in raw_observations)
                        seen.setdefault(source, set()).update(item.source_id for item in values)
                        changes.extend(await history.record_batch(run_id, values))
                        normalized = await asyncio.to_thread(_normalize_batch, values, trusts)
                        await spool.append(normalized)
                        batch_count += 1
                    successful = sorted(source for source, state in states.items() if state == "completed")
                    changes.extend(await history.finish_refresh(
                        run_id,
                        source_names=successful,
                        seen_by_source=seen,
                        disappearance_after_runs=int(self.config.get("disappearance_after_runs", 2)),
                    ))
                except BaseException:
                    await history.abort_refresh(run_id)
                    raise

            metadata: dict[str, Any] = {
                "run_id": run_id,
                "distributed_cycle_id": cycle_id,
                "observation_count": spool.count,
                "errors": errors,
                "changes": [
                    {"source": item.source, "source_id": item.source_id, "change_type": item.change_type, "previous": item.previous, "current": item.current}
                    for item in changes
                ],
                "runtime": {
                    "distributed": True,
                    "secure_protocol": "v2",
                    "streamed_result_batches": batch_count,
                    "remote_tasks": status,
                    "total_ms": round((time.perf_counter() - started) * 1000.0, 3),
                },
            }
            await spool.finalize(metadata)
            self.telemetry.counter_add("distributed_refresh_observations", spool.count)
            self.telemetry.counter_add("distributed_refresh_cycles", 1, {"ok": str(not bool(errors)).lower()})
            return metadata
