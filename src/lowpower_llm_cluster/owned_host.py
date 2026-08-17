# src/lowpower_llm_cluster/owned_host.py
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable, Mapping

from .compatibility import gpu_requirements


@dataclass(frozen=True, slots=True)
class OwnedHostValidation:
    """Compatibility result for installing an accelerator into hardware already owned."""

    status: str
    confidence: str
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    unknowns: tuple[str, ...]
    selected_pcie_slot: dict[str, Any] | None
    gpu_requirement_basis: str
    cooling_power_basis: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _connector_name(value: str) -> str:
    normalized = " ".join(str(value).strip().casefold().replace("_", " ").split())
    normalized = normalized.replace("12v 2x6", "12v-2x6").replace("12vhpwr", "12vhpwr")
    normalized = normalized.replace("6+2 pin", "8-pin").replace("6+2-pin", "8-pin")
    normalized = re.sub(r"\s*[- ]?pin\b", "-pin", normalized)
    return normalized


def _connector_counter(values: Any) -> Counter[str]:
    if values in (None, ""):
        return Counter()
    if isinstance(values, Mapping):
        return Counter({_connector_name(str(key)): int(count) for key, count in values.items() if int(count) > 0})
    if isinstance(values, str):
        values = [values]
    out: Counter[str] = Counter()
    for raw in values:
        text = str(raw).strip()
        match = re.match(r"^(\d+)\s*[x×]\s*(.+)$", text, re.IGNORECASE)
        if match:
            out[_connector_name(match.group(2))] += int(match.group(1))
        else:
            out[_connector_name(text)] += 1
    return out


def _slot_physical_lanes(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"x\s*(\d+)", str(value), re.IGNORECASE)
    return int(match.group(1)) if match else None


def _available_slots(host: Mapping[str, Any]) -> list[dict[str, Any]]:
    slots = host.get("pcie_slots")
    if isinstance(slots, Iterable) and not isinstance(slots, (str, bytes, Mapping)):
        normalized: list[dict[str, Any]] = []
        for index, raw in enumerate(slots):
            if not isinstance(raw, Mapping):
                continue
            normalized.append(
                {
                    "id": str(raw.get("id") or f"slot-{index + 1}"),
                    "physical_lanes": _slot_physical_lanes(raw.get("physical_lanes") or raw.get("physical") or raw.get("slot")),
                    "wired_lanes": _slot_physical_lanes(raw.get("wired_lanes") or raw.get("lanes")),
                    "generation": int(raw["generation"]) if raw.get("generation") is not None else None,
                    "available": bool(raw.get("available", not raw.get("occupied", False))),
                }
            )
        return normalized

    physical = _slot_physical_lanes(host.get("pcie_physical_slot") or host.get("pcie_slot"))
    if physical is None and host.get("pcie_gpu_slot_present") is True:
        physical = 16
    if physical is None:
        return []
    return [
        {
            "id": "gpu-slot",
            "physical_lanes": physical,
            "wired_lanes": _slot_physical_lanes(host.get("pcie_gpu_slot_lanes") or host.get("pcie_lanes")),
            "generation": int(host["pcie_generation"]) if host.get("pcie_generation") is not None else None,
            "available": bool(host.get("pcie_gpu_slot_available", True)),
        }
    ]


def _board_power_w(gpu_part: Mapping[str, Any], exact_facts: Mapping[str, Any] | None) -> tuple[float | None, str | None]:
    for source, values in (("exact_sku_manufacturer_spec", exact_facts or {}), ("catalog_board_power", gpu_part)):
        for key in ("board_power_w", "tgp_w", "tbp_w", "default_tgp_w", "default_tbp_w"):
            value = values.get(key)
            if value is not None:
                return float(value), source
    return None, None


def _choose_slot(slots: list[dict[str, Any]], *, physical_lanes: int, wired_lanes: int, generation: int) -> dict[str, Any] | None:
    available = [slot for slot in slots if slot.get("available", True)]
    if not available:
        return None

    def score(slot: dict[str, Any]) -> tuple[int, int, int]:
        physical = int(slot.get("physical_lanes") or 0)
        wired = int(slot.get("wired_lanes") or 0)
        gen = int(slot.get("generation") or 0)
        satisfies = int(physical >= physical_lanes and (not wired_lanes or wired >= wired_lanes) and (not generation or gen >= generation))
        return satisfies, wired, gen

    return max(available, key=score)


def validate_owned_host(
    gpu_part: Mapping[str, Any],
    host_facts: Mapping[str, Any],
    *,
    exact_gpu_facts: Mapping[str, Any] | None = None,
    minimum_psu_headroom_w: float = 100.0,
) -> OwnedHostValidation:
    """Validate an already-owned host without assuming missing compatibility facts.

    `minimum_psu_headroom_w` is used only when the caller supplies an estimated complete-system
    peak in `host_facts`. GPU TGP/TBP is never relabeled as complete-system power.
    """
    if minimum_psu_headroom_w < 0:
        raise ValueError("minimum_psu_headroom_w cannot be negative")

    failures: list[str] = []
    warnings: list[str] = []
    unknowns: list[str] = []
    requirements = gpu_requirements(dict(gpu_part), dict(exact_gpu_facts or {}))

    required_physical = _slot_physical_lanes(requirements.get("pcie_slot")) or 16
    required_lanes = int(requirements.get("minimum_pcie_lanes") or 0)
    required_generation = int(requirements.get("minimum_pcie_generation") or 0)
    slots = _available_slots(host_facts)
    selected = _choose_slot(slots, physical_lanes=required_physical, wired_lanes=required_lanes, generation=required_generation)
    if not slots:
        unknowns.append("pcie_physical_slot")
    elif selected is None:
        failures.append("pcie_slot: no unoccupied PCIe slot is available")
    else:
        physical = selected.get("physical_lanes")
        if physical is None:
            unknowns.append("pcie_physical_slot")
        elif int(physical) < required_physical:
            failures.append(f"pcie_physical_slot: x{physical} < required physical x{required_physical}")
        wired = selected.get("wired_lanes")
        if required_lanes and wired is None:
            unknowns.append("pcie_lanes")
        elif required_lanes and int(wired) < required_lanes:
            failures.append(f"pcie_lanes: x{wired} < required x{required_lanes}")
        generation = selected.get("generation")
        if required_generation and generation is None:
            unknowns.append("pcie_generation")
        elif required_generation and int(generation) < required_generation:
            failures.append(f"pcie_generation: Gen{generation} < required Gen{required_generation}")

    minimum_psu_w = requirements.get("minimum_psu_w")
    psu_w = host_facts.get("psu_wattage_w")
    if minimum_psu_w is not None and psu_w is None:
        unknowns.append("psu_wattage")
    elif minimum_psu_w is not None and float(psu_w) < float(minimum_psu_w):
        failures.append(f"psu_wattage: {psu_w}W < manufacturer/planning requirement {minimum_psu_w}W")

    peak_w = host_facts.get("estimated_peak_system_w")
    if psu_w is None or peak_w is None:
        unknowns.append("psu_headroom")
    else:
        headroom = float(psu_w) - float(peak_w)
        if headroom < minimum_psu_headroom_w:
            failures.append(f"psu_headroom: {headroom:.0f}W < required planning reserve {minimum_psu_headroom_w:.0f}W")
        else:
            warnings.append(f"psu_headroom: {headroom:.0f}W based on caller-supplied complete-system peak estimate")

    required_connectors = _connector_counter(requirements.get("power_connectors"))
    available_connectors = _connector_counter(host_facts.get("psu_gpu_power_connectors"))
    if required_connectors:
        if not available_connectors:
            unknowns.append("gpu_power_connectors")
        else:
            missing = required_connectors - available_connectors
            if missing:
                failures.append(f"gpu_power_connectors: missing {dict(missing)}; available {dict(available_connectors)}")

    gpu_length = requirements.get("gpu_length_mm")
    max_length = host_facts.get("chassis_max_gpu_length_mm")
    if gpu_length is None:
        unknowns.append("exact_gpu_length")
    elif max_length is None:
        unknowns.append("gpu_clearance")
    elif float(max_length) < float(gpu_length):
        failures.append(f"gpu_clearance: chassis {max_length}mm < GPU {gpu_length}mm")

    gpu_slots = requirements.get("gpu_slots")
    max_slots = host_facts.get("chassis_max_gpu_slots")
    if gpu_slots is None:
        unknowns.append("exact_gpu_slot_width")
    elif max_slots is None:
        unknowns.append("gpu_slot_width")
    elif float(max_slots) < float(gpu_slots):
        failures.append(f"gpu_slot_width: chassis {max_slots} slots < GPU {gpu_slots} slots")

    board_power, cooling_basis = _board_power_w(gpu_part, exact_gpu_facts)
    cooling_capacity = host_facts.get("gpu_cooling_capacity_w")
    if board_power is None or cooling_capacity is None:
        unknowns.append("gpu_cooling_capacity")
    elif float(cooling_capacity) < board_power:
        failures.append(f"gpu_cooling_capacity: {cooling_capacity}W < board-power planning load {board_power:.0f}W")
    else:
        warnings.append(
            f"cooling check uses {board_power:.0f}W accelerator-board power only; it is not complete-node wall input"
        )

    failures = sorted(set(failures))
    unknowns = sorted(set(unknowns))
    warnings = sorted(set(warnings))
    status = "incompatible" if failures else "compatible" if not unknowns else "provisionally_compatible"
    confidence = (
        "rejected"
        if status == "incompatible"
        else "high"
        if status == "compatible"
        else "medium"
        if len(unknowns) <= 2
        else "low"
    )
    return OwnedHostValidation(
        status=status,
        confidence=confidence,
        failures=tuple(failures),
        warnings=tuple(warnings),
        unknowns=tuple(unknowns),
        selected_pcie_slot=selected,
        gpu_requirement_basis="exact_sku_manufacturer_spec" if exact_gpu_facts else "catalog_reference",
        cooling_power_basis=cooling_basis,
    )
