# src/lowpower_llm_cluster/performance.py
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit

MEASURED_SOURCE_TYPES = {"measured_local", "community_measured", "vendor_measured"}
LLM_WORKLOAD_CLASSES = {"llm_prefill", "llm_decode"}
SPECIALIST_WORKLOAD_CLASSES = {"vision", "audio", "embedding", "reranking", "other_specialist"}


@dataclass(frozen=True, slots=True)
class PerformanceRecord:
    hardware_id: str
    source_type: str
    source_url: str
    source_name: str
    model: str
    runtime: str
    runtime_version: str
    workload_class: str
    metric_name: str
    value: float
    unit: str
    quantization: str = ""
    context_tokens: int | None = None
    power_w: float | None = None
    power_scope: str = "unknown"
    observed_on: str = ""

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "PerformanceRecord":
        return cls(
            hardware_id=str(raw["hardware_id"]), source_type=str(raw["source_type"]),
            source_url=str(raw["source_url"]), source_name=str(raw.get("source_name", "")),
            model=str(raw["model"]), runtime=str(raw["runtime"]), runtime_version=str(raw.get("runtime_version", "")),
            workload_class=str(raw["workload_class"]), metric_name=str(raw["metric_name"]), value=float(raw["value"]),
            unit=str(raw["unit"]), quantization=str(raw.get("quantization", "")),
            context_tokens=int(raw["context_tokens"]) if raw.get("context_tokens") is not None else None,
            power_w=float(raw["power_w"]) if raw.get("power_w") is not None else None,
            power_scope=str(raw.get("power_scope", "unknown")), observed_on=str(raw.get("observed_on", "")),
        )


def load_performance_records(path: Path | str) -> list[PerformanceRecord]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        raw_records = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        payload = json.loads(text)
        raw_records = payload.get("records", payload) if isinstance(payload, dict) else payload
    return [PerformanceRecord.from_mapping(record) for record in raw_records]


def _source_identity(record: PerformanceRecord) -> str:
    if record.source_name.strip():
        return record.source_name.strip().lower()
    return urlsplit(record.source_url).netloc.lower() or record.source_url.lower()


def confidence_aware_range(records: Sequence[PerformanceRecord], *, minimum_independent_sources: int = 2) -> dict[str, Any] | None:
    """Return a measured range only for compatible records with independent provenance."""
    if minimum_independent_sources < 2:
        raise ValueError("minimum_independent_sources must be >= 2")
    measured = [record for record in records if record.source_type in MEASURED_SOURCE_TYPES]
    if not measured:
        return None
    signature = {(r.hardware_id, r.model, r.runtime, r.workload_class, r.metric_name, r.unit, r.quantization, r.context_tokens) for r in measured}
    if len(signature) != 1:
        raise ValueError("performance ranges require one compatible hardware/model/runtime/workload/metric signature")
    sources = {_source_identity(record) for record in measured}
    if len(sources) < minimum_independent_sources:
        return None
    values = [record.value for record in measured]
    low, high = min(values), max(values)
    median = statistics.median(values)
    relative_spread = 0.0 if median == 0 else (high - low) / abs(median)
    confidence = "high" if len(sources) >= 3 and relative_spread <= 0.25 else "medium"
    first = measured[0]
    return {
        "hardware_id": first.hardware_id,
        "model": first.model,
        "runtime": first.runtime,
        "workload_class": first.workload_class,
        "metric_name": first.metric_name,
        "unit": first.unit,
        "low": round(low, 4),
        "median": round(float(median), 4),
        "high": round(high, 4),
        "sample_count": len(values),
        "independent_source_count": len(sources),
        "confidence": confidence,
        "source_urls": sorted({record.source_url for record in measured}),
    }


def separate_workload_records(records: Iterable[PerformanceRecord]) -> dict[str, list[PerformanceRecord]]:
    buckets = {"llm": [], "specialist": [], "unknown": []}
    for record in records:
        if record.workload_class in LLM_WORKLOAD_CLASSES:
            buckets["llm"].append(record)
        elif record.workload_class in SPECIALIST_WORKLOAD_CLASSES:
            buckets["specialist"].append(record)
        else:
            buckets["unknown"].append(record)
    return buckets


def import_third_party_records(path: Path | str, *, mapping: dict[str, str] | None = None) -> list[PerformanceRecord]:
    """Import simple JSON/JSONL benchmark exports through an explicit field mapping."""
    mapping = mapping or {}
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    raw = [json.loads(line) for line in text.splitlines() if line.strip()] if path.suffix.lower() == ".jsonl" else json.loads(text)
    if isinstance(raw, dict):
        raw = raw.get("records", raw.get("results", []))
    records: list[PerformanceRecord] = []
    for item in raw:
        normalized = {target: item.get(source) for target, source in mapping.items()}
        for key in ("hardware_id", "source_type", "source_url", "source_name", "model", "runtime", "runtime_version", "workload_class", "metric_name", "value", "unit", "quantization", "context_tokens", "power_w", "power_scope", "observed_on"):
            if key not in normalized and key in item:
                normalized[key] = item[key]
        records.append(PerformanceRecord.from_mapping(normalized))
    return records
