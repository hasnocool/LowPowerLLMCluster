# src/lowpower_llm_cluster/tco.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalog import load_catalog, project_root


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_tco_scenarios(path: Path | None = None) -> dict[str, Any]:
    target = path or project_root() / "data" / "market" / "tco-scenarios.json"
    return _load(target, {"schema_version": 3, "component_costs_cad": {}, "ownership_profiles": {}, "energy_scenarios": {}})


def deployment_requirements(part: dict[str, Any]) -> dict[str, Any]:
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
        components = ["cpu_host", "motherboard", "host_ram_32gb", "storage_1tb", "psu_750w", "pcie_adapter", "cooling", "chassis", "chassis_misc"]
    elif "usb" in host_mode:
        profile = "host_attached_usb"
        components = ["cpu_host", "motherboard", "host_ram_32gb", "storage_1tb", "power_supply", "chassis"]
    elif "module" in host_mode or "som" in hardware_class:
        profile = "module_requires_carrier"
        components = ["carrier_board", "storage_1tb", "power_supply", "cooling", "chassis", "chassis_misc"]
    elif memory_status == "configurable" or any(token in name for token in ("barebone", "mainboard", "motherboard")):
        profile = "barebone_or_board"
        components = ["system_ram_32gb", "storage_1tb", "power_supply", "cooling", "chassis", "chassis_misc"]
    elif category in {"sbc", "dev_board", "embedded_board", "specialty_board"}:
        profile = "standalone_board"
        components = ["storage_1tb", "power_supply", "cooling", "chassis", "chassis_misc"]

    if category == "gpu_accelerator":
        warnings.append("GPU board price excludes CPU/host, motherboard, RAM, storage, PSU, chassis and cooling required for a new complete node.")
    if memory_status == "configurable":
        warnings.append("Catalog price is treated as not including system RAM unless the live listing proves otherwise.")
    if profile != "complete_system":
        warnings.append("Infrastructure costs are scenario assumptions, not live sourced component quotes.")
    return {"profile": profile, "components": components, "warnings": warnings}


def ownership_components(scenarios: dict[str, Any], profile: str = "new-build", owned_components: list[str] | None = None) -> set[str]:
    profiles = scenarios.get("ownership_profiles") or {}
    if profile not in profiles:
        raise KeyError(f"unknown ownership profile: {profile}")
    owned = set(str(value) for value in (profiles[profile].get("owned_components") or []))
    owned.update(str(value) for value in (owned_components or []))
    return owned


def infrastructure_cost(
    part: dict[str, Any],
    scenarios: dict[str, Any],
    *,
    ownership_profile: str = "new-build",
    owned_components: list[str] | None = None,
) -> dict[str, Any]:
    requirements = deployment_requirements(part)
    costs = scenarios.get("component_costs_cad") or {}
    owned = ownership_components(scenarios, ownership_profile, owned_components)
    lines: list[dict[str, Any]] = []
    total = 0.0
    avoided = 0.0
    for component in requirements["components"]:
        value = costs.get(component)
        if component in owned:
            avoided += float(value or 0.0)
            lines.append({"component": component, "cad": 0.0, "reference_cad": float(value) if value is not None else None, "basis": "already_owned"})
            continue
        if value is None:
            lines.append({"component": component, "cad": None, "basis": "missing_assumption"})
            continue
        cad = float(value)
        total += cad
        lines.append({"component": component, "cad": round(cad, 2), "basis": "planning_assumption"})
    return {
        "profile": requirements["profile"],
        "ownership_profile": ownership_profile,
        "owned_components": sorted(owned),
        "components": lines,
        "total_cad": round(total, 2),
        "avoided_acquisition_cad": round(avoided, 2),
        "complete": all(line.get("cad") is not None for line in lines),
        "warnings": requirements["warnings"],
    }


def complete_node_power(part: dict[str, Any], scenarios: dict[str, Any]) -> dict[str, Any]:
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
    return {"idle_w": round(idle, 1), "load_w": round(load, 1), "basis": basis, "confidence": confidence, "source_power_scope": scope, "warnings": warnings}


def operating_cost(power: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    idle_w, load_w = power.get("idle_w"), power.get("load_w")
    if idle_w is None or load_w is None:
        return {"annual_kwh": None, "annual_cad": None, "years": int(scenario.get("years", 3)), "period_cad": None}
    load_h = float(scenario.get("load_hours_per_day", 4.0))
    idle_h = float(scenario.get("idle_hours_per_day", max(0.0, 24.0 - load_h)))
    days = float(scenario.get("days_per_year", 365.0))
    rate = float(scenario.get("electricity_cad_per_kwh", 0.15))
    years = int(scenario.get("years", 3))
    annual_kwh = (((float(load_w) * load_h) + (float(idle_w) * idle_h)) / 1000.0) * days
    annual_cad = annual_kwh * rate
    return {"annual_kwh": round(annual_kwh, 1), "electricity_cad_per_kwh": rate, "annual_cad": round(annual_cad, 2), "years": years, "period_cad": round(annual_cad * years, 2), "load_hours_per_day": load_h, "idle_hours_per_day": idle_h}


def evaluate_tco(
    part: dict[str, Any],
    product_price_cad: float | None,
    *,
    scenario_name: str = "mixed-3yr",
    scenarios: dict[str, Any] | None = None,
    ownership_profile: str = "new-build",
    owned_components: list[str] | None = None,
) -> dict[str, Any]:
    scenarios = scenarios or load_tco_scenarios()
    infra = infrastructure_cost(part, scenarios, ownership_profile=ownership_profile, owned_components=owned_components)
    power = complete_node_power(part, scenarios)
    energy_scenarios = scenarios.get("energy_scenarios") or {}
    scenario = energy_scenarios.get(scenario_name) or next(iter(energy_scenarios.values()), {})
    energy = operating_cost(power, scenario)
    acquisition = None if product_price_cad is None or not infra["complete"] else round(float(product_price_cad) + float(infra["total_cad"]), 2)
    period = energy.get("period_cad")
    total = None if acquisition is None or period is None else round(float(acquisition) + float(period), 2)
    return {
        "scenario": scenario_name,
        "ownership_profile": ownership_profile,
        "product_price_cad": round(float(product_price_cad), 2) if product_price_cad is not None else None,
        "infrastructure": infra,
        "complete_node_acquisition_cad": acquisition,
        "power": power,
        "operating": energy,
        "total_cost_of_ownership_cad": total,
        "basis": "sourced product price plus ownership-aware incremental infrastructure and editable electricity assumptions",
        "warnings": list(dict.fromkeys([*infra.get("warnings", []), *power.get("warnings", [])])),
    }


def _scenario(scenarios: dict[str, Any], name: str) -> dict[str, Any]:
    values = scenarios.get("energy_scenarios") or {}
    if name not in values:
        raise KeyError(f"unknown TCO scenario: {name}")
    return dict(values[name])


def break_even_analysis(
    part_a: dict[str, Any], price_a_cad: float, part_b: dict[str, Any], price_b_cad: float, *,
    scenario_name: str = "mixed-3yr", scenarios: dict[str, Any] | None = None,
    ownership_profile_a: str = "new-build", ownership_profile_b: str = "new-build",
    owned_components_a: list[str] | None = None, owned_components_b: list[str] | None = None,
) -> dict[str, Any]:
    scenarios = scenarios or load_tco_scenarios()
    scenario = _scenario(scenarios, scenario_name)
    tco_a = evaluate_tco(part_a, price_a_cad, scenario_name=scenario_name, scenarios=scenarios, ownership_profile=ownership_profile_a, owned_components=owned_components_a)
    tco_b = evaluate_tco(part_b, price_b_cad, scenario_name=scenario_name, scenarios=scenarios, ownership_profile=ownership_profile_b, owned_components=owned_components_b)
    infra_a = float((tco_a.get("infrastructure") or {}).get("total_cad") or 0.0)
    infra_b = float((tco_b.get("infrastructure") or {}).get("total_cad") or 0.0)
    operating_a = float((tco_a.get("operating") or {}).get("period_cad") or 0.0)
    operating_b = float((tco_b.get("operating") or {}).get("period_cad") or 0.0)
    price_a_break_even = float(price_b_cad) + infra_b + operating_b - infra_a - operating_a
    price_b_break_even = float(price_a_cad) + infra_a + operating_a - infra_b - operating_b
    power_a, power_b = tco_a.get("power") or {}, tco_b.get("power") or {}
    load_a, load_b, idle_a, idle_b = power_a.get("load_w"), power_b.get("load_w"), power_a.get("idle_w"), power_b.get("idle_w")
    years, days = float(scenario.get("years", 3)), float(scenario.get("days_per_year", 365))
    load_h, idle_h, rate = float(scenario.get("load_hours_per_day", 0)), float(scenario.get("idle_hours_per_day", 0)), float(scenario.get("electricity_cad_per_kwh", 0))
    rate_break_even = None
    load_hours_break_even = None
    if None not in (load_a, load_b, idle_a, idle_b):
        annual_delta_kwh = ((((float(load_a) - float(load_b)) * load_h) + ((float(idle_a) - float(idle_b)) * idle_h)) / 1000.0) * days
        acquisition_delta = (float(price_a_cad) + infra_a) - (float(price_b_cad) + infra_b)
        period_delta_kwh = annual_delta_kwh * years
        if abs(period_delta_kwh) > 1e-9:
            candidate = -acquisition_delta / period_delta_kwh
            if candidate >= 0: rate_break_even = round(candidate, 4)
        total_daily_hours = load_h + idle_h
        if total_daily_hours > 0 and rate > 0 and years > 0 and days > 0:
            delta_load = float(load_a) - float(load_b); delta_idle = float(idle_a) - float(idle_b)
            denominator = (delta_load - delta_idle) * days * years * rate / 1000.0
            constant = acquisition_delta + (delta_idle * total_daily_hours * days * years * rate / 1000.0)
            if abs(denominator) > 1e-9:
                candidate_h = -constant / denominator
                if 0 <= candidate_h <= total_daily_hours: load_hours_break_even = round(candidate_h, 2)
    total_a, total_b = tco_a.get("total_cost_of_ownership_cad"), tco_b.get("total_cost_of_ownership_cad")
    cheaper = None if None in (total_a, total_b) else ("a" if float(total_a) < float(total_b) else "b" if float(total_b) < float(total_a) else "equal")
    return {
        "scenario": scenario_name,
        "a": {"id": part_a.get("id"), "name": part_a.get("name"), "price_cad": price_a_cad, "ownership_profile": ownership_profile_a, "tco": tco_a},
        "b": {"id": part_b.get("id"), "name": part_b.get("name"), "price_cad": price_b_cad, "ownership_profile": ownership_profile_b, "tco": tco_b},
        "currently_cheaper": cheaper,
        "price_a_break_even_cad": round(price_a_break_even, 2), "price_b_break_even_cad": round(price_b_break_even, 2),
        "electricity_rate_break_even_cad_per_kwh": rate_break_even, "load_hours_per_day_break_even": load_hours_break_even,
        "notes": ["Already-owned components have zero incremental acquisition cost, but continue to contribute to complete-node electricity use.", "Break-even thresholds hold all other selected scenario assumptions constant.", "Power-derived thresholds remain planning estimates when either option lacks measured complete-node input power."],
    }


def apply_tco_to_summary(summary: dict[str, Any], *, scenario_name: str = "mixed-3yr", scenarios: dict[str, Any] | None = None, ownership_profile: str = "new-build", owned_components: list[str] | None = None) -> dict[str, Any]:
    scenarios = scenarios or load_tco_scenarios()
    parts = {str(part["id"]): part for part in load_catalog()["parts"]}
    rows = list(summary.get("recommendations", []))
    for row in rows:
        part = parts.get(str(row.get("id")))
        row["tco"] = evaluate_tco(part, row.get("current_cad"), scenario_name=scenario_name, scenarios=scenarios, ownership_profile=ownership_profile, owned_components=owned_components) if part else None
    totals = sorted(float((row.get("tco") or {}).get("total_cost_of_ownership_cad")) for row in rows if (row.get("tco") or {}).get("total_cost_of_ownership_cad") is not None)
    for row in rows:
        tco = row.get("tco") or {}; total = tco.get("total_cost_of_ownership_cad"); old_score = float(row.get("deal_score") or 0.0); percentile = None
        if total is not None and totals:
            percentile = sum(1 for value in totals if value <= float(total)) / len(totals)
            adjusted = (old_score * 0.75) + ((1.0 - percentile) * 25.0)
            acquisition = tco.get("complete_node_acquisition_cad"); product = tco.get("product_price_cad"); period = (tco.get("operating") or {}).get("period_cad")
            if acquisition and product and float(acquisition) > float(product) * 1.5: adjusted -= 5.0
            if acquisition and period and float(period) > float(acquisition) * 0.5: adjusted -= 5.0
        else: adjusted = min(old_score, 59.0)
        adjusted = round(max(0.0, min(100.0, adjusted)), 1); row["pre_tco_deal_score"] = old_score; row["deal_score"] = adjusted; row["tco_percentile"] = round(percentile, 3) if percentile is not None else None
        original = str(row.get("recommendation"))
        if original == "Experimental": recommendation = original
        elif total is None: recommendation = "Watch" if original == "Buy" else original
        elif adjusted >= 72 and original in {"Buy", "Watch"}: recommendation = "Buy"
        elif adjusted >= 45: recommendation = "Watch"
        else: recommendation = "Ignore"
        row["recommendation"] = recommendation
        infra = tco.get("infrastructure") or {}
        if infra.get("total_cad", 0): row.setdefault("reasons", []).append(f"incremental infrastructure CA${float(infra['total_cad']):,.0f} under {ownership_profile}")
        if infra.get("avoided_acquisition_cad", 0): row.setdefault("reasons", []).append(f"already-owned infrastructure avoids CA${float(infra['avoided_acquisition_cad']):,.0f} of modeled acquisition")
        if total is not None: row.setdefault("reasons", []).append(f"{scenario_name} TCO CA${float(total):,.0f}")
    order = {"Buy": 0, "Watch": 1, "Experimental": 2, "Ignore": 3}; rows.sort(key=lambda row: (order.get(str(row.get("recommendation")), 9), -float(row.get("deal_score") or 0.0), str(row.get("name") or "")))
    summary["recommendations"] = rows; summary["counts"] = {name: sum(1 for row in rows if row.get("recommendation") == name) for name in ("Buy", "Watch", "Experimental", "Ignore")}; summary["tco_scenario"] = scenario_name; summary["ownership_profile"] = ownership_profile
    summary.setdefault("method_notes", []).extend(["TCO is incremental-acquisition aware: already-owned compatible components cost CA$0 to acquire again.", "Owned components still consume power and therefore remain in the complete-node operating-cost model.", "Custom owned-component overrides can supplement a named ownership profile."])
    return summary


def render_tco_report(summary: dict[str, Any], *, limit: int = 30) -> str:
    lines = ["# Complete-Node Total Cost of Ownership", "", f"Scenario: **{summary.get('tco_scenario', 'mixed-3yr')}**", f"Ownership: **{summary.get('ownership_profile', 'new-build')}**", "", "Product price is separated from incremental infrastructure and electricity. Already-owned compatible parts have zero acquisition cost but remain part of the powered node.", "", "Decision | Score | Product | Missing infra | Avoided owned cost | Complete node | Operating | TCO | Candidate", "--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---"]
    def money(value: Any) -> str: return f"CA${float(value):,.0f}" if value is not None else "—"
    for row in list(summary.get("recommendations", []))[:limit]:
        tco = row.get("tco") or {}; infra = tco.get("infrastructure") or {}; operating = tco.get("operating") or {}
        lines.append(f"{row.get('recommendation')} | {float(row.get('deal_score') or 0):.1f} | {money(tco.get('product_price_cad'))} | {money(infra.get('total_cad'))} | {money(infra.get('avoided_acquisition_cad'))} | {money(tco.get('complete_node_acquisition_cad'))} | {money(operating.get('period_cad'))} | {money(tco.get('total_cost_of_ownership_cad'))} | {row.get('name')}")
    lines.extend(["", "- Missing infra = only components that must still be purchased.", "- Avoided owned cost = planning-reference cost of required parts already owned and compatible.", "- Ownership changes acquisition cost, not the complete-node power model.", ""])
    return "\n".join(lines)
