# src/lowpower_llm_cluster/optimizer.py
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .normalized_scoring import TaskRequirements, metric_value, rank_devices
from .operational_metrics import operational_dimensions


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
        profile = row["profile_score"]
        practical_values = [value for value in (categories.get("llm_speed"), categories.get("power_efficiency")) if isinstance(value, (int, float))]
        if float(profile.get("coverage", 0.0) or 0.0) > 0 and isinstance(profile.get("score"), (int, float)):
            practical_values.append(float(profile["score"]))
        row["practical_score"] = round(sum(practical_values) / len(practical_values), 2) if practical_values else None

        reasons: list[str] = []
        for label, value in (("LLM speed", categories.get("llm_speed")), ("model capacity", categories.get("model_capacity")), ("power efficiency", categories.get("power_efficiency")), ("cost efficiency", categories.get("cost_efficiency")), ("off-grid fit", categories.get("off_grid")), ("software support", operational.get("software_support")), ("deployability", operational.get("deployability")), ("reliability", operational.get("reliability"))):
            text = _reason(label, value)
            if text:
                reasons.append(text)
        if metric_value(source, "decode_tokens_s") is None and req.workload != "vision":
            reasons.append("no measured or sourced decode throughput; speed score coverage is limited")
        if row["gates"]:
            reasons.extend(f"ineligible: {failure}" for failure in row["gates"])
        row["reasons"] = reasons
    return rows
