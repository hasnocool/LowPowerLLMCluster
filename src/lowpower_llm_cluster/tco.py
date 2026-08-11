# src/lowpower_llm_cluster/tco.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalog import project_root


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_tco_scenarios(path: Path | None = None) -> dict[str, Any]:
    target = path or project_root() / "data" / "market" / "tco-scenarios.json"
    return _load(target, {"schema_version": 1, "component_costs_cad": {}, "energy_scenarios": {}})


def deployment_requirements(part: dict[str, Any]) -> dict[str, Any]:
    """Return infrastructure required to turn a catalog item into a usable node.

    This is intentionally conservative. It distinguishes complete/integrated systems
    from barebones and host-attached accelerators. Unknown requirements are surfaced
    as assumptions rather than silently counted as included.
    """
    category = str(part.get("category") or "")
    host_mode = str(part.get("host_mode") or "").casefold()
    hardware_class = str(part.get("hardware_class") or "").casefold()
    name = str(part.get("name") or "").casefold()
    memory_status = str(part.get("memory_config_status") or "unknown")

    components: list[str] = []
    warnings: list[str] = []
    profile = "complete_system"

    if "pcie" in host_mode or category == "gpu_accelerator":
        profile = "host_attached_pcie"
        components = ["host_platform", "host_ram_32gb", "storage_1tb", "psu_750w", "pcie_adapter", "cooling", "chassis_misc"]
    elif "usb" in host_mode:
        profile = "host_attached_usb"
        components = ["host_platform", "host_ram_32gb", "storage_1tb"]
    elif "module" in host_mode or "som" in hardware_class:
        profile = "module_requires_carrier"
        components = ["carrier_board", "storage_1tb", "cooling", "chassis_misc"]
    elif memory_status == "configurable" or any(token in name for token in ("barebone", "mainboard", "motherboard")):
        profile = "barebone_or_board"
        components = ["system_ram_32gb", "storage_1tb", "power_supply", "cooling", "chassis_misc"]
    elif category in {"sbc", "dev_board", "embedded_board", "specialty_board"}:
        profile = "standalone_board"
        components = ["storage_1tb", "power_supply", "cooling", "chassis_misc"]

    if category == "gpu_accelerator":
        warnings.append("GPU board price excludes the host platform required to use the card.")
    if memory_status == "configurable":
        warnings.append("Catalog price is treated as not including system RAM unless the live listing proves otherwise.")
    if profile != "complete_system":
        warnings.append("Infrastructure costs are scenario assumptions, not live sourced component quotes.")

    return {"profile": profile, "components": components, "warnings": warnings}


def infrastructure_cost(part: dict[str, Any], scenarios: dict[str, Any]) -> dict[str, Any]:
    requirements = deployment_requirements(part)
    costs = scenarios.get("component_costs_cad") or {}
    lines: list[dict[str, Any]] = []
    total = 0.0
    for component in requirements["components"]:
        value = costs.get(component)
        if value is None:
            lines.append({"component": component, "cad": None, "basis": "missing_assumption"})
            continue
        cad = float(value)
        total += cad
        lines.append({"component": component, "cad": round(cad, 2), "basis": "planning_assumption"})
    return {
        "profile": requirements["profile"],
        "components": lines,
        "total_cad": round(total, 2),
        "complete": all(line["cad"] is not None for line in lines),
        "warnings": requirements["warnings"],
    }


def complete_node_power(part: dict[str, Any], scenarios: dict[str, Any]) -> dict[str, Any]:
    """Return planning idle/load watts with an explicit evidence boundary."""
    scope = str(part.get("power_scope") or "unknown")
    target = part.get("power_target_w")
    target_w = float(target) if target is not None else None
    assumptions = scenarios.get("power_assumptions") or {}
    host_idle = float(assumptions.get("host_idle_w", 35.0))
    host_load = float(assumptions.get("host_load_w", 90.0))
    platform_idle_ratio = float(assumptions.get("integrated_idle_ratio", 0.25))
    gpu_idle = float(assumptions.get("gpu_idle_w", 20.0))
    overhead_pct = float(assumptions.get("psu_cooling_overhead_pct", 0.08))

    warnings: list[str] = []
    if target_w is None:
        return {"idle_w": None, "load_w": None, "basis": "unknown", "confidence": "unknown", "warnings": ["No usable power evidence is available for this product."]}

    if scope == "complete_node_input":
        load = target_w
        idle = target_w * platform_idle_ratio
        basis = "complete_node_reference_or_measurement"
        confidence = "medium"
    elif scope.startswith("accelerator_board") or str(part.get("category")) == "gpu_accelerator":
        load = (host_load + target_w) * (1.0 + overhead_pct)
        idle = (host_idle + gpu_idle) * (1.0 + overhead_pct)
        basis = "estimated_complete_node_from_board_power_plus_host_assumptions"
        confidence = "low"
        warnings.append("Complete-node power is estimated from accelerator board power plus host/PSU/cooling assumptions; it is not a wall measurement.")
    else:
        load = target_w * (1.0 + overhead_pct)
        idle = max(5.0, target_w * platform_idle_ratio)
        basis = "estimated_complete_node_from_published_platform_power"
        confidence = "low"
        warnings.append("Complete-node power is inferred from a published platform/board power value, not measured wall input.")

    return {
        "idle_w": round(idle, 1),
        "load_w": round(load, 1),
        "basis": basis,
        "confidence": confidence,
        "source_power_scope": scope,
        "warnings": warnings,
    }


def operating_cost(power: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    idle_w = power.get("idle_w")
    load_w = power.get("load_w")
    if idle_w is None or load_w is None:
        return {"annual_kwh": None, "annual_cad": None, "years": int(scenario.get("years", 3)), "period_cad": None}
    load_h = float(scenario.get("load_hours_per_day", 4.0))
    idle_h = float(scenario.get("idle_hours_per_day", max(0.0, 24.0 - load_h)))
    days = float(scenario.get("days_per_year", 365.0))
    rate = float(scenario.get("electricity_cad_per_kwh", 0.15))
    years = int(scenario.get("years", 3))
    annual_kwh = (((float(load_w) * load_h) + (float(idle_w) * idle_h)) / 1000.0) * days
    annual_cad = annual_kwh * rate
    return {
        "annual_kwh": round(annual_kwh, 1),
        "electricity_cad_per_kwh": rate,
        "annual_cad": round(annual_cad, 2),
        "years": years,
        "period_cad": round(annual_cad * years, 2),
        "load_hours_per_day": load_h,
        "idle_hours_per_day": idle_h,
    }


def evaluate_tco(
    part: dict[str, Any],
    product_price_cad: float | None,
    *,
    scenario_name: str = "mixed-3yr",
    scenarios: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scenarios = scenarios or load_tco_scenarios()
    infra = infrastructure_cost(part, scenarios)
    power = complete_node_power(part, scenarios)
    energy_scenarios = scenarios.get("energy_scenarios") or {}
    scenario = energy_scenarios.get(scenario_name) or next(iter(energy_scenarios.values()), {})
    energy = operating_cost(power, scenario)

    acquisition = None if product_price_cad is None or not infra["complete"] else round(float(product_price_cad) + float(infra["total_cad"]), 2)
    period = energy.get("period_cad")
    total = None if acquisition is None or period is None else round(float(acquisition) + float(period), 2)
    product_share = None if acquisition in (None, 0) or product_price_cad is None else round(float(product_price_cad) / float(acquisition), 3)

    return {
        "scenario": scenario_name,
        "product_price_cad": round(float(product_price_cad), 2) if product_price_cad is not None else None,
        "infrastructure": infra,
        "complete_node_acquisition_cad": acquisition,
        "product_share_of_acquisition": product_share,
        "power": power,
        "operating": energy,
        "total_cost_of_ownership_cad": total,
        "basis": "live/sourced product price plus editable infrastructure and electricity planning assumptions",
        "warnings": list(dict.fromkeys([*infra.get("warnings", []), *power.get("warnings", [])])),
    }
