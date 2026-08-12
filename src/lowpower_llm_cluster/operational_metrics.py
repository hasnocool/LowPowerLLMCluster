# src/lowpower_llm_cluster/operational_metrics.py
from __future__ import annotations

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
    """Score explicit runtime/OS/deployment support; absent claims remain unknown."""
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
    group_weights = {
        "major_runtime_support": 0.25,
        "llm_runtime_support": 0.20,
        "quantization_support": 0.15,
        "os_support": 0.15,
        "driver_maturity": 0.10,
        "multi_device_support": 0.10,
        "deployment_support": 0.05,
    }
    group_scores: dict[str, float] = {}
    for group, keys in groups.items():
        known = [_score(support.get(key)) for key in keys if key in support]
        values = [value for value in known if value is not None]
        if values:
            group_scores[group] = sum(values) / len(values)
    return _weighted(group_scores, group_weights)


def deployability_score(device: Mapping[str, Any]) -> float | None:
    deployment = device.get("deployability", {})
    if not isinstance(deployment, Mapping):
        return None
    return _weighted(
        deployment,
        {
            "installation": 0.15,
            "driver_setup": 0.15,
            "firmware_setup": 0.08,
            "power_integration": 0.12,
            "cooling_integration": 0.10,
            "host_compatibility": 0.15,
            "runtime_setup": 0.15,
            "model_conversion": 0.10,
        },
    )


def reliability_score(device: Mapping[str, Any]) -> float | None:
    """Translate reproducible soak-test observations into a transparent 0-100 score."""
    soak = device.get("soak", {})
    if not isinstance(soak, Mapping) or not soak:
        return None
    hours = float(soak.get("hours", 0.0) or 0.0)
    crashes = int(soak.get("crashes", 0) or 0)
    resets = int(soak.get("resets", 0) or 0)
    inference_errors = int(soak.get("inference_errors", 0) or 0)
    throttle_events = int(soak.get("thermal_throttle_events", 0) or 0)
    cv = float(soak.get("throughput_cv", 1.0) or 1.0)

    duration = min(1.0, hours / 24.0) * 20.0
    stability = max(0.0, 40.0 - 12.0 * crashes - 8.0 * resets - 4.0 * inference_errors)
    consistency = max(0.0, 15.0 * (1.0 - min(cv, 1.0)))
    thermal = 10.0 if throttle_events == 0 else max(0.0, 10.0 - 2.0 * throttle_events)
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
    """Return secondary dimensions kept separate from workload performance scores."""
    return {
        "software_support": software_support_score(device),
        "deployability": deployability_score(device),
        "reliability": reliability_score(device),
        "sustained_ratio": sustained_ratio(device),
        "thermal_headroom_c": thermal_headroom_c(device),
        "energy_proportionality": energy_proportionality(device),
    }
