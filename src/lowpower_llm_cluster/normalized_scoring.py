# src/lowpower_llm_cluster/normalized_scoring.py
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from statistics import median
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class MetricSpec:
    """Definition for one normalized metric."""

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


WORKLOAD_PROFILES: dict[str, ScoreProfile] = {
    "interactive_chat": ScoreProfile(
        "interactive_chat",
        (
            MetricSpec("decode_tokens_s", 0.35),
            MetricSpec("prefill_tokens_s", 0.15),
            MetricSpec("time_to_first_token_ms", 0.10, False),
            MetricSpec("model_capacity_b_q4", 0.10),
            MetricSpec("tokens_per_joule", 0.10),
            MetricSpec("software_support", 0.10),
            MetricSpec("reliability", 0.10),
        ),
        {"decode_tokens_s": 5.0},
    ),
    "coding_agent": ScoreProfile(
        "coding_agent",
        (
            MetricSpec("decode_tokens_s", 0.25),
            MetricSpec("prefill_tokens_s", 0.20),
            MetricSpec("model_capacity_b_q4", 0.15),
            MetricSpec("context_capacity_tokens", 0.10),
            MetricSpec("tokens_per_joule", 0.10),
            MetricSpec("software_support", 0.10),
            MetricSpec("reliability", 0.10),
        ),
        {"decode_tokens_s": 7.0},
    ),
    "long_context": ScoreProfile(
        "long_context",
        (
            MetricSpec("usable_ai_memory_gb", 0.30),
            MetricSpec("prefill_tokens_s", 0.25),
            MetricSpec("memory_bandwidth_gbs", 0.15),
            MetricSpec("context_capacity_tokens", 0.10),
            MetricSpec("tokens_per_joule", 0.10),
            MetricSpec("decode_tokens_s", 0.10),
        ),
    ),
    "always_on_agent": ScoreProfile(
        "always_on_agent",
        (
            MetricSpec("idle_w", 0.25, False),
            MetricSpec("joules_per_task", 0.20, False),
            MetricSpec("reliability", 0.15),
            MetricSpec("model_capacity_b_q4", 0.10),
            MetricSpec("time_to_first_token_ms", 0.10, False),
            MetricSpec("software_support", 0.10),
            MetricSpec("sustained_ratio", 0.10),
        ),
    ),
    "off_grid_ai": ScoreProfile(
        "off_grid_ai",
        (
            MetricSpec("tokens_per_joule", 0.25),
            MetricSpec("idle_w", 0.15, False),
            MetricSpec("system_power_w", 0.15, False),
            MetricSpec("model_capacity_b_q4", 0.10),
            MetricSpec("decode_tokens_s", 0.10),
            MetricSpec("dc_powerability", 0.10),
            MetricSpec("sleep_wake", 0.05),
            MetricSpec("reliability", 0.05),
            MetricSpec("cooling_overhead_w", 0.05, False),
        ),
        {"decode_tokens_s": 3.0},
    ),
    "vision": ScoreProfile(
        "vision",
        (
            MetricSpec("vision_units_s", 0.45),
            MetricSpec("vision_units_per_joule", 0.25),
            MetricSpec("system_power_w", 0.10, False),
            MetricSpec("software_support", 0.10),
            MetricSpec("reliability", 0.10),
        ),
    ),
}

OVERALL_WEIGHTS: Mapping[str, float] = {
    "llm_speed": 0.25,
    "model_capacity": 0.20,
    "ai_compute": 0.10,
    "power_efficiency": 0.15,
    "cost_efficiency": 0.15,
    "off_grid": 0.15,
}

OFF_GRID_OVERALL_WEIGHTS: Mapping[str, float] = {
    "llm_speed": 0.20,
    "model_capacity": 0.20,
    "ai_compute": 0.05,
    "power_efficiency": 0.25,
    "cost_efficiency": 0.10,
    "off_grid": 0.20,
}

CONFIDENCE_BY_SOURCE: Mapping[str, float] = {
    "measured_local": 1.00,
    "measured": 1.00,
    "community_measured": 0.90,
    "reported": 0.90,
    "vendor_measured": 0.82,
    "manufacturer": 0.75,
    "theoretical": 0.65,
    "derived_estimate": 0.60,
    "spec_based_estimate": 0.45,
    "estimated": 0.45,
    "unknown": 0.0,
}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def metric_value(device: Mapping[str, Any], key: str) -> float | None:
    """Read a flat metric or a nested metrics/derived value."""
    for source in (device, device.get("metrics", {}), device.get("derived", {})):
        if isinstance(source, Mapping) and key in source:
            raw = source[key]
            if isinstance(raw, Mapping):
                raw = raw.get("value", raw.get("median"))
            value = _number(raw)
            if value is not None:
                return value
    return None


def measurement_confidence(device: Mapping[str, Any], key: str) -> float:
    """Return confidence in [0, 1] without promoting unknown evidence."""
    explicit = device.get("confidence", {})
    if isinstance(explicit, Mapping):
        raw = explicit.get(key)
        if isinstance(raw, Mapping):
            raw = raw.get("value", raw.get("confidence"))
        value = _number(raw)
        if value is not None:
            return max(0.0, min(1.0, value))

    for source in (device.get("metrics", {}), device.get("derived", {})):
        if isinstance(source, Mapping) and isinstance(source.get(key), Mapping):
            item = source[key]
            raw = _number(item.get("confidence"))
            if raw is not None:
                return max(0.0, min(1.0, raw))
            return CONFIDENCE_BY_SOURCE.get(str(item.get("source_type", "unknown")), 0.0)
    if key in device:
        return 1.0
    derived = device.get("derived", {})
    if isinstance(derived, Mapping) and _number(derived.get(key)) is not None:
        return 1.0
    return 0.0


def percentile_score(value: float, population: Iterable[float], *, higher_is_better: bool = True) -> float:
    """Return a duplicate-safe midpoint percentile in [0, 100]."""
    values = sorted(float(v) for v in population if isfinite(float(v)))
    if not values:
        return 0.0
    if len(values) == 1:
        return 100.0
    below = sum(v < value for v in values)
    equal = sum(v == value for v in values)
    score = 100.0 * (below + 0.5 * max(equal, 1)) / len(values)
    score = max(0.0, min(100.0, score))
    return score if higher_is_better else 100.0 - score


def normalize_metric(device: Mapping[str, Any], population: Sequence[Mapping[str, Any]], spec: MetricSpec) -> float | None:
    value = metric_value(device, spec.key)
    if value is None:
        return None
    peers = [v for item in population if (v := metric_value(item, spec.key)) is not None]
    if not peers:
        return None
    raw = percentile_score(value, peers, higher_is_better=spec.higher_is_better)
    return raw * measurement_confidence(device, spec.key)


def profile_score(device: Mapping[str, Any], population: Sequence[Mapping[str, Any]], profile: ScoreProfile) -> dict[str, Any]:
    gate_failures: list[str] = []
    for key, minimum in profile.minimum_gates.items():
        value = metric_value(device, key)
        if value is not None and value < minimum:
            gate_failures.append(f"{key}={value:g} below {minimum:g}")

    contributions: dict[str, float] = {}
    weight_used = 0.0
    weighted = 0.0
    for spec in profile.metrics:
        score = normalize_metric(device, population, spec)
        if score is None:
            continue
        contributions[spec.key] = round(score, 2)
        weighted += score * spec.weight
        weight_used += spec.weight

    score = weighted / weight_used if weight_used else 0.0
    if gate_failures:
        score *= 0.35
    total_weight = sum(metric.weight for metric in profile.metrics)
    return {
        "profile": profile.name,
        "score": round(score, 2),
        "gate_failures": gate_failures,
        "coverage": round(weight_used / total_weight, 3) if total_weight else 0.0,
        "metrics": contributions,
    }


def model_weight_gb(params_b: float, bits_per_weight: float, *, overhead_fraction: float = 0.12, extra_gb: float = 2.0) -> float:
    """Transparent model-capacity planning estimate; this does not predict speed."""
    weights_gb = params_b * bits_per_weight / 8.0
    return weights_gb * (1.0 + overhead_fraction) + extra_gb


def compatibility_gates(device: Mapping[str, Any], req: TaskRequirements) -> list[str]:
    """Reject known incompatibilities before ranking; unknown evidence remains unknown."""
    failures: list[str] = []
    if req.model_params_b is not None:
        memory = metric_value(device, "usable_ai_memory_gb")
        needed = model_weight_gb(req.model_params_b, req.bits_per_weight)
        if memory is not None and memory < needed:
            failures.append(f"model needs ~{needed:.1f}GB but usable AI memory is {memory:.1f}GB")
    if req.context_tokens is not None:
        cap = metric_value(device, "context_capacity_tokens")
        if cap is not None and cap < req.context_tokens:
            failures.append(f"context {req.context_tokens} exceeds verified capacity {int(cap)}")
    if req.min_decode_tokens_s is not None:
        speed = metric_value(device, "decode_tokens_s")
        if speed is not None and speed < req.min_decode_tokens_s:
            failures.append(f"decode {speed:.2f} tok/s below {req.min_decode_tokens_s:.2f}")
    if req.min_prefill_tokens_s is not None:
        speed = metric_value(device, "prefill_tokens_s")
        if speed is not None and speed < req.min_prefill_tokens_s:
            failures.append(f"prefill {speed:.2f} tok/s below {req.min_prefill_tokens_s:.2f}")
    if req.max_system_power_w is not None:
        power = metric_value(device, "system_power_w")
        if power is not None and power > req.max_system_power_w:
            failures.append(f"system power {power:.1f}W exceeds {req.max_system_power_w:.1f}W")
    if req.budget_usd is not None:
        price = metric_value(device, "price_usd")
        if price is not None and price > req.budget_usd:
            failures.append(f"price ${price:.0f} exceeds ${req.budget_usd:.0f}")
    if req.required_runtime:
        runtimes = {str(item).lower() for item in device.get("runtimes", [])}
        if runtimes and req.required_runtime.lower() not in runtimes:
            failures.append(f"runtime {req.required_runtime} unsupported")
    if req.required_precision:
        precisions = {str(item).lower() for item in device.get("precisions", [])}
        if precisions and req.required_precision.lower() not in precisions:
            failures.append(f"precision {req.required_precision} unsupported")
    if device.get("workloads") and req.workload not in set(device["workloads"]):
        failures.append(f"workload {req.workload} unsupported")
    return failures


def derive_metrics(device: Mapping[str, Any], req: TaskRequirements | None = None) -> dict[str, float]:
    """Derive arithmetic metrics from supplied measurements; never invent throughput."""
    result: dict[str, float] = {}
    decode = metric_value(device, "decode_tokens_s")
    prefill = metric_value(device, "prefill_tokens_s")
    power = metric_value(device, "system_power_w")
    idle = metric_value(device, "idle_w")
    price = metric_value(device, "price_usd")

    if decode is not None and power and power > 0:
        result["tokens_per_joule"] = decode / power
        if decode > 0:
            result["joules_per_token"] = power / decode
            result["tokens_per_kwh"] = 3_600_000.0 / result["joules_per_token"]
    if prefill is not None and power and power > 0:
        result["prefill_tokens_per_joule"] = prefill / power
    if decode is not None and price and price > 0:
        result["decode_tokens_s_per_dollar"] = decode / price
    if idle is not None and power and power > 0:
        result["idle_ratio"] = idle / power
        result["daily_idle_wh"] = idle * 24.0

    if req is not None:
        seconds = 0.0
        if req.expected_output_tokens and decode and decode > 0:
            seconds += req.expected_output_tokens / decode
        if req.expected_prompt_tokens and prefill and prefill > 0:
            seconds += req.expected_prompt_tokens / prefill
        if seconds > 0:
            result["task_seconds"] = seconds
            if power is not None:
                result["joules_per_task"] = power * seconds
                result["wh_per_task"] = result["joules_per_task"] / 3600.0
                if req.max_energy_wh is not None:
                    result["energy_budget_ratio"] = result["wh_per_task"] / req.max_energy_wh
                if req.available_solar_w and req.available_solar_w > 0:
                    result["solar_recovery_hours"] = result["wh_per_task"] / req.available_solar_w
            if req.usable_battery_wh and power and power > 0:
                result["battery_runtime_hours"] = req.usable_battery_wh / power
                if decode and decode > 0:
                    result["decode_tokens_per_battery"] = req.usable_battery_wh * 3600.0 * decode / power
    return result


def _category_score(device: Mapping[str, Any], population: Sequence[Mapping[str, Any]], metrics: Sequence[MetricSpec]) -> float | None:
    weighted = 0.0
    used = 0.0
    for spec in metrics:
        score = normalize_metric(device, population, spec)
        if score is None:
            continue
        weighted += score * spec.weight
        used += spec.weight
    return round(weighted / used, 2) if used else None


def category_scores(device: Mapping[str, Any], population: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    groups = {
        "llm_speed": (MetricSpec("decode_tokens_s", 0.60), MetricSpec("prefill_tokens_s", 0.30), MetricSpec("time_to_first_token_ms", 0.10, False)),
        "model_capacity": (MetricSpec("model_capacity_b_q4", 0.45), MetricSpec("usable_ai_memory_gb", 0.25), MetricSpec("memory_bandwidth_gbs", 0.20), MetricSpec("context_capacity_tokens", 0.10)),
        "ai_compute": (MetricSpec("fp32_tflops", 0.10), MetricSpec("fp16_tflops", 0.25), MetricSpec("bf16_tflops", 0.15), MetricSpec("fp8_tflops", 0.15), MetricSpec("int8_tops", 0.20), MetricSpec("int4_tops", 0.15)),
        "power_efficiency": (MetricSpec("tokens_per_joule", 0.55), MetricSpec("system_power_w", 0.20, False), MetricSpec("idle_w", 0.15, False), MetricSpec("sustained_ratio", 0.10)),
        "cost_efficiency": (MetricSpec("decode_tokens_s_per_dollar", 0.50), MetricSpec("usable_ai_memory_gb_per_dollar", 0.20), MetricSpec("memory_bandwidth_gbs_per_dollar", 0.15), MetricSpec("tokens_per_joule", 0.15)),
        "off_grid": (MetricSpec("tokens_per_joule", 0.30), MetricSpec("system_power_w", 0.20, False), MetricSpec("idle_w", 0.15, False), MetricSpec("dc_powerability", 0.10), MetricSpec("sleep_wake", 0.10), MetricSpec("cooling_overhead_w", 0.05, False), MetricSpec("reliability", 0.10)),
    }
    return {name: _category_score(device, population, specs) for name, specs in groups.items()}


def weighted_overall(scores: Mapping[str, float | None], *, off_grid_first: bool = False) -> float | None:
    weights = OFF_GRID_OVERALL_WEIGHTS if off_grid_first else OVERALL_WEIGHTS
    total = 0.0
    used = 0.0
    for key, weight in weights.items():
        value = scores.get(key)
        if value is None:
            continue
        total += value * weight
        used += weight
    return round(total / used, 2) if used else None


def enrich_device(device: Mapping[str, Any], req: TaskRequirements | None = None) -> dict[str, Any]:
    enriched = dict(device)
    derived = dict(device.get("derived", {})) if isinstance(device.get("derived"), Mapping) else {}
    derived.update(derive_metrics(device, req))
    price = metric_value(enriched, "price_usd")
    memory = metric_value(enriched, "usable_ai_memory_gb")
    bandwidth = metric_value(enriched, "memory_bandwidth_gbs")
    if price and price > 0:
        if memory is not None:
            derived["usable_ai_memory_gb_per_dollar"] = memory / price
        if bandwidth is not None:
            derived["memory_bandwidth_gbs_per_dollar"] = bandwidth / price
    enriched["derived"] = derived
    return enriched


def rank_devices(devices: Sequence[Mapping[str, Any]], req: TaskRequirements) -> list[dict[str, Any]]:
    enriched = [enrich_device(device, req) for device in devices]
    profile = WORKLOAD_PROFILES.get(req.workload, WORKLOAD_PROFILES["interactive_chat"])
    rows: list[dict[str, Any]] = []
    for device in enriched:
        gates = compatibility_gates(device, req)
        workload_score = profile_score(device, enriched, profile)
        categories = category_scores(device, enriched)
        overall = weighted_overall(categories, off_grid_first=req.workload == "off_grid_ai")
        task_energy = metric_value(device, "wh_per_task")
        if req.max_energy_wh is not None and task_energy is not None and task_energy > req.max_energy_wh:
            gates.append(f"task energy {task_energy:.2f}Wh exceeds {req.max_energy_wh:.2f}Wh")
        effective = workload_score["score"] if not gates else workload_score["score"] * 0.2
        rows.append({
            "id": device.get("id", device.get("name", "unknown")),
            "name": device.get("name", device.get("id", "unknown")),
            "eligible": not gates,
            "score": round(effective, 2),
            "profile_score": workload_score,
            "category_scores": categories,
            "overall_score": overall,
            "gates": gates,
            "derived": device.get("derived", {}),
        })
    rows.sort(key=lambda row: (row["eligible"], row["score"], row["overall_score"] or 0.0), reverse=True)
    return rows


def pareto_frontier(rows: Sequence[Mapping[str, Any]], *, time_key: str = "task_seconds", energy_key: str = "wh_per_task") -> list[Mapping[str, Any]]:
    """Return rows not dominated on both task time and task energy."""
    candidates: list[tuple[Mapping[str, Any], float, float]] = []
    for row in rows:
        derived = row.get("derived", {})
        time = _number(derived.get(time_key)) if isinstance(derived, Mapping) else None
        energy = _number(derived.get(energy_key)) if isinstance(derived, Mapping) else None
        if time is not None and energy is not None:
            candidates.append((row, time, energy))
    frontier: list[Mapping[str, Any]] = []
    for row, time, energy in candidates:
        dominated = any(
            (other_time <= time and other_energy <= energy)
            and (other_time < time or other_energy < energy)
            for other, other_time, other_energy in candidates
            if other is not row
        )
        if not dominated:
            frontier.append(row)
    return frontier


def cluster_metrics(nodes: Sequence[Mapping[str, Any]], *, measured_combined_decode_tokens_s: float | None = None) -> dict[str, float]:
    """Aggregate cluster capacity/power and calculate measured scaling efficiency."""
    result: dict[str, float] = {}
    independent = sum(metric_value(node, "decode_tokens_s") or 0.0 for node in nodes)
    if independent > 0:
        result["ideal_decode_tokens_s"] = independent
    memory = sum(metric_value(node, "usable_ai_memory_gb") or 0.0 for node in nodes)
    if memory > 0:
        result["aggregate_usable_ai_memory_gb"] = memory
    idle = sum(metric_value(node, "idle_w") or 0.0 for node in nodes)
    load = sum(metric_value(node, "system_power_w") or 0.0 for node in nodes)
    if idle > 0:
        result["combined_idle_w"] = idle
    if load > 0:
        result["combined_system_power_w"] = load
    if measured_combined_decode_tokens_s is not None and independent > 0:
        result["measured_combined_decode_tokens_s"] = measured_combined_decode_tokens_s
        result["scaling_efficiency"] = measured_combined_decode_tokens_s / independent
    return result


def summarize_population(devices: Sequence[Mapping[str, Any]], key: str) -> dict[str, float] | None:
    values = [value for device in devices if (value := metric_value(device, key)) is not None]
    if not values:
        return None
    return {"minimum": min(values), "median": median(values), "maximum": max(values), "count": float(len(values))}
