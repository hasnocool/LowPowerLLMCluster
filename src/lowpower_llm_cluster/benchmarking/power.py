# src/lowpower_llm_cluster/benchmarking/power.py
from __future__ import annotations

import asyncio
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from statistics import mean, median
from typing import Any

from .models import PowerWindow

_FLOAT_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")


class PowerProbe(ABC):
    """Asynchronous instantaneous power source.

    A probe's scope is part of the measurement. Only ``complete_node_input``
    is accepted for canonical tokens/joule or specialist units/joule metrics.
    """

    scope: str
    source: str

    @abstractmethod
    async def sample_watts(self) -> float:
        raise NotImplementedError


@dataclass
class CommandPowerProbe(PowerProbe):
    argv: list[str]
    scope: str
    source: str = "external_command"
    timeout_s: float = 5.0

    async def sample_watts(self) -> float:
        if not self.argv:
            raise ValueError("power command argv may not be empty")
        process = await asyncio.create_subprocess_exec(
            *self.argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_s)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError("power probe command timed out") from None
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"power probe failed with exit {process.returncode}: {message}")
        output = stdout.decode("utf-8", errors="replace")
        match = _FLOAT_RE.search(output)
        if not match:
            raise RuntimeError(f"power probe did not emit a numeric watt value: {output!r}")
        watts = float(match.group(0))
        if watts < 0:
            raise RuntimeError(f"power probe returned negative watts: {watts}")
        return watts


@dataclass
class StaticMeasuredPowerProbe(PowerProbe):
    """A manually supplied *measured* value, useful with a handheld meter.

    This must never be populated from TDP/TBP/spec-sheet values. The profile
    has to mark the source and scope explicitly so the result remains auditable.
    """

    watts_by_phase: dict[str, float]
    scope: str
    source: str = "manual_measured"
    active_phase: str = "active"

    def set_phase(self, phase: str) -> None:
        self.active_phase = phase

    async def sample_watts(self) -> float:
        try:
            watts = float(self.watts_by_phase[self.active_phase])
        except KeyError as exc:
            raise RuntimeError(f"no static measured watt value for phase {self.active_phase!r}") from exc
        if watts < 0:
            raise RuntimeError(f"static measured watts may not be negative: {watts}")
        return watts


@dataclass(frozen=True)
class _TimedPowerSample:
    t: float
    watts: float


def build_power_probe(config: dict[str, Any] | None) -> PowerProbe | None:
    if not config or config.get("provider", "none") == "none":
        return None
    provider = str(config["provider"])
    scope = str(config.get("scope", "unknown"))
    if provider == "command":
        argv = [str(value) for value in config.get("argv", [])]
        return CommandPowerProbe(
            argv=argv,
            scope=scope,
            source=str(config.get("source", "external_command")),
            timeout_s=float(config.get("timeout_s", 5.0)),
        )
    if provider == "static_measured":
        watts = {str(key): float(value) for key, value in config.get("watts_by_phase", {}).items()}
        return StaticMeasuredPowerProbe(
            watts_by_phase=watts,
            scope=scope,
            source=str(config.get("source", "manual_measured")),
        )
    raise ValueError(f"unsupported power provider: {provider}")


async def _collect_samples(
    probe: PowerProbe,
    *,
    interval_s: float,
    stop: asyncio.Event,
    phase: str,
) -> list[_TimedPowerSample]:
    if isinstance(probe, StaticMeasuredPowerProbe):
        probe.set_phase(phase)
    samples: list[_TimedPowerSample] = []
    while not stop.is_set():
        sample_start = time.monotonic()
        watts = await probe.sample_watts()
        samples.append(_TimedPowerSample(sample_start, watts))
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
        except TimeoutError:
            pass
    return samples


def _integrate_energy(samples: list[_TimedPowerSample], start: float, end: float) -> float | None:
    if not samples or end <= start:
        return None
    if len(samples) == 1:
        return samples[0].watts * (end - start)

    energy = 0.0
    previous_t = start
    previous_w = samples[0].watts
    for sample in samples[1:]:
        t = min(max(sample.t, previous_t), end)
        dt = t - previous_t
        energy += ((previous_w + sample.watts) / 2.0) * dt
        previous_t = t
        previous_w = sample.watts
    if previous_t < end:
        energy += previous_w * (end - previous_t)
    return energy


async def measure_idle(
    probe: PowerProbe | None,
    *,
    duration_s: float,
    interval_s: float,
) -> PowerWindow | None:
    if probe is None or duration_s <= 0:
        return None
    stop = asyncio.Event()
    start = time.monotonic()
    task = asyncio.create_task(
        _collect_samples(probe, interval_s=interval_s, stop=stop, phase="idle")
    )
    await asyncio.sleep(duration_s)
    stop.set()
    samples = await task
    end = time.monotonic()
    values = [sample.watts for sample in samples]
    return PowerWindow(
        phase="idle",
        scope=probe.scope,
        source=probe.source,
        duration_s=end - start,
        samples_w=values,
        mean_w=float(mean(values)) if values else None,
        median_w=float(median(values)) if values else None,
        energy_j=_integrate_energy(samples, start, end),
    )


async def run_process_with_power(
    argv: list[str],
    *,
    phase: str,
    probe: PowerProbe | None,
    interval_s: float,
    timeout_s: float | None,
    env: dict[str, str] | None = None,
) -> tuple[int, bytes, bytes, PowerWindow | None]:
    """Run a command without blocking the event loop while sampling power."""
    if not argv:
        raise ValueError("benchmark command argv may not be empty")

    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stop = asyncio.Event()
    start = time.monotonic()
    sampler: asyncio.Task[list[_TimedPowerSample]] | None = None
    if probe is not None:
        sampler = asyncio.create_task(
            _collect_samples(probe, interval_s=interval_s, stop=stop, phase=phase)
        )

    timed_out = False
    try:
        communicate = process.communicate()
        if timeout_s is None:
            stdout, stderr = await communicate
        else:
            stdout, stderr = await asyncio.wait_for(communicate, timeout=timeout_s)
    except TimeoutError:
        timed_out = True
        process.kill()
        stdout, stderr = await process.communicate()
    finally:
        stop.set()

    end = time.monotonic()
    samples = await sampler if sampler is not None else []
    if timed_out:
        raise RuntimeError(f"benchmark phase {phase!r} timed out after {timeout_s}s")
    values = [sample.watts for sample in samples]
    window = None
    if probe is not None:
        window = PowerWindow(
            phase=phase,
            scope=probe.scope,
            source=probe.source,
            duration_s=end - start,
            samples_w=values,
            mean_w=float(mean(values)) if values else None,
            median_w=float(median(values)) if values else None,
            energy_j=_integrate_energy(samples, start, end),
        )
    return int(process.returncode), stdout, stderr, window
