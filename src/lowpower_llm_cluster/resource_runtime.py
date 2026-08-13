from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    cpu_load_fraction: float
    available_memory_mb: float | None = None
    thermal_c: float | None = None
    power_budget_w: float | None = None
    energy_budget_wh: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return asdict(self)


def _available_memory_mb() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return float(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        pass
    return None


def _thermal_c() -> float | None:
    values: list[float] = []
    try:
        for path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
            try:
                raw = float(path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            value = raw / 1000.0 if raw > 500 else raw
            if -20 <= value <= 150:
                values.append(value)
    except OSError:
        return None
    return max(values) if values else None


def _snapshot_sync(*, power_budget_w: float | None, energy_budget_wh: float | None) -> ResourceSnapshot:
    cpus = max(1, os.cpu_count() or 1)
    try:
        load = max(0.0, os.getloadavg()[0] / cpus)
    except (AttributeError, OSError):
        load = 0.0
    return ResourceSnapshot(
        cpu_load_fraction=round(load, 4),
        available_memory_mb=_available_memory_mb(),
        thermal_c=_thermal_c(),
        power_budget_w=power_budget_w,
        energy_budget_wh=energy_budget_wh,
    )


async def sample_resources(*, power_budget_w: float | None = None, energy_budget_wh: float | None = None) -> ResourceSnapshot:
    return await asyncio.to_thread(_snapshot_sync, power_budget_w=power_budget_w, energy_budget_wh=energy_budget_wh)


@dataclass(frozen=True, slots=True)
class SchedulingRequirements:
    capabilities: tuple[str, ...] = ()
    labels: tuple[tuple[str, str], ...] = ()
    affinity: tuple[str, ...] = ()
    max_cpu_load: float | None = None
    max_thermal_c: float | None = None
    min_available_memory_mb: float | None = None
    min_power_budget_w: float | None = None

    @classmethod
    def from_source(cls, source: Mapping[str, Any]) -> "SchedulingRequirements":
        raw = dict(source.get("worker_requirements", {}) or {})
        labels_raw = dict(raw.get("labels", {}) or {})
        return cls(
            capabilities=tuple(sorted(str(item) for item in raw.get("capabilities", ()) if str(item))),
            labels=tuple(sorted((str(k), str(v)) for k, v in labels_raw.items())),
            affinity=tuple(str(item) for item in source.get("worker_affinity", raw.get("affinity", ())) if str(item)),
            max_cpu_load=float(raw["max_cpu_load"]) if raw.get("max_cpu_load") is not None else None,
            max_thermal_c=float(raw["max_thermal_c"]) if raw.get("max_thermal_c") is not None else None,
            min_available_memory_mb=float(raw["min_available_memory_mb"]) if raw.get("min_available_memory_mb") is not None else None,
            min_power_budget_w=float(raw["min_power_budget_w"]) if raw.get("min_power_budget_w") is not None else None,
        )

    def matches(self, *, worker_id: str, capabilities: set[str], labels: Mapping[str, str], resources: Mapping[str, Any], allow_steal: bool) -> tuple[bool, float, str]:
        missing = [item for item in self.capabilities if item not in capabilities]
        if missing:
            return False, 0.0, f"missing capabilities: {','.join(missing)}"
        for key, value in self.labels:
            if str(labels.get(key, "")) != value:
                return False, 0.0, f"label {key} mismatch"
        if self.affinity and worker_id not in self.affinity and not allow_steal:
            return False, 0.0, "waiting for affinity worker"

        cpu = resources.get("cpu_load_fraction")
        if self.max_cpu_load is not None:
            if cpu is None:
                return False, 0.0, "cpu load unavailable for hard task limit"
            if float(cpu) > self.max_cpu_load:
                return False, 0.0, "cpu load above task limit"

        thermal = resources.get("thermal_c")
        if self.max_thermal_c is not None:
            if thermal is None:
                return False, 0.0, "thermal reading unavailable for hard task limit"
            if float(thermal) > self.max_thermal_c:
                return False, 0.0, "thermal limit exceeded"

        memory = resources.get("available_memory_mb")
        if self.min_available_memory_mb is not None:
            if memory is None:
                return False, 0.0, "available memory unknown for hard task requirement"
            if float(memory) < self.min_available_memory_mb:
                return False, 0.0, "insufficient available memory"

        power = resources.get("power_budget_w")
        if self.min_power_budget_w is not None:
            if power is None:
                return False, 0.0, "power budget unavailable for hard task requirement"
            if float(power) < self.min_power_budget_w:
                return False, 0.0, "worker power budget below task requirement"

        score = 100.0
        if worker_id in self.affinity:
            score += 100.0
        score += 3.0 * len(self.capabilities)
        score += 1.0 * len(self.labels)
        if cpu is not None:
            score -= min(50.0, float(cpu) * 25.0)
        return True, score, "matched"
