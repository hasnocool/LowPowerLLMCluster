# src/lowpower_llm_cluster/structured_identity.py
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .catalog import project_root


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("_", " ").replace("-", " ").split())


def _set(out: dict[str, Any], key: str, value: Any) -> None:
    if value not in (None, "", [], {}) and out.get(key) in (None, "", [], {}):
        out[key] = value


def load_vendor_parameter_mappings(path: Path | None = None) -> dict[str, Any]:
    target = path or project_root() / "data" / "identity" / "vendor-parameter-mappings.json"
    if not target.exists():
        return {"schema_version": 1, "generic": {}, "vendors": {}}
    return json.loads(target.read_text(encoding="utf-8"))


def _pairs_from_mapping(value: Any) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(value, list):
        for row in value:
            out.extend(_pairs_from_mapping(row))
        return out
    if not isinstance(value, dict):
        return out

    name = value.get("name") or value.get("Name") or value.get("propertyID") or value.get("Parameter") or value.get("ParameterText")
    raw = value.get("value") or value.get("Value") or value.get("ValueText") or value.get("ParameterValue") or value.get("DisplayValue")
    if isinstance(raw, dict):
        raw = raw.get("name") or raw.get("value") or raw.get("Value")
    if name not in (None, "") and raw not in (None, ""):
        out.append((str(name), str(raw)))

    for key in ("additionalProperty", "AdditionalProperty", "Parameters", "parameters", "ProductAttributes", "productAttributes", "Specifications", "specifications"):
        child = value.get(key)
        if child is not None:
            out.extend(_pairs_from_mapping(child))
    return out


def structured_property_pairs(*values: Any) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for value in values:
        pairs.extend(_pairs_from_mapping(value))
    dedup: dict[tuple[str, str], tuple[str, str]] = {}
    for key, val in pairs:
        dedup[(_norm(key), _norm(val))] = (key, val)
    return list(dedup.values())


def _alias_field(label: str, existing: dict[str, Any], mappings: dict[str, Any]) -> str | None:
    manufacturer = _norm(existing.get("manufacturer"))
    groups = [dict(mappings.get("generic") or {})]
    for vendor, fields in (mappings.get("vendors") or {}).items():
        if manufacturer and _norm(vendor) in manufacturer:
            groups.insert(0, dict(fields or {}))
    for group in groups:
        for field, aliases in group.items():
            if any(_norm(alias) == label or _norm(alias) in label for alias in aliases or []):
                return str(field)
    return None


def extract_structured_identity(
    pairs: Iterable[tuple[str, str]],
    *,
    existing: dict[str, Any] | None = None,
    mappings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract explicit hardware identity from structured manufacturer/distributor properties.

    Vendor aliases only map an explicitly supplied field label to a normalized identity
    key. They never supply or infer the value itself.
    """
    out = dict(existing or {})
    topology = dict(out.get("ram_topology") or {})
    registry = mappings or load_vendor_parameter_mappings()

    for raw_key, raw_value in pairs:
        label = _norm(raw_key)
        value = " ".join(str(raw_value or "").split())
        lower = _norm(value)
        if not label or not value:
            continue
        alias = _alias_field(label, out, registry)

        if alias == "ssd_controller" or (any(term in label for term in ("ssd controller", "nvme controller", "storage controller", "controller")) and not any(term in label for term in ("fan controller", "rgb controller"))):
            _set(out, "ssd_controller", value)
        if alias == "nand_type" or any(term in label for term in ("nand", "flash type", "flash memory", "nand type")):
            _set(out, "nand_type", value)
        if alias == "storage_interface" or (any(term in label for term in ("storage interface", "interface", "bus type")) and any(term in lower for term in ("nvme", "pcie", "sata"))):
            _set(out, "storage_interface", value)

        if alias in {"gpu_board_revision", "board_revision"} or any(term in label for term in ("pcb revision", "board revision", "hardware revision")):
            _set(out, "gpu_board_revision", value)
            _set(out, "board_revision", value)
        if alias == "vbios_version" or "vbios" in label or "video bios" in label:
            _set(out, "vbios_version", value)
        if alias == "board_partner" or any(term in label for term in ("board partner", "graphics manufacturer", "gpu manufacturer")):
            _set(out, "board_partner", value)

        if alias == "ram_configuration" or any(term in label for term in ("module configuration", "memory configuration", "dimm configuration", "memory kit")):
            match = re.search(r"\b(\d+)\s*[x×]\s*(\d+)\s*GB\b", value, re.I)
            if match:
                topology.setdefault("module_count", int(match.group(1)))
                topology.setdefault("module_capacity_gb", int(match.group(2)))
                topology.setdefault("total_gb", int(match.group(1)) * int(match.group(2)))
        if alias == "ram_module_count" or any(term in label for term in ("number of modules", "module count", "dimm count")):
            match = re.search(r"\d+", value)
            if match:
                topology.setdefault("module_count", int(match.group(0)))
        if alias == "ram_module_capacity" or any(term in label for term in ("capacity per module", "module capacity")):
            match = re.search(r"(\d+)\s*GB", value, re.I)
            if match:
                topology.setdefault("module_capacity_gb", int(match.group(1)))
        if alias == "ram_channels" or any(term in label for term in ("channel", "memory channel")):
            for name, channels in (("single", 1), ("dual", 2), ("triple", 3), ("quad", 4)):
                if name in lower:
                    topology.setdefault("channels", channels)
                    break
        if alias == "memory_type" or any(term in label for term in ("memory type", "dram type", "ram type")):
            match = re.search(r"\b(LPDDR\dX?|DDR[345])\b", value, re.I)
            if match:
                topology.setdefault("memory_type", match.group(1).upper())
                _set(out, "memory_type", match.group(1).upper())

        if alias == "device_sku" or any(term in label for term in ("device sku", "model number", "part number", "device model")):
            _set(out, "device_sku", value)
        if alias == "soc" or label in {"soc", "system on chip", "chipset", "processor soc"} or "soc model" in label:
            _set(out, "soc", value)
        if alias == "soc_variant" or any(term in label for term in ("soc variant", "chip variant", "processor variant")):
            _set(out, "soc_variant", value)

        if alias == "host_cpu" or any(term in label for term in ("host cpu", "test cpu")):
            _set(out, "host_cpu", value)
        if alias == "host_motherboard" or any(term in label for term in ("host motherboard", "test motherboard", "mainboard")):
            _set(out, "host_motherboard", value)
        if alias == "host_psu" or any(term in label for term in ("host psu", "test psu", "power supply model")):
            _set(out, "host_psu", value)
        if alias == "host_ram_gb" or any(term in label for term in ("host ram", "system memory")):
            match = re.search(r"(\d+)\s*GB", value, re.I)
            if match:
                _set(out, "host_ram_gb", int(match.group(1)))

    if topology:
        out["ram_topology"] = topology
    return out
