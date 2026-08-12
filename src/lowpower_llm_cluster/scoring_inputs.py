# src/lowpower_llm_cluster/scoring_inputs.py
from __future__ import annotations

from typing import Any, Mapping, Sequence


def _median_metric(result: Mapping[str, Any], key: str) -> float | None:
    metrics = result.get("metrics", {})
    item = metrics.get(key) if isinstance(metrics, Mapping) else None
    if not isinstance(item, Mapping):
        return None
    value = item.get("median")
    return float(value) if isinstance(value, (int, float)) else None


def _phase_power(result: Mapping[str, Any], phase: str) -> float | None:
    power = result.get("power", {})
    if not isinstance(power, Mapping):
        return None
    for item in power.values():
        if not isinstance(item, Mapping):
            continue
        if item.get("phase") != phase or item.get("scope") != "complete_node_input":
            continue
        value = item.get("mean_w", item.get("median_w"))
        if isinstance(value, (int, float)):
            return float(value)
    return None


def benchmark_result_to_device(result: Mapping[str, Any]) -> dict[str, Any]:
    """Map one benchmark-schema-v2 result to normalized scoring fields.

    Only complete-node power becomes canonical system power. Board-only power is
    intentionally ignored for tokens/joule scoring, matching benchmark guardrails.
    """
    hardware_id = str(result.get("hardware_id", "unknown"))
    configuration_id = str(result.get("configuration_id", "default"))
    device: dict[str, Any] = {
        "id": f"{hardware_id}:{configuration_id}",
        "name": hardware_id,
        "workloads": [],
        "metrics": {},
        "confidence": {},
    }
    workload_class = str(result.get("workload_class", "other"))
    if workload_class == "llm":
        device["workloads"] = ["interactive_chat", "coding_agent", "long_context", "always_on_agent", "off_grid_ai"]
        decode = _median_metric(result, "generation_tokens_per_second")
        prefill = _median_metric(result, "prompt_tokens_per_second")
        if decode is not None:
            device["metrics"]["decode_tokens_s"] = {"value": decode, "source_type": "measured_local", "confidence": 1.0}
        if prefill is not None:
            device["metrics"]["prefill_tokens_s"] = {"value": prefill, "source_type": "measured_local", "confidence": 1.0}
        decode_w = _phase_power(result, "decode")
        prefill_w = _phase_power(result, "prefill")
        if decode_w is not None:
            device["metrics"]["system_power_w"] = {"value": decode_w, "source_type": "measured_local", "confidence": 1.0}
        if prefill_w is not None:
            device["metrics"]["prefill_power_w"] = {"value": prefill_w, "source_type": "measured_local", "confidence": 1.0}
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
                device["metrics"]["vision_units_per_joule"] = {"value": primary / active_w, "source_type": "derived_estimate", "confidence": 1.0}

    cost = result.get("cost", {})
    if isinstance(cost, Mapping):
        for key in ("complete_system_purchase_usd", "system_cost_usd", "purchase_usd"):
            value = cost.get(key)
            if isinstance(value, (int, float)):
                device["price_usd"] = float(value)
                break
    runtime = result.get("runtime", {})
    if isinstance(runtime, Mapping) and runtime.get("runtime_name"):
        device["runtimes"] = [str(runtime["runtime_name"])]
    model = result.get("model", {})
    if isinstance(model, Mapping) and model.get("quantization"):
        device["precisions"] = [str(model["quantization"])]
    workload = result.get("workload", {})
    if isinstance(workload, Mapping):
        context = workload.get("context_tokens")
        if isinstance(context, int):
            device["context_capacity_tokens"] = context
    device["benchmark_result_id"] = result.get("result_id")
    return device


def merge_device_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Merge records with the same id, preferring later concrete values."""
    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(record.get("id", record.get("name", "unknown")))
        current = merged.setdefault(key, {"id": key})
        for field, value in record.items():
            if field in {"metrics", "derived", "confidence"} and isinstance(value, Mapping):
                bucket = current.setdefault(field, {})
                if isinstance(bucket, dict):
                    bucket.update(value)
            elif field in {"runtimes", "precisions", "workloads"} and isinstance(value, list):
                current[field] = sorted(set(current.get(field, [])) | {str(item) for item in value})
            elif value is not None:
                current[field] = value
    return list(merged.values())
