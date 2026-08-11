# src/lowpower_llm_cluster/power_model.py
from __future__ import annotations

from typing import Any

# Conservative planning baselines used only when stronger per-part evidence is absent.
# Values represent the device/component itself, not an attached host unless noted.
CATEGORY_POWER_DEFAULTS: dict[str, dict[str, float]] = {
    "compute_node": {"idle_w": 12.0, "load_w": 45.0},
    "mini_pc": {"idle_w": 8.0, "load_w": 35.0},
    "dev_board": {"idle_w": 4.0, "load_w": 15.0},
    "sbc": {"idle_w": 3.0, "load_w": 12.0},
    "embedded_board": {"idle_w": 4.0, "load_w": 18.0},
    "specialty_board": {"idle_w": 8.0, "load_w": 35.0},
    "control_plane": {"idle_w": 4.0, "load_w": 12.0},
    "apple_silicon_system": {"idle_w": 7.0, "load_w": 45.0},
    "mobile_phone": {"idle_w": 1.2, "load_w": 6.0},
    "tablet": {"idle_w": 2.0, "load_w": 12.0},
    "media_device": {"idle_w": 2.5, "load_w": 8.0},
    "gpu_accelerator": {"idle_w": 18.0, "load_w": 180.0},
    "npu_accelerator": {"idle_w": 2.0, "load_w": 12.0},
    "tpu_accelerator": {"idle_w": 2.0, "load_w": 15.0},
    "ai_asic_accelerator": {"idle_w": 3.0, "load_w": 20.0},
    "fpga_accelerator": {"idle_w": 8.0, "load_w": 45.0},
    "adaptive_soc": {"idle_w": 5.0, "load_w": 25.0},
    "decommissioned_accelerator": {"idle_w": 25.0, "load_w": 180.0},
    "network": {"idle_w": 4.0, "load_w": 10.0},
    "memory": {"idle_w": 1.0, "load_w": 3.0},
    "storage": {"idle_w": 0.8, "load_w": 4.0},
}

ACCELERATOR_CATEGORIES = {
    "gpu_accelerator", "npu_accelerator", "tpu_accelerator", "ai_asic_accelerator",
    "fpga_accelerator", "adaptive_soc", "decommissioned_accelerator",
}


def _number(part: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = part.get(key)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number >= 0:
            return number
    return None


def _category_default(category: str) -> dict[str, float]:
    return dict(CATEGORY_POWER_DEFAULTS.get(category, {"idle_w": 5.0, "load_w": 25.0}))


def _idle_ratio(category: str) -> float:
    if category in {"mobile_phone", "tablet", "media_device"}:
        return 0.18
    if category in ACCELERATOR_CATEGORIES:
        return 0.12
    if category in {"memory", "storage", "network"}:
        return 0.35
    return 0.25


def estimate_device_power(part: dict[str, Any]) -> dict[str, Any]:
    """Estimate direct hardware power using the strongest available evidence.

    Evidence order: measured idle/load -> measured load -> published target/limit -> category baseline.
    Battery capacity and charger ratings are intentionally not treated as consumption.
    """
    category = str(part.get("category") or "unknown")
    measured_idle = _number(part, "measured_idle_w", "idle_power_w", "wall_idle_w")
    measured_load = _number(part, "measured_load_w", "load_power_w", "wall_load_w")
    measured_typical = _number(part, "measured_power_w", "wall_power_w")
    if measured_load is None:
        measured_load = measured_typical
    if measured_load is not None:
        idle = measured_idle if measured_idle is not None else measured_load * _idle_ratio(category)
        return {
            "idle_w": round(idle, 2), "load_w": round(measured_load, 2), "basis": "measured_power",
            "confidence": "high" if measured_idle is not None else "medium",
            "power_scope": str(part.get("power_scope") or "measured_device_input"),
            "inferred": measured_idle is None,
            "warnings": [] if measured_idle is not None else ["Idle power is inferred from measured load because a separate idle measurement is unavailable."],
        }

    target = _number(part, "power_target_w")
    maximum = _number(part, "power_max_w", "tdp_w", "tbp_w", "tgp_w", "board_power_w")
    if target is not None:
        load = min(target, maximum) if maximum is not None and maximum >= target else target
        idle = max(0.2, target * _idle_ratio(category))
        return {
            "idle_w": round(idle, 2), "load_w": round(load, 2), "basis": "published_target_power",
            "confidence": "medium", "power_scope": str(part.get("power_scope") or "published_device_or_board_power"),
            "inferred": True,
            "warnings": ["Idle power is inferred from the published target power; target/TDP/TBP is not a wall measurement."],
        }

    if maximum is not None:
        load_factor = 0.82 if category in ACCELERATOR_CATEGORIES else 0.70
        load = maximum * load_factor
        idle = max(0.2, load * _idle_ratio(category))
        return {
            "idle_w": round(idle, 2), "load_w": round(load, 2), "max_w": round(maximum, 2),
            "basis": "derived_from_published_maximum", "confidence": "low",
            "power_scope": str(part.get("power_scope") or "published_device_or_board_limit"), "inferred": True,
            "warnings": ["Typical load is inferred below the published maximum/TDP/TBP value; it is a planning estimate, not a measurement."],
        }

    default = _category_default(category)
    return {
        "idle_w": round(default["idle_w"], 2), "load_w": round(default["load_w"], 2),
        "basis": "inferred_category_baseline", "confidence": "low", "power_scope": "device_or_component_estimate",
        "inferred": True,
        "warnings": [f"No per-part power evidence is available; using the conservative '{category}' category planning baseline."],
    }


def estimate_complete_node_power(part: dict[str, Any], assumptions: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return wall-input planning power for a usable node, including host overhead where needed."""
    assumptions = assumptions or {}
    device = estimate_device_power(part)
    category = str(part.get("category") or "")
    scope = str(part.get("power_scope") or device.get("power_scope") or "unknown").casefold()
    host_idle = float(assumptions.get("host_idle_w", 35.0))
    host_load = float(assumptions.get("host_load_w", 90.0))
    overhead_pct = float(assumptions.get("psu_cooling_overhead_pct", 0.08))
    idle, load = float(device["idle_w"]), float(device["load_w"])
    warnings = list(device.get("warnings") or [])
    confidence = str(device.get("confidence") or "unknown")

    if scope == "complete_node_input" or category in {"compute_node", "mini_pc", "apple_silicon_system", "mobile_phone", "tablet", "media_device", "control_plane"}:
        complete_idle, complete_load = idle, load
        basis = device["basis"] if scope == "complete_node_input" else f"{device['basis']}_as_integrated_system"
    elif category in ACCELERATOR_CATEGORIES or scope.startswith("accelerator_board"):
        complete_idle = (host_idle + idle) * (1.0 + overhead_pct)
        complete_load = (host_load + load) * (1.0 + overhead_pct)
        basis = f"complete_node_from_{device['basis']}_plus_host"
        confidence = "low"
        warnings.append("Complete-node power includes inferred host and PSU/cooling overhead; board power is not relabeled as measured wall power.")
    elif category in {"dev_board", "sbc", "embedded_board", "specialty_board"}:
        peripheral_idle = float(assumptions.get("board_peripheral_idle_w", 2.0))
        peripheral_load = float(assumptions.get("board_peripheral_load_w", 5.0))
        complete_idle = (idle + peripheral_idle) * (1.0 + overhead_pct)
        complete_load = (load + peripheral_load) * (1.0 + overhead_pct)
        basis = f"complete_node_from_{device['basis']}_plus_peripherals"
        confidence = "low" if device.get("inferred") else "medium"
    else:
        complete_idle = idle * (1.0 + overhead_pct)
        complete_load = load * (1.0 + overhead_pct)
        basis = f"incremental_component_from_{device['basis']}"
        confidence = "low" if device.get("inferred") else confidence

    return {
        "idle_w": round(complete_idle, 2), "load_w": round(complete_load, 2), "basis": basis,
        "confidence": confidence, "source_power_scope": scope, "device_power": device,
        "inferred": bool(device.get("inferred")) or category in ACCELERATOR_CATEGORIES,
        "warnings": list(dict.fromkeys(warnings)),
    }


def energy_usage_wh(power: dict[str, Any], *, load_hours: float = 1.0, idle_hours: float = 0.0, off_hours: float = 0.0, off_w: float = 0.0) -> dict[str, Any]:
    """Convert a power model into Wh/kWh for an explicit duty cycle."""
    for name, value in (("load_hours", load_hours), ("idle_hours", idle_hours), ("off_hours", off_hours), ("off_w", off_w)):
        if float(value) < 0:
            raise ValueError(f"{name} cannot be negative")
    idle_w, load_w = float(power.get("idle_w") or 0.0), float(power.get("load_w") or 0.0)
    wh = (load_w * float(load_hours)) + (idle_w * float(idle_hours)) + (float(off_w) * float(off_hours))
    total_hours = float(load_hours) + float(idle_hours) + float(off_hours)
    return {
        "load_hours": round(float(load_hours), 3), "idle_hours": round(float(idle_hours), 3), "off_hours": round(float(off_hours), 3),
        "wh": round(wh, 2), "kwh": round(wh / 1000.0, 5), "average_w": round(wh / max(total_hours, 1e-9), 2),
        "basis": power.get("basis"), "confidence": power.get("confidence", "unknown"), "inferred": bool(power.get("inferred", False)),
    }


def daily_energy_usage(part: dict[str, Any], *, load_hours: float = 4.0, idle_hours: float = 20.0, assumptions: dict[str, Any] | None = None) -> dict[str, Any]:
    power = estimate_complete_node_power(part, assumptions)
    return {"power": power, "energy": energy_usage_wh(power, load_hours=load_hours, idle_hours=idle_hours)}
