# src/lowpower_llm_cluster/benchmarking/models.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean, median, pstdev
from typing import Any, Iterable


@dataclass(frozen=True)
class MetricSummary:
    unit: str
    samples: list[float]
    median: float
    mean: float
    stdev: float
    minimum: float
    maximum: float

    @classmethod
    def from_values(cls, values: Iterable[float], unit: str) -> "MetricSummary":
        samples = [float(value) for value in values]
        if not samples:
            raise ValueError("metric samples may not be empty")
        return cls(
            unit=unit,
            samples=samples,
            median=float(median(samples)),
            mean=float(mean(samples)),
            stdev=float(pstdev(samples)) if len(samples) > 1 else 0.0,
            minimum=float(min(samples)),
            maximum=float(max(samples)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PowerWindow:
    phase: str
    scope: str
    source: str
    duration_s: float
    samples_w: list[float]
    mean_w: float | None
    median_w: float | None
    energy_j: float | None

    @property
    def is_complete_node(self) -> bool:
        return self.scope == "complete_node_input"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
