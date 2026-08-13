from __future__ import annotations

import asyncio
import math
import resource
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker:
    """Async per-source circuit breaker with bounded half-open probes."""

    def __init__(
        self,
        *,
        failure_threshold: int = 4,
        recovery_timeout_s: float = 120.0,
        half_open_max_calls: int = 1,
        enabled: bool = True,
    ) -> None:
        if failure_threshold < 1 or recovery_timeout_s <= 0 or half_open_max_calls < 1:
            raise ValueError("invalid circuit breaker settings")
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.half_open_max_calls = half_open_max_calls
        self.enabled = enabled
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.opened_at: float | None = None
        self.half_open_in_flight = 0
        self.opens = self.rejects = self.recoveries = self.successes = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if not self.enabled:
            return
        async with self._lock:
            now = time.monotonic()
            if self.state is CircuitState.OPEN:
                assert self.opened_at is not None
                if now - self.opened_at < self.recovery_timeout_s:
                    self.rejects += 1
                    remaining = self.recovery_timeout_s - (now - self.opened_at)
                    raise CircuitOpenError(f"source circuit open; retry in {remaining:.1f}s")
                self.state = CircuitState.HALF_OPEN
                self.half_open_in_flight = 0
            if self.state is CircuitState.HALF_OPEN:
                if self.half_open_in_flight >= self.half_open_max_calls:
                    self.rejects += 1
                    raise CircuitOpenError("source circuit half-open probe already in flight")
                self.half_open_in_flight += 1

    async def success(self) -> None:
        if not self.enabled:
            return
        async with self._lock:
            self.successes += 1
            if self.state is CircuitState.HALF_OPEN:
                self.half_open_in_flight = max(0, self.half_open_in_flight - 1)
                self.recoveries += 1
            self.state = CircuitState.CLOSED
            self.failures = 0
            self.opened_at = None

    async def failure(self) -> None:
        if not self.enabled:
            return
        async with self._lock:
            if self.state is CircuitState.HALF_OPEN:
                self.half_open_in_flight = max(0, self.half_open_in_flight - 1)
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()
                self.opens += 1
                return
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()
                self.opens += 1

    async def cancel(self) -> None:
        """Release a half-open probe permit when caller cancellation is not a source failure."""
        if not self.enabled:
            return
        async with self._lock:
            if self.state is CircuitState.HALF_OPEN:
                self.half_open_in_flight = max(0, self.half_open_in_flight - 1)

    def metrics(self) -> dict[str, Any]:
        cooldown_remaining = 0.0
        if self.state is CircuitState.OPEN and self.opened_at is not None:
            cooldown_remaining = max(0.0, self.recovery_timeout_s - (time.monotonic() - self.opened_at))
        return {
            "enabled": self.enabled,
            "state": self.state.value,
            "consecutive_failures": self.failures,
            "opens": self.opens,
            "rejects": self.rejects,
            "recoveries": self.recoveries,
            "successes": self.successes,
            "cooldown_remaining_s": round(cooldown_remaining, 3),
        }


def peak_rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024.0 * 1024.0) if value > 16 * 1024 * 1024 else value / 1024.0


@dataclass(slots=True)
class AdaptiveBatchSizer:
    """AIMD-like batch controller using wall latency and process RSS pressure."""

    minimum: int = 64
    maximum: int = 2048
    initial: int = 256
    target_latency_ms: float = 250.0
    rss_soft_limit_mb: float = 1024.0
    success_window: int = 4
    enabled: bool = True
    current: int = field(init=False)
    _healthy: int = field(init=False, default=0)
    _increases: int = field(init=False, default=0)
    _decreases: int = field(init=False, default=0)
    _ewma_ms: float | None = field(init=False, default=None)
    _last_rss_mb: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        if self.minimum < 1 or self.maximum < self.minimum:
            raise ValueError("invalid adaptive batch bounds")
        if not self.minimum <= self.initial <= self.maximum:
            raise ValueError("initial batch size outside bounds")
        if self.target_latency_ms <= 0 or self.rss_soft_limit_mb <= 0 or self.success_window < 1:
            raise ValueError("invalid adaptive batch targets")
        self.current = self.initial

    def observe(self, *, latency_ms: float, rss_mb: float | None = None) -> int:
        if not self.enabled:
            return self.current
        rss = peak_rss_mb() if rss_mb is None else max(0.0, rss_mb)
        self._last_rss_mb = rss
        alpha = 0.25
        self._ewma_ms = latency_ms if self._ewma_ms is None else alpha * latency_ms + (1 - alpha) * self._ewma_ms
        pressured = rss >= self.rss_soft_limit_mb or latency_ms > self.target_latency_ms * 1.5
        if pressured:
            new_value = max(self.minimum, self.current // 2)
            if new_value < self.current:
                self.current = new_value
                self._decreases += 1
            self._healthy = 0
            return self.current
        healthy = latency_ms <= self.target_latency_ms and rss <= self.rss_soft_limit_mb * 0.8
        self._healthy = self._healthy + 1 if healthy else 0
        if self._healthy >= self.success_window and self.current < self.maximum:
            grown = max(self.current + 1, int(math.ceil(self.current * 1.25)))
            self.current = min(self.maximum, grown)
            self._healthy = 0
            self._increases += 1
        return self.current

    def metrics(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "current": self.current,
            "target_latency_ms": self.target_latency_ms,
            "rss_soft_limit_mb": self.rss_soft_limit_mb,
            "ewma_latency_ms": None if self._ewma_ms is None else round(self._ewma_ms, 3),
            "last_rss_mb": round(self._last_rss_mb, 3),
            "increases": self._increases,
            "decreases": self._decreases,
        }
