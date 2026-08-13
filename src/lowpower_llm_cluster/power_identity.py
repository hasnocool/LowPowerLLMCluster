from __future__ import annotations

import re
from typing import Any


def _norm(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return " ".join(str(value).casefold().replace("_", " ").replace("-", " ").split())


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if mapping.get(key) not in (None, ""):
            return mapping[key]
    return None


def _text(part: dict[str, Any]) -> str:
    cfg = part.get("configuration") or {}
    chunks = [part.get("name"), part.get("title"), part.get("description"), cfg.get("model"), cfg.get("soc"), cfg.get("chip")]
    return " ".join(str(v) for v in chunks if v)


def _ram_topology(part: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(part.get("configuration") or {})
    facts = dict(part.get("compatibility_facts") or {})
    topology = dict(cfg.get("ram_topology") or facts.get("ram_topology") or part.get("ram_topology") or {})
    text = _text(part)
    total = _first(topology, "total_gb") or part.get("memory_capacity_gb") or cfg.get("memory_capacity_gb") or facts.get("memory_capacity_gb")
    modules = _first(topology, "module_count", "modules")
    per_module = _first(topology, "module_capacity_gb", "capacity_per_module_gb")
    channels = _first(topology, "channels", "channel_count")
    memory_type = _first(topology, "memory_type") or cfg.get("memory_type") or facts.get("memory_type") or part.get("memory_type")
    if modules is None:
        match = re.search(r"\b(\d+)\s*[x×]\s*(\d+)\s*gb\b", text, re.I)
        if match:
            modules, per_module = int(match.group(1)), int(match.group(2))
            total = total or int(match.group(1)) * int(match.group(2))
    if channels is None:
        match = re.search(r"\b(single|dual|triple|quad)[ -]?channel\b", text, re.I)
        if match:
            channels = {"single": 1, "dual": 2, "triple": 3, "quad": 4}[match.group(1).casefold()]
    if memory_type is None:
        match = re.search(r"\b(LPDDR\dX?|DDR[345])\b", text, re.I)
        if match:
            memory_type = match.group(1).upper()
    return {k: v for k, v in {"total_gb": total, "module_count": modules, "module_capacity_gb": per_module, "channels": channels, "memory_type": memory_type}.items() if v not in (None, "")}


def enrich_power_identity(part: dict[str, Any]) -> dict[str, Any]:
    """Return a hardware fingerprint using only explicit catalog/listing/spec facts.

    Missing controller/NAND/revision/topology values remain missing; names are never
    converted into guessed silicon identities. Structured manufacturer compatibility
    facts are allowed to narrow identity when their field provenance has already been
    verified by the enrichment pipeline.
    """
    cfg = dict(part.get("configuration") or {})
    spec = dict(part.get("spec_enrichment") or {})
    facts = dict(part.get("compatibility_facts") or {})
    fields = dict(spec.get("facts") or {})
    category = _norm(part.get("category"))

    exact_id = _norm(_first(cfg, "apple_part_number", "model_identifier", "apple_a_number", "mpn", "device_sku") or _first(facts, "device_sku", "mpn") or _first(part, "mpn", "model_number", "sku"))
    model = _norm(_first(cfg, "soc", "chip", "model", "device_model") or _first(facts, "soc", "device_model") or part.get("name"))
    family = _norm(_first(part, "accelerator_family", "hardware_class") or _first(cfg, "soc_family", "soc") or _first(facts, "soc_family", "soc"))

    identity: dict[str, Any] = {
        "exact_id": exact_id,
        "model": model,
        "family": family,
        "category": category,
        "memory_gb": part.get("memory_capacity_gb") or cfg.get("memory_capacity_gb") or facts.get("memory_capacity_gb"),
        "storage_gb": cfg.get("storage_gb") or facts.get("storage_gb"),
    }

    identity.update({
        "apple_model_identifier": _norm(cfg.get("model_identifier") or facts.get("model_identifier")),
        "apple_a_number": _norm(cfg.get("apple_a_number") or facts.get("apple_a_number")),
        "apple_part_number": _norm(cfg.get("apple_part_number") or facts.get("apple_part_number")),
        "apple_soc": _norm(_first(cfg, "soc", "chip") or _first(facts, "soc", "chip")),
        "apple_gpu_cores": cfg.get("gpu_core_count_explicit") or cfg.get("gpu_core_count") or facts.get("gpu_core_count_explicit") or facts.get("gpu_core_count"),
        "screen_inches": cfg.get("screen_inches") or facts.get("screen_inches"),
    })

    identity.update({
        "storage_controller": _norm(_first(cfg, "ssd_controller", "storage_controller", "nvme_controller") or _first(fields, "ssd_controller", "storage_controller", "nvme_controller") or _first(facts, "ssd_controller", "storage_controller", "nvme_controller")),
        "nand_type": _norm(_first(cfg, "nand_type", "nand_flash", "flash_type") or _first(fields, "nand_type", "nand_flash", "flash_type") or _first(facts, "nand_type", "nand_flash", "flash_type")),
        "storage_interface": _norm(_first(cfg, "storage_interface") or _first(facts, "interface", "storage_interface")),
    })

    identity.update({
        "gpu_board_partner": _norm(_first(cfg, "board_partner", "gpu_board_partner", "manufacturer") or _first(facts, "board_partner", "gpu_board_partner") or part.get("manufacturer")),
        "gpu_board_mpn": _norm(_first(cfg, "gpu_mpn", "mpn") or _first(facts, "gpu_mpn", "mpn") or part.get("mpn")),
        "gpu_board_revision": _norm(_first(cfg, "board_revision", "gpu_board_revision", "pcb_revision") or _first(fields, "board_revision", "gpu_board_revision", "pcb_revision") or _first(facts, "board_revision", "gpu_board_revision", "pcb_revision")),
        "gpu_vbios": _norm(_first(cfg, "vbios", "vbios_version") or _first(facts, "vbios", "vbios_version")),
        "host_cpu": _norm(_first(cfg, "host_cpu", "cpu_model") or _first(facts, "host_cpu", "cpu_model")),
        "host_motherboard": _norm(_first(cfg, "host_motherboard", "motherboard_model") or _first(facts, "host_motherboard", "motherboard_model")),
        "host_psu": _norm(_first(cfg, "host_psu", "psu_model") or _first(facts, "host_psu", "psu_model")),
        "host_ram_gb": cfg.get("host_ram_gb") or facts.get("host_ram_gb"),
    })

    identity.update({
        "device_model": _norm(_first(cfg, "device_model", "model") or _first(facts, "device_model", "model")),
        "device_sku": _norm(_first(cfg, "device_sku", "sku") or _first(facts, "device_sku", "sku") or part.get("sku")),
        "mobile_soc": _norm(_first(cfg, "soc", "chip") or _first(facts, "soc", "chip")),
        "mobile_soc_variant": _norm(_first(cfg, "soc_variant", "chip_variant") or _first(facts, "soc_variant", "chip_variant")),
    })

    identity["ram_topology"] = _ram_topology(part)
    return {key: value for key, value in identity.items() if value not in (None, "", {})}


def identity_specificity(identity: dict[str, Any]) -> int:
    """Return a stable specificity score used to choose the narrowest distribution."""
    weighted = {
        "exact_id": 40,
        "apple_model_identifier": 30,
        "apple_part_number": 30,
        "device_sku": 28,
        "gpu_board_mpn": 28,
        "gpu_board_revision": 16,
        "storage_controller": 18,
        "nand_type": 14,
        "host_cpu": 10,
        "host_motherboard": 10,
        "host_psu": 6,
        "ram_topology": 12,
        "model": 12,
        "family": 6,
        "category": 1,
    }
    return sum(weight for key, weight in weighted.items() if identity.get(key) not in (None, "", {}))
