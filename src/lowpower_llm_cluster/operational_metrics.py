from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Sequence

from .scoring_inputs import TaskRequirements, measurement_confidence, metric_value, model_weight_gb, number


def _score(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return 100.0 if value else 0.0
    try:
        number_value = float(value)
    except (TypeError, ValueError):
        return default
    if not isfinite(number_value):
        return default
    return max(0.0, min(100.0, number_value))


def _weighted(values: Mapping[str, Any], weights: Mapping[str, float]) -> float | None:
    known = [(value, weights[key]) for key in weights if (value := _score(values.get(key))) is not None]
    return round(sum(value * weight for value, weight in known) / sum(weight for _, weight in known), 2) if known else None


def software_support_score(device: Mapping[str, Any]) -> float | None:
    support = device.get("software", {})
    if not isinstance(support, Mapping):
        return None
    groups = {"major_runtime_support": ("pytorch", "onnxruntime", "tensorflow", "jax"), "llm_runtime_support": ("llama_cpp", "mlx", "vllm", "tensorrt_llm", "openvino"), "quantization_support": ("int8", "int4", "gguf", "awq", "gptq"), "os_support": ("linux", "windows", "macos"), "driver_maturity": ("driver_maturity",), "multi_device_support": ("tensor_parallel", "multi_gpu", "distributed"), "deployment_support": ("docker", "container", "server_api")}
    weights = {"major_runtime_support": .25, "llm_runtime_support": .20, "quantization_support": .15, "os_support": .15, "driver_maturity": .10, "multi_device_support": .10, "deployment_support": .05}
    scores: dict[str, float] = {}
    for group, keys in groups.items():
        values = [_score(support.get(key)) for key in keys if key in support]
        values = [value for value in values if value is not None]
        if values:
            scores[group] = sum(values) / len(values)
    return _weighted(scores, weights)


def deployability_score(device: Mapping[str, Any]) -> float | None:
    deployment = device.get("deployability", {})
    if not isinstance(deployment, Mapping):
        return None
    return _weighted(deployment, {"installation": .15, "driver_setup": .15, "firmware_setup": .08, "power_integration": .12, "cooling_integration": .10, "host_compatibility": .15, "runtime_setup": .15, "model_conversion": .10})


def _nonnegative(value: Any, *, integer: bool = False) -> float | int | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(result) or result < 0:
        return None
    if integer:
        return int(result) if result.is_integer() else None
    return result


def reliability_score(device: Mapping[str, Any]) -> float | None:
    soak = device.get("soak", {})
    required = ("hours", "crashes", "resets", "inference_errors", "thermal_throttle_events", "throughput_cv")
    if not isinstance(soak, Mapping) or any(key not in soak for key in required):
        return None
    hours = _nonnegative(soak["hours"])
    crashes = _nonnegative(soak["crashes"], integer=True)
    resets = _nonnegative(soak["resets"], integer=True)
    errors = _nonnegative(soak["inference_errors"], integer=True)
    throttles = _nonnegative(soak["thermal_throttle_events"], integer=True)
    cv = _nonnegative(soak["throughput_cv"])
    if any(value is None for value in (hours, crashes, resets, errors, throttles, cv)):
        return None
    duration = min(1.0, float(hours) / 24.0) * 20.0
    stability = max(0.0, 40.0 - 12.0 * int(crashes) - 8.0 * int(resets) - 4.0 * int(errors))
    consistency = max(0.0, 15.0 * (1.0 - min(float(cv), 1.0)))
    thermal = 10.0 if int(throttles) == 0 else max(0.0, 10.0 - 2.0 * int(throttles))
    extras = 5.0 * sum(bool(soak.get(key)) for key in ("automatic_recovery", "watchdog", "ecc"))
    return round(min(100.0, duration + stability + consistency + thermal + extras), 2)


def sustained_ratio(device: Mapping[str, Any]) -> float | None:
    peak, sustained = device.get("burst_decode_tokens_s"), device.get("sustained_decode_tokens_s")
    if not isinstance(peak, (int, float)) or not isinstance(sustained, (int, float)) or peak <= 0:
        return None
    return max(0.0, min(1.0, float(sustained) / float(peak)))


def thermal_headroom_c(device: Mapping[str, Any]) -> float | None:
    throttle, sustained = device.get("thermal_throttle_c"), device.get("sustained_temp_c")
    if not isinstance(throttle, (int, float)) or not isinstance(sustained, (int, float)):
        return None
    return float(throttle) - float(sustained)


def energy_proportionality(device: Mapping[str, Any]) -> float | None:
    idle, loaded = device.get("idle_w"), device.get("system_power_w")
    if not isinstance(idle, (int, float)) or not isinstance(loaded, (int, float)) or loaded <= 0:
        return None
    return max(0.0, min(1.0, 1.0 - float(idle) / float(loaded)))


def operational_dimensions(device: Mapping[str, Any]) -> dict[str, float | None]:
    return {"software_support": software_support_score(device), "deployability": deployability_score(device), "reliability": reliability_score(device), "sustained_ratio": sustained_ratio(device), "thermal_headroom_c": thermal_headroom_c(device), "energy_proportionality": energy_proportionality(device)}


def compatibility_gates(device: Mapping[str, Any], req: TaskRequirements) -> list[str]:
    failures: list[str] = []
    if req.model_params_b is not None:
        memory = metric_value(device, "usable_ai_memory_gb")
        needed = model_weight_gb(req.model_params_b, req.bits_per_weight)
        if memory is not None and memory < needed:
            failures.append(f"model needs ~{needed:.1f}GB but usable AI memory is {memory:.1f}GB")
    if req.context_tokens is not None:
        capacity = metric_value(device, "context_capacity_tokens")
        if capacity is not None and capacity < req.context_tokens:
            failures.append(f"context {req.context_tokens} exceeds verified capacity {int(capacity)}")
    for key, floor, label in (("decode_tokens_s", req.min_decode_tokens_s, "decode"), ("prefill_tokens_s", req.min_prefill_tokens_s, "prefill")):
        value = metric_value(device, key)
        if floor is not None and value is not None and value < floor:
            failures.append(f"{label} {value:.2f} tok/s below {floor:.2f}")
    power, price = metric_value(device, "system_power_w"), metric_value(device, "price_usd")
    if req.max_system_power_w is not None and power is not None and power > req.max_system_power_w:
        failures.append(f"system power {power:.1f}W exceeds {req.max_system_power_w:.1f}W")
    if req.budget_usd is not None and price is not None and price > req.budget_usd:
        failures.append(f"price ${price:.0f} exceeds ${req.budget_usd:.0f}")
    runtimes = {str(value).lower() for value in device.get("runtimes", [])}
    precisions = {str(value).lower() for value in device.get("precisions", [])}
    if req.required_runtime and runtimes and req.required_runtime.lower() not in runtimes:
        failures.append(f"runtime {req.required_runtime} unsupported")
    if req.required_precision and precisions and req.required_precision.lower() not in precisions:
        failures.append(f"precision {req.required_precision} unsupported")
    if device.get("workloads") and req.workload not in set(device["workloads"]):
        failures.append(f"workload {req.workload} unsupported")
    return failures


def derive_metrics(device: Mapping[str, Any], req: TaskRequirements | None = None) -> dict[str, float]:
    result: dict[str, float] = {}
    decode, prefill = metric_value(device, "decode_tokens_s"), metric_value(device, "prefill_tokens_s")
    decode_power = metric_value(device, "system_power_w")
    prefill_power = metric_value(device, "prefill_power_w") or decode_power
    idle, price = metric_value(device, "idle_w"), metric_value(device, "price_usd")
    if decode is not None and decode_power and decode_power > 0:
        result["tokens_per_joule"] = decode / decode_power
        if decode > 0:
            result["joules_per_token"] = decode_power / decode
            result["tokens_per_kwh"] = 3_600_000.0 / result["joules_per_token"]
    if prefill is not None and prefill_power and prefill_power > 0:
        result["prefill_tokens_per_joule"] = prefill / prefill_power
    if decode is not None and price and price > 0:
        result["decode_tokens_s_per_dollar"] = decode / price
    if idle is not None and decode_power and decode_power > 0:
        result["idle_ratio"] = idle / decode_power
        result["daily_idle_wh"] = idle * 24.0
    if req:
        output_seconds = req.expected_output_tokens / decode if req.expected_output_tokens and decode and decode > 0 else 0.0
        prompt_seconds = req.expected_prompt_tokens / prefill if req.expected_prompt_tokens and prefill and prefill > 0 else 0.0
        seconds = output_seconds + prompt_seconds
        if seconds > 0:
            result["task_seconds"] = seconds
            joules = (output_seconds * decode_power if output_seconds and decode_power is not None else 0.0) + (prompt_seconds * prefill_power if prompt_seconds and prefill_power is not None else 0.0)
            if joules > 0:
                result["joules_per_task"] = joules
                result["wh_per_task"] = joules / 3600.0
                if req.max_energy_wh and req.max_energy_wh > 0:
                    result["energy_budget_ratio"] = result["wh_per_task"] / req.max_energy_wh
                if req.available_solar_w and req.available_solar_w > 0:
                    result["solar_recovery_hours"] = result["wh_per_task"] / req.available_solar_w
            if req.usable_battery_wh and decode_power and decode_power > 0:
                result["battery_runtime_hours"] = req.usable_battery_wh / decode_power
                if decode and decode > 0:
                    result["decode_tokens_per_battery"] = req.usable_battery_wh * 3600.0 * decode / decode_power
    return result


def enrich_device(device: Mapping[str, Any], req: TaskRequirements | None = None) -> dict[str, Any]:
    result = dict(device)
    derived = dict(device.get("derived", {})) if isinstance(device.get("derived"), Mapping) else {}
    confidence = dict(device.get("confidence", {})) if isinstance(device.get("confidence"), Mapping) else {}
    additions = derive_metrics(device, req)
    derived.update(additions)
    dependencies = {"tokens_per_joule": ("decode_tokens_s", "system_power_w"), "joules_per_token": ("decode_tokens_s", "system_power_w"), "tokens_per_kwh": ("decode_tokens_s", "system_power_w"), "prefill_tokens_per_joule": ("prefill_tokens_s", "prefill_power_w"), "decode_tokens_s_per_dollar": ("decode_tokens_s", "price_usd"), "idle_ratio": ("idle_w", "system_power_w"), "daily_idle_wh": ("idle_w",)}
    for key in additions:
        if key in dependencies:
            values = [measurement_confidence(device, dep) for dep in dependencies[key]]
            confidence[key] = min(values) if values and all(value > 0 for value in values) else 0.0
    price, memory, bandwidth = metric_value(device, "price_usd"), metric_value(device, "usable_ai_memory_gb"), metric_value(device, "memory_bandwidth_gbs")
    if price and price > 0:
        if memory is not None:
            derived["usable_ai_memory_gb_per_dollar"] = memory / price
            confidence["usable_ai_memory_gb_per_dollar"] = min(measurement_confidence(device, "usable_ai_memory_gb"), measurement_confidence(device, "price_usd"))
        if bandwidth is not None:
            derived["memory_bandwidth_gbs_per_dollar"] = bandwidth / price
            confidence["memory_bandwidth_gbs_per_dollar"] = min(measurement_confidence(device, "memory_bandwidth_gbs"), measurement_confidence(device, "price_usd"))
    result["derived"], result["confidence"] = derived, confidence
    return result


def pareto_frontier(rows: Sequence[Mapping[str, Any]], *, time_key: str = "task_seconds", energy_key: str = "wh_per_task") -> list[Mapping[str, Any]]:
    candidates: list[tuple[Mapping[str, Any], float, float]] = []
    for row in rows:
        if row.get("eligible") is False:
            continue
        derived = row.get("derived", {})
        time = number(derived.get(time_key)) if isinstance(derived, Mapping) else None
        energy = number(derived.get(energy_key)) if isinstance(derived, Mapping) else None
        if time is not None and energy is not None:
            candidates.append((row, time, energy))
    return [row for row, time, energy in candidates if not any((other_time <= time and other_energy <= energy) and (other_time < time or other_energy < energy) for other, other_time, other_energy in candidates if other is not row)]


def cluster_metrics(nodes: Sequence[Mapping[str, Any]], *, measured_combined_decode_tokens_s: float | None = None) -> dict[str, float]:
    result: dict[str, float] = {}
    ideal = sum(metric_value(node, "decode_tokens_s") or 0.0 for node in nodes)
    memory = sum(metric_value(node, "usable_ai_memory_gb") or 0.0 for node in nodes)
    idle = sum(metric_value(node, "idle_w") or 0.0 for node in nodes)
    load = sum(metric_value(node, "system_power_w") or 0.0 for node in nodes)
    if ideal > 0: result["ideal_decode_tokens_s"] = ideal
    if memory > 0: result["aggregate_usable_ai_memory_gb"] = memory
    if idle > 0: result["combined_idle_w"] = idle
    if load > 0: result["combined_load_w"] = load
    if measured_combined_decode_tokens_s is not None and ideal > 0:
        result["measured_combined_decode_tokens_s"] = float(measured_combined_decode_tokens_s)
        result["scaling_efficiency"] = float(measured_combined_decode_tokens_s) / ideal
    return result
