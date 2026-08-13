# src/lowpower_llm_cluster/operational_metrics.py
from __future__ import annotations

from math import isfinite
from typing import Any, Mapping


def _score(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return 100.0 if value else 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not isfinite(number):
        return default
    return max(0.0, min(100.0, number))


def _weighted(values: Mapping[str, Any], weights: Mapping[str, float]) -> float | None:
    total = 0.0
    used = 0.0
    for key, weight in weights.items():
        value = _score(values.get(key))
        if value is None:
            continue
        total += value * weight
        used += weight
    return round(total / used, 2) if used else None


def software_support_score(device: Mapping[str, Any]) -> float | None:
    support = device.get("software", {})
    if not isinstance(support, Mapping):
        return None
    groups = {
        "major_runtime_support": ("pytorch", "onnxruntime", "tensorflow", "jax"),
        "llm_runtime_support": ("llama_cpp", "mlx", "vllm", "tensorrt_llm", "openvino"),
        "quantization_support": ("int8", "int4", "gguf", "awq", "gptq"),
        "os_support": ("linux", "windows", "macos"),
        "driver_maturity": ("driver_maturity",),
        "multi_device_support": ("tensor_parallel", "multi_gpu", "distributed"),
        "deployment_support": ("docker", "container", "server_api"),
    }
    group_weights = {"major_runtime_support": .25, "llm_runtime_support": .20, "quantization_support": .15, "os_support": .15, "driver_maturity": .10, "multi_device_support": .10, "deployment_support": .05}
    group_scores: dict[str, float] = {}
    for group, keys in groups.items():
        values = [_score(support.get(key)) for key in keys if key in support]
        known = [value for value in values if value is not None]
        if known:
            group_scores[group] = sum(known) / len(known)
    return _weighted(group_scores, group_weights)


def deployability_score(device: Mapping[str, Any]) -> float | None:
    deployment = device.get("deployability", {})
    if not isinstance(deployment, Mapping):
        return None
    return _weighted(deployment, {"installation": .15, "driver_setup": .15, "firmware_setup": .08, "power_integration": .12, "cooling_integration": .10, "host_compatibility": .15, "runtime_setup": .15, "model_conversion": .10})


def _nonnegative_number(value: Any, *, integer: bool = False) -> float | int | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number) or number < 0:
        return None
    if integer:
        if not number.is_integer():
            return None
        return int(number)
    return number


def reliability_score(device: Mapping[str, Any]) -> float | None:
    """Score only complete, valid soak observations; partial evidence remains unknown."""
    soak = device.get("soak", {})
    required = ("hours", "crashes", "resets", "inference_errors", "thermal_throttle_events", "throughput_cv")
    if not isinstance(soak, Mapping) or any(key not in soak for key in required):
        return None
    hours = _nonnegative_number(soak["hours"])
    crashes = _nonnegative_number(soak["crashes"], integer=True)
    resets = _nonnegative_number(soak["resets"], integer=True)
    inference_errors = _nonnegative_number(soak["inference_errors"], integer=True)
    throttle_events = _nonnegative_number(soak["thermal_throttle_events"], integer=True)
    cv = _nonnegative_number(soak["throughput_cv"])
    if any(value is None for value in (hours, crashes, resets, inference_errors, throttle_events, cv)):
        return None
    duration = min(1.0, float(hours) / 24.0) * 20.0
    stability = max(0.0, 40.0 - 12.0 * int(crashes) - 8.0 * int(resets) - 4.0 * int(inference_errors))
    consistency = max(0.0, 15.0 * (1.0 - min(float(cv), 1.0)))
    thermal = 10.0 if int(throttle_events) == 0 else max(0.0, 10.0 - 2.0 * int(throttle_events))
    recovery = 5.0 if bool(soak.get("automatic_recovery")) else 0.0
    watchdog = 5.0 if bool(soak.get("watchdog")) else 0.0
    ecc = 5.0 if bool(soak.get("ecc")) else 0.0
    return round(min(100.0, duration + stability + consistency + thermal + recovery + watchdog + ecc), 2)


def sustained_ratio(device: Mapping[str, Any]) -> float | None:
    peak = device.get("burst_decode_tokens_s")
    sustained = device.get("sustained_decode_tokens_s")
    if not isinstance(peak, (int, float)) or not isinstance(sustained, (int, float)) or peak <= 0:
        return None
    return max(0.0, min(1.0, float(sustained) / float(peak)))


def thermal_headroom_c(device: Mapping[str, Any]) -> float | None:
    throttle = device.get("thermal_throttle_c")
    sustained = device.get("sustained_temp_c")
    if not isinstance(throttle, (int, float)) or not isinstance(sustained, (int, float)):
        return None
    return float(throttle) - float(sustained)


def energy_proportionality(device: Mapping[str, Any]) -> float | None:
    idle = device.get("idle_w")
    loaded = device.get("system_power_w")
    if not isinstance(idle, (int, float)) or not isinstance(loaded, (int, float)) or loaded <= 0:
        return None
    return max(0.0, min(1.0, 1.0 - float(idle) / float(loaded)))


def operational_dimensions(device: Mapping[str, Any]) -> dict[str, float | None]:
    return {"software_support": software_support_score(device), "deployability": deployability_score(device), "reliability": reliability_score(device), "sustained_ratio": sustained_ratio(device), "thermal_headroom_c": thermal_headroom_c(device), "energy_proportionality": energy_proportionality(device)}
