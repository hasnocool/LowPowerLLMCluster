from __future__ import annotations

from typing import Any, Mapping, Sequence

from .operational_metrics import compatibility_gates, enrich_device, operational_dimensions
from .scoring_inputs import MetricSpec, TaskRequirements, WORKLOAD_PROFILES, metric_value, normalize_metric, profile_score

OVERALL_WEIGHTS: Mapping[str, float] = {"llm_speed": .25, "model_capacity": .20, "ai_compute": .10, "power_efficiency": .15, "cost_efficiency": .15, "off_grid": .15}
OFF_GRID_OVERALL_WEIGHTS: Mapping[str, float] = {"llm_speed": .20, "model_capacity": .20, "ai_compute": .05, "power_efficiency": .25, "cost_efficiency": .10, "off_grid": .20}


def _category(device: Mapping[str, Any], population: Sequence[Mapping[str, Any]], specs: Sequence[MetricSpec]) -> float | None:
    values = [(score, spec.weight) for spec in specs if (score := normalize_metric(device, population, spec)) is not None]
    return round(sum(score * weight for score, weight in values) / sum(weight for _, weight in values), 2) if values else None


def category_scores(device: Mapping[str, Any], population: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    groups = {
        "llm_speed": (MetricSpec("decode_tokens_s", .60), MetricSpec("prefill_tokens_s", .30), MetricSpec("time_to_first_token_ms", .10, False)),
        "model_capacity": (MetricSpec("model_capacity_b_q4", .45), MetricSpec("usable_ai_memory_gb", .25), MetricSpec("memory_bandwidth_gbs", .20), MetricSpec("context_capacity_tokens", .10)),
        "ai_compute": (MetricSpec("fp32_tflops", .10), MetricSpec("fp16_tflops", .25), MetricSpec("bf16_tflops", .15), MetricSpec("fp8_tflops", .15), MetricSpec("int8_tops", .20), MetricSpec("int4_tops", .15)),
        "power_efficiency": (MetricSpec("tokens_per_joule", .55), MetricSpec("system_power_w", .20, False), MetricSpec("idle_w", .15, False), MetricSpec("sustained_ratio", .10)),
        "cost_efficiency": (MetricSpec("decode_tokens_s_per_dollar", .50), MetricSpec("usable_ai_memory_gb_per_dollar", .20), MetricSpec("memory_bandwidth_gbs_per_dollar", .15), MetricSpec("tokens_per_joule", .15)),
        "off_grid": (MetricSpec("tokens_per_joule", .30), MetricSpec("system_power_w", .20, False), MetricSpec("idle_w", .15, False), MetricSpec("dc_powerability", .10), MetricSpec("sleep_wake", .10), MetricSpec("cooling_overhead_w", .05, False), MetricSpec("reliability", .10)),
    }
    return {name: _category(device, population, specs) for name, specs in groups.items()}


def weighted_overall(scores: Mapping[str, float | None], *, off_grid_first: bool = False) -> float | None:
    weights = OFF_GRID_OVERALL_WEIGHTS if off_grid_first else OVERALL_WEIGHTS
    values = [(scores.get(key), weight) for key, weight in weights.items() if scores.get(key) is not None]
    return round(sum(float(value) * weight for value, weight in values) / sum(weight for _, weight in values), 2) if values else None


def rank_devices(devices: Sequence[Mapping[str, Any]], req: TaskRequirements) -> list[dict[str, Any]]:
    enriched = [enrich_device(device, req) for device in devices]
    profile = WORKLOAD_PROFILES.get(req.workload, WORKLOAD_PROFILES["interactive_chat"])
    rows: list[dict[str, Any]] = []
    for device in enriched:
        workload_score = profile_score(device, enriched, profile)
        gates = compatibility_gates(device, req) + list(workload_score["gate_failures"])
        categories = category_scores(device, enriched)
        overall = weighted_overall(categories, off_grid_first=req.workload == "off_grid_ai")
        task_energy = metric_value(device, "wh_per_task")
        if req.max_energy_wh is not None and task_energy is not None and task_energy > req.max_energy_wh:
            gates.append(f"task energy {task_energy:.2f}Wh exceeds {req.max_energy_wh:.2f}Wh")
        score = workload_score["score"] if not gates else workload_score["score"] * .2
        rows.append({"id": device.get("id", device.get("name", "unknown")), "name": device.get("name", device.get("id", "unknown")), "eligible": not gates, "score": round(score, 2), "profile_score": workload_score, "category_scores": categories, "overall_score": overall, "gates": gates, "derived": device.get("derived", {})})
    rows.sort(key=lambda row: (row["eligible"], row["score"], row["overall_score"] or 0.0), reverse=True)
    return rows


def _reason(label: str, value: float | None, *, high: float = 75.0, low: float = 25.0) -> str | None:
    if value is None:
        return None
    if value >= high:
        return f"strong {label} ({value:.1f}/100)"
    if value <= low:
        return f"weak {label} ({value:.1f}/100)"
    return None


def rank_devices_full(devices: Sequence[Mapping[str, Any]], req: TaskRequirements) -> list[dict[str, Any]]:
    rows = rank_devices(devices, req)
    by_id = {str(device.get("id", device.get("name", "unknown"))): device for device in devices}
    for row in rows:
        source = by_id.get(str(row["id"]), {})
        operational = operational_dimensions(source)
        row["operational"] = operational
        categories = row["category_scores"]
        row["theoretical_score"] = categories.get("ai_compute")
        practical_values = [value for value in (categories.get("llm_speed"), categories.get("power_efficiency")) if isinstance(value, (int, float))]
        profile = row["profile_score"]
        if float(profile.get("coverage", 0.0) or 0.0) > 0 and isinstance(profile.get("score"), (int, float)):
            practical_values.append(float(profile["score"]))
        row["practical_score"] = round(sum(practical_values) / len(practical_values), 2) if practical_values else None
        reasons: list[str] = []
        for label, value in (("LLM speed", categories.get("llm_speed")), ("model capacity", categories.get("model_capacity")), ("power efficiency", categories.get("power_efficiency")), ("cost efficiency", categories.get("cost_efficiency")), ("off-grid fit", categories.get("off_grid")), ("software support", operational.get("software_support")), ("deployability", operational.get("deployability")), ("reliability", operational.get("reliability"))):
            if text := _reason(label, value):
                reasons.append(text)
        if metric_value(source, "decode_tokens_s") is None and req.workload != "vision":
            reasons.append("no measured or sourced decode throughput; speed score coverage is limited")
        if row["gates"]:
            reasons.extend(f"ineligible: {failure}" for failure in row["gates"])
        row["reasons"] = reasons
    return rows
