from __future__ import annotations

import itertools
import json
import re
from pathlib import Path
from typing import Any

from .catalog import project_root


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("-", " ").split())


def _number(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def infer_listing_facts(component: str, title: str, spec: dict[str, Any]) -> dict[str, Any]:
    text = _norm(title)
    facts: dict[str, Any] = {"component": component}
    matched_variant = None
    for variant in spec.get("variants", []):
        terms = [_norm(term) for term in variant.get("match_terms", [])]
        if terms and any(term in text for term in terms):
            facts.update(variant.get("facts") or {})
            matched_variant = variant.get("id")
            break
    if matched_variant:
        facts["variant"] = matched_variant
    if component in {"host_ram_32gb", "system_ram_32gb"}:
        if "ddr5" in text: facts.setdefault("memory_type", "DDR5")
        elif "ddr4" in text: facts.setdefault("memory_type", "DDR4")
        capacity = _number(r"(?:^|\D)(\d{1,3})\s*gb(?:\D|$)", text)
        if capacity: facts.setdefault("capacity_gb", int(capacity))
    elif component == "psu_750w":
        watts = _number(r"(?:^|\D)(\d{3,4})\s*w(?:\D|$)", text)
        if watts: facts.setdefault("wattage_w", int(watts))
        connectors = list(facts.get("gpu_power_connectors") or [])
        if any(term in text for term in ("12vhpwr", "12v 2x6", "12v2x6")): connectors.append("12V-2x6")
        if "8 pin" in text or "8pin" in text or "6+2" in text: connectors.append("8-pin")
        if connectors: facts["gpu_power_connectors"] = sorted(set(connectors))
    elif component == "chassis":
        clearance = _number(r"(?:gpu|max(?:imum)? gpu|graphics card)[^0-9]{0,20}(\d{3})\s*mm", text)
        cooler = _number(r"(?:cpu cooler|cooler height)[^0-9]{0,20}(\d{2,3})\s*mm", text)
        if clearance: facts.setdefault("max_gpu_length_mm", int(clearance))
        if cooler: facts.setdefault("max_cpu_cooler_height_mm", int(cooler))
    elif component == "cooling":
        height = _number(r"(?:height|cooler)[^0-9]{0,20}(\d{2,3})\s*mm", text)
        if height: facts.setdefault("height_mm", int(height))
    return facts


def gpu_requirements(part: dict[str, Any]) -> dict[str, Any]:
    requirements = dict(part.get("compatibility_requirements") or {})
    text = str(part.get("host_requirements") or "")
    requirements.setdefault("pcie_slot", "x16")
    lane_match = re.search(r"pcie\s*[0-9.]*\s*x(\d+)", text, re.IGNORECASE)
    if lane_match: requirements.setdefault("minimum_pcie_lanes", int(lane_match.group(1)))
    watt_values = [int(value) for value in re.findall(r"(\d{3,4})\s*w", text, re.IGNORECASE)]
    explicit_psu = part.get("recommended_psu_w")
    if explicit_psu is not None:
        requirements.setdefault("minimum_psu_w", explicit_psu)
    elif watt_values:
        requirements.setdefault("minimum_psu_w", max(watt_values))
    requirements.setdefault("gpu_length_mm", part.get("length_mm"))
    requirements.setdefault("gpu_slots", part.get("slot_width"))
    connectors = part.get("power_connectors")
    if connectors: requirements.setdefault("power_connectors", connectors)
    return {key: value for key, value in requirements.items() if value is not None}


def _check_equal(name: str, left: Any, right: Any, failures: list[str], unknowns: list[str]) -> None:
    if left is None or right is None: unknowns.append(name)
    elif _norm(left) != _norm(right): failures.append(f"{name}: {left} != {right}")


def evaluate_build_compatibility(build: dict[str, dict[str, Any]], gpu_part: dict[str, Any] | None = None) -> dict[str, Any]:
    failures: list[str] = []
    unknowns: list[str] = []
    cpu = build.get("cpu_host", {}).get("compatibility_facts") or {}
    board = build.get("motherboard", {}).get("compatibility_facts") or {}
    ram = build.get("host_ram_32gb", {}).get("compatibility_facts") or {}
    storage = build.get("storage_1tb", {}).get("compatibility_facts") or {}
    psu = build.get("psu_750w", {}).get("compatibility_facts") or {}
    chassis = build.get("chassis", {}).get("compatibility_facts") or {}
    cooler = build.get("cooling", {}).get("compatibility_facts") or {}

    _check_equal("cpu_socket", cpu.get("socket"), board.get("socket"), failures, unknowns)
    cpu_memory = set(str(v).upper() for v in cpu.get("memory_types", []))
    board_memory = str(board.get("memory_type") or "").upper() or None
    ram_memory = str(ram.get("memory_type") or "").upper() or None
    if board_memory and ram_memory and board_memory != ram_memory: failures.append(f"memory_type: motherboard {board_memory} != RAM {ram_memory}")
    elif not board_memory or not ram_memory: unknowns.append("motherboard_ram_memory_type")
    if cpu_memory and board_memory and board_memory not in cpu_memory: failures.append(f"cpu_memory_support: {board_memory} not in {sorted(cpu_memory)}")
    elif not cpu_memory or not board_memory: unknowns.append("cpu_memory_support")

    cooler_sockets = set(str(v) for v in cooler.get("supported_sockets", []))
    if cpu.get("socket") and cooler_sockets and str(cpu["socket"]) not in cooler_sockets: failures.append(f"cooler_socket: {cpu['socket']} unsupported")
    elif cpu.get("socket") and not cooler_sockets: unknowns.append("cooler_socket")

    board_forms = set(str(v).upper() for v in board.get("form_factors", []))
    chassis_forms = set(str(v).upper() for v in chassis.get("motherboard_form_factors", []))
    if board_forms and chassis_forms and not (board_forms & chassis_forms): failures.append(f"motherboard_form_factor: {sorted(board_forms)} not supported by {sorted(chassis_forms)}")
    elif not board_forms or not chassis_forms: unknowns.append("motherboard_form_factor")

    if storage.get("interface") == "NVMe" and board.get("supports_nvme_m2") is False: failures.append("storage_interface: motherboard lacks NVMe M.2 support")
    elif storage.get("interface") == "NVMe" and "supports_nvme_m2" not in board: unknowns.append("nvme_m2_support")

    if gpu_part:
        gpu = gpu_requirements(gpu_part)
        board_slot = str(board.get("gpu_slot") or "") or None
        if board_slot is None: unknowns.append("pcie_gpu_slot")
        elif "x16" not in board_slot.casefold(): failures.append(f"pcie_gpu_slot: {board_slot} is not x16 physical")
        min_psu, psu_w = gpu.get("minimum_psu_w"), psu.get("wattage_w")
        if min_psu is not None and psu_w is not None and float(psu_w) < float(min_psu): failures.append(f"psu_wattage: {psu_w}W < required {min_psu}W")
        elif min_psu is not None and psu_w is None: unknowns.append("psu_wattage")
        required_connectors = set(str(v) for v in gpu.get("power_connectors", []) if v)
        available_connectors = set(str(v) for v in psu.get("gpu_power_connectors", []) if v)
        if required_connectors:
            if not available_connectors: unknowns.append("gpu_power_connectors")
            elif not required_connectors.issubset(available_connectors): failures.append(f"gpu_power_connectors: need {sorted(required_connectors)}, have {sorted(available_connectors)}")
        gpu_length, case_length = gpu.get("gpu_length_mm"), chassis.get("max_gpu_length_mm")
        if gpu_length is not None and case_length is not None and float(case_length) < float(gpu_length): failures.append(f"gpu_clearance: chassis {case_length}mm < GPU {gpu_length}mm")
        elif gpu_length is not None and case_length is None: unknowns.append("gpu_clearance")
        elif gpu_length is None: unknowns.append("exact_gpu_length")
        gpu_slots, case_slots = gpu.get("gpu_slots"), chassis.get("max_gpu_slots")
        if gpu_slots is not None and case_slots is not None and float(case_slots) < float(gpu_slots): failures.append(f"gpu_slot_width: chassis {case_slots} < GPU {gpu_slots}")
        elif gpu_slots is not None and case_slots is None: unknowns.append("gpu_slot_width")
        elif gpu_slots is None: unknowns.append("exact_gpu_slot_width")
        lane_req = int(gpu.get("minimum_pcie_lanes") or 0)
        lanes = board.get("gpu_slot_lanes")
        if lane_req and lanes is not None and int(lanes) < lane_req: failures.append(f"pcie_lanes: {lanes} < required {lane_req}")
        elif lane_req and lanes is None: unknowns.append("pcie_lanes")

    cooler_height, case_cooler = cooler.get("height_mm"), chassis.get("max_cpu_cooler_height_mm")
    if cooler_height is not None and case_cooler is not None and float(case_cooler) < float(cooler_height): failures.append(f"cooler_height: chassis {case_cooler}mm < cooler {cooler_height}mm")
    elif cooler_height is not None and case_cooler is None: unknowns.append("cooler_height")
    elif cooler_height is None: unknowns.append("exact_cooler_height")

    status = "incompatible" if failures else "compatible" if not unknowns else "provisionally_compatible"
    confidence = "high" if status == "compatible" else "medium" if status == "provisionally_compatible" and len(set(unknowns)) <= 2 else "low" if status == "provisionally_compatible" else "rejected"
    return {"status": status, "confidence": confidence, "failures": failures, "unknowns": sorted(set(unknowns))}


def construct_compatible_builds(components: dict[str, Any], *, gpu_part: dict[str, Any] | None = None, required_components: list[str] | None = None, max_candidates_per_component: int = 5, maximum_builds: int = 25, allow_provisional: bool = True) -> list[dict[str, Any]]:
    required = required_components or ["cpu_host", "motherboard", "host_ram_32gb", "storage_1tb", "psu_750w", "cooling", "chassis"]
    pools: list[list[dict[str, Any]]] = []
    for component in required:
        rows = list((components.get(component) or {}).get("candidates", []))[:max_candidates_per_component]
        if not rows: return []
        pools.append(rows)
    builds: list[dict[str, Any]] = []
    for combination in itertools.product(*pools):
        selected = {component: row for component, row in zip(required, combination, strict=True)}
        compatibility = evaluate_build_compatibility(selected, gpu_part)
        if compatibility["status"] == "incompatible": continue
        if compatibility["status"] == "provisionally_compatible" and not allow_provisional: continue
        component_cost = sum(float((row.get("landed") or {}).get("landed_cad") or 0.0) for row in selected.values())
        confidence_penalty = len(compatibility["unknowns"]) * 5.0
        builds.append({"components": selected, "compatibility": compatibility, "component_landed_cad": round(component_cost, 2), "ranking_cost_cad": round(component_cost + confidence_penalty, 2)})
    builds.sort(key=lambda row: (0 if row["compatibility"]["status"] == "compatible" else 1, row["ranking_cost_cad"], row["component_landed_cad"]))
    return builds[:maximum_builds]


def load_builds(path: Path | None = None) -> dict[str, Any]:
    target = path or project_root() / "data" / "market" / "compatible-builds.json"
    return _load(target, {"schema_version": 1, "gpus": {}})
