# src/lowpower_llm_cluster/estimates.py
from __future__ import annotations

from typing import Any

from .evidence import memory_basis

MODEL_PRESETS: dict[str, dict[str, float | str]] = {
    "tiny-1b-q4": {"params_b": 1.0, "bits_per_weight": 4.0, "description": "~1B class model at nominal 4-bit weights"},
    "small-3b-q4": {"params_b": 3.0, "bits_per_weight": 4.0, "description": "~3B class model at nominal 4-bit weights"},
    "7b-q4": {"params_b": 7.0, "bits_per_weight": 4.0, "description": "~7B class model at nominal 4-bit weights"},
    "14b-q4": {"params_b": 14.0, "bits_per_weight": 4.0, "description": "~14B class model at nominal 4-bit weights"},
    "32b-q4": {"params_b": 32.0, "bits_per_weight": 4.0, "description": "~32B class model at nominal 4-bit weights"},
    "70b-q4": {"params_b": 70.0, "bits_per_weight": 4.0, "description": "~70B class model at nominal 4-bit weights"},
    "70b-q6": {"params_b": 70.0, "bits_per_weight": 6.0, "description": "~70B class model at nominal 6-bit weights"},
}


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
    """Conservative capacity screen, not a throughput prediction."""
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


def model_fit_preset(part: dict[str, Any], preset: str, *, runtime_headroom_fraction: float = 0.12, extra_headroom_gb: float = 2.0) -> dict[str, Any]:
    try:
        selected = MODEL_PRESETS[preset]
    except KeyError as exc:
        raise KeyError(f"unknown model preset {preset!r}; choices: {', '.join(sorted(MODEL_PRESETS))}") from exc
    result = model_fit_screen(
        part, params_b=float(selected["params_b"]), bits_per_weight=float(selected["bits_per_weight"]),
        runtime_headroom_fraction=runtime_headroom_fraction, extra_headroom_gb=extra_headroom_gb,
    )
    return {**result, "preset": preset, "preset_description": selected["description"]}
