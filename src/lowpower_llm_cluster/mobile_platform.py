from __future__ import annotations

from typing import Any


def mobile_runtime_profile(part: dict[str, Any]) -> dict[str, Any]:
    """Return deployment constraints for Apple/mobile devices without inventing performance."""
    category = str(part.get("category") or "")
    stack = str(part.get("software_stack") or "").casefold()
    name = str(part.get("name") or "")
    android = any(term in stack for term in ("android", "oxygenos", "one ui", "hyperos", "redmagicos"))
    vulkan = "vulkan" in stack

    if category == "apple_silicon_system":
        return {
            "host_class": "general_purpose",
            "headless_service": True,
            "local_cli": True,
            "metal": "metal" in stack,
            "vulkan": vulkan,
            "mlx": "mlx" in stack,
            "core_ml": "core ml" in stack,
            "persistent_daemon": True,
            "thermal_constraint": "device_specific",
            "memory_shared_with_gpu": True,
            "notes": "macOS Apple-silicon systems are general-purpose nodes; exact unified-memory configuration is fixed at purchase.",
        }
    if category == "mobile_phone":
        return {
            "host_class": "mobile_endpoint",
            "headless_service": False,
            "local_cli": android,
            "metal": "metal" in stack,
            "vulkan": vulkan,
            "mlx": False,
            "core_ml": "core ml" in stack,
            "persistent_daemon": False,
            "thermal_constraint": "high",
            "memory_shared_with_gpu": True,
            "notes": (
                "Android phones can expose app-local/native CLI inference paths, but background execution and sustained thermals remain device-specific; do not rank them as unattended daemon hosts."
                if android
                else "Phone-class devices are interactive/sandboxed inference endpoints; do not rank them as unattended daemon hosts."
            ),
        }
    if category == "tablet":
        return {
            "host_class": "mobile_endpoint",
            "headless_service": False,
            "local_cli": android,
            "metal": "metal" in stack,
            "vulkan": vulkan,
            "mlx": False,
            "core_ml": "core ml" in stack,
            "persistent_daemon": False,
            "thermal_constraint": "medium_high",
            "memory_shared_with_gpu": True,
            "notes": (
                "Android tablets can expose app-local/native CLI inference paths and may have more thermal area than phones, but they remain mobile endpoints rather than normal daemon hosts."
                if android
                else "Tablet-class devices can run substantial on-device inference but remain app-sandboxed and thermally constrained."
            ),
        }
    if category == "media_device":
        return {
            "host_class": "restricted_endpoint",
            "headless_service": False,
            "local_cli": False,
            "metal": "metal" in stack,
            "vulkan": vulkan,
            "mlx": False,
            "core_ml": "core ml" in stack,
            "persistent_daemon": False,
            "thermal_constraint": "device_specific",
            "memory_shared_with_gpu": True,
            "notes": "tvOS/media devices are retained for specialist experiments, not general LLM serving.",
        }
    return {
        "host_class": "unknown",
        "headless_service": None,
        "local_cli": None,
        "persistent_daemon": None,
        "memory_shared_with_gpu": None,
        "notes": f"No mobile runtime policy for {name or category or 'unknown device'}.",
    }


def model_fit_memory_budget(part: dict[str, Any], *, reserve_fraction: float | None = None) -> dict[str, Any]:
    """Conservative usable-memory screen; this is capacity accounting, not a throughput estimate."""
    capacity = part.get("memory_capacity_gb")
    if capacity is None:
        return {"known": False, "usable_gb": None, "reason": "memory_capacity_unknown"}
    profile = mobile_runtime_profile(part)
    if reserve_fraction is None:
        reserve_fraction = 0.25 if profile["host_class"] == "general_purpose" else 0.40
    reserve_fraction = min(max(float(reserve_fraction), 0.0), 0.80)
    usable = round(float(capacity) * (1.0 - reserve_fraction), 2)
    return {
        "known": True,
        "installed_gb": float(capacity),
        "reserve_fraction": reserve_fraction,
        "usable_gb": usable,
        "basis": "conservative_capacity_reserve",
        "performance_claim": False,
    }
