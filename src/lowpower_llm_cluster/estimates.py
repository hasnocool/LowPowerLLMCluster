from __future__ import annotations

from typing import Any

from .evidence import memory_basis


def model_weight_gb(params_b: float, bits_per_weight: float) -> float:
    if params_b <= 0 or bits_per_weight <= 0:
        raise ValueError("params_b and bits_per_weight must be positive")
    return params_b * bits_per_weight / 8.0


def model_fit_screen(
    part: dict[str, Any],
    *,
    params_b: float,
    bits_per_weight: float,
    runtime_headroom_fraction: float = 0.12,
    extra_headroom_gb: float = 2.0,
) -> dict[str, Any]:
    """Conservative capacity screen, not a throughput prediction.

    It estimates weight storage from parameter count and nominal bits/weight, then
    adds configurable planning headroom. KV cache/runtime details vary by model and
    backend, so the result intentionally says only whether this is a reasonable
    catalog candidate to investigate further.
    """
    if runtime_headroom_fraction < 0 or extra_headroom_gb < 0:
        raise ValueError("headroom values cannot be negative")
    weights = model_weight_gb(params_b, bits_per_weight)
    planning = weights * (1.0 + runtime_headroom_fraction) + extra_headroom_gb
    memory_gb, basis, confidence_weight = memory_basis(part)

    if memory_gb is None:
        status = "unknown_memory"
    elif memory_gb < weights:
        status = "weights_do_not_fit"
    elif memory_gb < planning:
        status = "weights_fit_but_headroom_tight"
    elif basis in {"configurable_max", "cpu_theoretical_max_unverified_on_board"}:
        status = "possible_after_memory_configuration"
    else:
        status = "reasonable_capacity_candidate"

    return {
        "hardware_id": part.get("id"),
        "params_b": round(float(params_b), 3),
        "bits_per_weight": round(float(bits_per_weight), 3),
        "weights_only_gb": round(weights, 2),
        "planning_memory_gb": round(planning, 2),
        "catalog_memory_gb": round(memory_gb, 2) if memory_gb is not None else None,
        "memory_basis": basis,
        "memory_evidence_weight": confidence_weight,
        "status": status,
        "warning": "Capacity screen only. It does not predict tokens/sec and cannot know exact KV-cache/runtime overhead without a specific model/backend.",
    }
