from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence

@dataclass(frozen=True)
class MetricSpec:
    key: str
    weight: float
    higher_is_better: bool = True
    minimum: float | None = None

@dataclass(frozen=True)
class ScoreProfile:
    name: str
    metrics: tuple[MetricSpec, ...]
    minimum_gates: Mapping[str, float] = field(default_factory=dict)

@dataclass(frozen=True)
class TaskRequirements:
    workload: str = "interactive_chat"
    model_params_b: float | None = None
    bits_per_weight: float = 4.0
    context_tokens: int | None = None
    min_decode_tokens_s: float | None = None
    min_prefill_tokens_s: float | None = None
    max_system_power_w: float | None = None
    max_energy_wh: float | None = None
    budget_usd: float | None = None
    required_runtime: str | None = None
    required_precision: str | None = None
    expected_output_tokens: int | None = None
    expected_prompt_tokens: int | None = None
    usable_battery_wh: float | None = None
    available_solar_w: float | None = None

WORKLOAD_PROFILES = {
    "interactive_chat": ScoreProfile("interactive_chat", (MetricSpec("decode_tokens_s", .35), MetricSpec("prefill_tokens_s", .15), MetricSpec("time_to_first_token_ms", .10, False), MetricSpec("model_capacity_b_q4", .10), MetricSpec("tokens_per_joule", .10), MetricSpec("software_support", .10), MetricSpec("reliability", .10)), {"decode_tokens_s": 5.0}),
    "coding_agent": ScoreProfile("coding_agent", (MetricSpec("decode_tokens_s", .25), MetricSpec("prefill_tokens_s", .20), MetricSpec("model_capacity_b_q4", .15), MetricSpec("context_capacity_tokens", .10), MetricSpec("tokens_per_joule", .10), MetricSpec("software_support", .10), MetricSpec("reliability", .10)), {"decode_tokens_s": 7.0}),
    "long_context": ScoreProfile("long_context", (MetricSpec("usable_ai_memory_gb", .30), MetricSpec("prefill_tokens_s", .25), MetricSpec("memory_bandwidth_gbs", .15), MetricSpec("context_capacity_tokens", .10), MetricSpec("tokens_per_joule", .10), MetricSpec("decode_tokens_s", .10))),
    "always_on_agent": ScoreProfile("always_on_agent", (MetricSpec("idle_w", .25, False), MetricSpec("joules_per_task", .20, False), MetricSpec("reliability", .15), MetricSpec("model_capacity_b_q4", .10), MetricSpec("time_to_first_token_ms", .10, False), MetricSpec("software_support", .10), MetricSpec("sustained_ratio", .10))),
    "off_grid_ai": ScoreProfile("off_grid_ai", (MetricSpec("tokens_per_joule", .25), MetricSpec("idle_w", .15, False), MetricSpec("system_power_w", .15, False), MetricSpec("model_capacity_b_q4", .10), MetricSpec("decode_tokens_s", .10), MetricSpec("dc_powerability", .10), MetricSpec("sleep_wake", .05), MetricSpec("reliability", .05), MetricSpec("cooling_overhead_w", .05, False)), {"decode_tokens_s": 3.0}),
    "vision": ScoreProfile("vision", (MetricSpec("vision_units_s", .45), MetricSpec("vision_units_per_joule", .25), MetricSpec("system_power_w", .10, False), MetricSpec("software_support", .10), MetricSpec("reliability", .10))),
}
SOURCE_CONFIDENCE = {"measured_local": 1.0, "measured": 1.0, "community_measured": .90, "reported": .90, "vendor_measured": .82, "manufacturer": .75, "theoretical": .65, "derived_estimate": .60, "spec_based_estimate": .45, "estimated": .45}


def number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if isfinite(value) else None


def metric_value(device: Mapping[str, Any], key: str) -> float | None:
    for bucket in (device, device.get("metrics", {}), device.get("derived", {})):
        if isinstance(bucket, Mapping) and key in bucket:
            raw = bucket[key]
            if isinstance(raw, Mapping):
                raw = raw.get("value", raw.get("median"))
            value = number(raw)
            if value is not None:
                return value
    return None


def measurement_confidence(device: Mapping[str, Any], key: str) -> float:
    explicit = device.get("confidence", {})
    if isinstance(explicit, Mapping) and key in explicit:
        raw = explicit[key]
        if isinstance(raw, Mapping):
            raw = raw.get("confidence", raw.get("value"))
        value = number(raw)
        if value is not None:
            return max(0.0, min(1.0, value))
    for bucket in (device.get("metrics", {}), device.get("derived", {})):
        item = bucket.get(key) if isinstance(bucket, Mapping) else None
        if isinstance(item, Mapping):
            source_cap = SOURCE_CONFIDENCE.get(str(item.get("source_type", "")), 0.0)
            explicit_value = number(item.get("confidence"))
            return source_cap if explicit_value is None else min(source_cap, max(0.0, min(1.0, explicit_value)))
    return 0.0


def percentile_score(value: float, population: Iterable[float], *, higher_is_better: bool = True) -> float:
    values = sorted(float(v) for v in population if isfinite(float(v)))
    if not values:
        return 0.0
    if len(values) == 1:
        return 100.0
    score = 100.0 * (sum(v < value for v in values) + .5 * max(sum(v == value for v in values), 1)) / len(values)
    score = max(0.0, min(100.0, score))
    return score if higher_is_better else 100.0 - score


def normalize_metric(device: Mapping[str, Any], population: Sequence[Mapping[str, Any]], spec: MetricSpec) -> float | None:
    value = metric_value(device, spec.key)
    confidence = measurement_confidence(device, spec.key)
    if value is None or confidence <= 0:
        return None
    peers = [metric_value(row, spec.key) for row in population if measurement_confidence(row, spec.key) > 0]
    peers = [value for value in peers if value is not None]
    return percentile_score(value, peers, higher_is_better=spec.higher_is_better) * confidence if peers else None


def profile_score(device: Mapping[str, Any], population: Sequence[Mapping[str, Any]], profile: ScoreProfile) -> dict[str, Any]:
    failures = []
    for key, minimum in profile.minimum_gates.items():
        value = metric_value(device, key)
        if value is not None and value < minimum:
            failures.append(f"{key}={value:g} below {minimum:g}")
    weighted = used = 0.0
    contributions: dict[str, float] = {}
    for spec in profile.metrics:
        score = normalize_metric(device, population, spec)
        if score is None:
            continue
        contributions[spec.key] = round(score, 2)
        weighted += score * spec.weight
        used += spec.weight
    total = sum(spec.weight for spec in profile.metrics)
    return {"profile": profile.name, "score": round(weighted / used, 2) if used else 0.0, "gate_failures": failures, "coverage": round(used / total, 3) if total else 0.0, "metrics": contributions}


def model_weight_gb(params_b: float, bits_per_weight: float, *, overhead_fraction: float = .12, extra_gb: float = 2.0) -> float:
    return params_b * bits_per_weight / 8.0 * (1 + overhead_fraction) + extra_gb


def _median_metric(result: Mapping[str, Any], key: str) -> float | None:
    metrics = result.get("metrics", {})
    item = metrics.get(key) if isinstance(metrics, Mapping) else None
    value = item.get("median") if isinstance(item, Mapping) else None
    return float(value) if isinstance(value, (int, float)) else None


def _phase_power(result: Mapping[str, Any], phase: str) -> float | None:
    power = result.get("power", {})
    if not isinstance(power, Mapping):
        return None
    for item in power.values():
        if isinstance(item, Mapping) and item.get("phase") == phase and item.get("scope") == "complete_node_input":
            value = item.get("mean_w", item.get("median_w"))
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _condition_id(result: Mapping[str, Any]) -> str:
    condition = {"model": result.get("model", {}), "runtime": result.get("runtime", {}), "workload": result.get("workload", {}), "workload_class": result.get("workload_class")}
    return hashlib.sha256(json.dumps(condition, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()[:16]


def benchmark_result_to_device(result: Mapping[str, Any]) -> dict[str, Any]:
    hardware_id = str(result.get("hardware_id", "unknown"))
    configuration_id = str(result.get("configuration_id", "default"))
    device: dict[str, Any] = {"id": f"{hardware_id}:{configuration_id}:{_condition_id(result)}", "name": hardware_id, "workloads": [], "metrics": {}, "confidence": {}}
    workload_class = str(result.get("workload_class", "other"))
    if workload_class == "llm":
        device["workloads"] = ["interactive_chat", "coding_agent", "long_context", "always_on_agent", "off_grid_ai"]
        for source_key, target_key in (("generation_tokens_per_second", "decode_tokens_s"), ("prompt_tokens_per_second", "prefill_tokens_s")):
            value = _median_metric(result, source_key)
            if value is not None:
                device["metrics"][target_key] = {"value": value, "source_type": "measured_local", "confidence": 1.0}
        for phase, target_key in (("decode", "system_power_w"), ("prefill", "prefill_power_w")):
            value = _phase_power(result, phase)
            if value is not None:
                device["metrics"][target_key] = {"value": value, "source_type": "measured_local", "confidence": 1.0}
    elif workload_class == "vision":
        device["workloads"] = ["vision"]
        primary = None
        for key in ("frames_per_second", "images_per_second", "inferences_per_second"):
            primary = _median_metric(result, key)
            if primary is not None:
                break
        if primary is not None:
            device["metrics"]["vision_units_s"] = {"value": primary, "source_type": "measured_local", "confidence": 1.0}
        active_w = _phase_power(result, "active")
        if active_w is not None:
            device["metrics"]["system_power_w"] = {"value": active_w, "source_type": "measured_local", "confidence": 1.0}
            if primary is not None and active_w > 0:
                device["metrics"]["vision_units_per_joule"] = {"value": primary / active_w, "source_type": "derived_estimate", "confidence": .60}
    cost = result.get("cost", {})
    if isinstance(cost, Mapping):
        for key in ("complete_system_purchase_usd", "system_cost_usd", "purchase_usd"):
            value = cost.get(key)
            if isinstance(value, (int, float)):
                device["price_usd"] = float(value)
                device["confidence"]["price_usd"] = 1.0
                break
    runtime = result.get("runtime", {})
    if isinstance(runtime, Mapping) and runtime.get("runtime_name"):
        device["runtimes"] = [str(runtime["runtime_name"])]
    model = result.get("model", {})
    if isinstance(model, Mapping) and model.get("quantization"):
        device["precisions"] = [str(model["quantization"])]
    workload = result.get("workload", {})
    if isinstance(workload, Mapping) and isinstance(workload.get("context_tokens"), int):
        device["benchmarked_context_tokens"] = workload["context_tokens"]
    device["benchmark_result_id"] = result.get("result_id")
    return device


def merge_device_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(record.get("id", record.get("name", "unknown")))
        current = merged.setdefault(key, {"id": key})
        for field, value in record.items():
            if field in {"metrics", "derived", "confidence"} and isinstance(value, Mapping):
                current.setdefault(field, {}).update(value)
            elif field in {"runtimes", "precisions", "workloads"} and isinstance(value, list):
                current[field] = sorted(set(current.get(field, [])) | {str(item) for item in value})
            elif value is not None:
                current[field] = value
    return list(merged.values())
