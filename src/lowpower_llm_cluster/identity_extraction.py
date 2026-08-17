# src/lowpower_llm_cluster/identity_extraction.py
from __future__ import annotations

import re
from typing import Any


def _set(cfg: dict[str, Any], key: str, value: Any) -> None:
    if value not in (None, "") and cfg.get(key) in (None, ""):
        cfg[key] = value


def _match(pattern: str, text: str, flags: int = re.I) -> str | None:
    found = re.search(pattern, text, flags)
    return found.group(1).strip() if found else None


def enrich_hardware_identity(text: str, *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract explicit identity facts from listing/spec text without guessing missing silicon."""
    cfg = dict(existing or {})
    normalized = " ".join(str(text or "").split())

    # Storage controller / NAND / interface.
    _set(cfg, "ssd_controller", _match(r"(?:controller|ssd controller|nvme controller)\s*[:#-]?\s*([A-Za-z0-9 ._-]{3,40})", normalized))
    nand = _match(r"\b((?:TLC|QLC|MLC|SLC)(?:\s+NAND)?)\b", normalized)
    if nand:
        _set(cfg, "nand_type", nand.upper())
    if re.search(r"\bNVMe\b", normalized, re.I):
        gen = _match(r"\bPCIe\s*(\d(?:\.0)?)\s*x?4\b", normalized)
        _set(cfg, "storage_interface", f"NVMe PCIe {gen} x4" if gen else "NVMe")

    # GPU board identity / VBIOS / revision.
    partner = _match(r"\b(ASUS|MSI|Gigabyte|AORUS|EVGA|Zotac|PNY|Sapphire|PowerColor|XFX|ASRock|Intel|NVIDIA)\b", normalized)
    _set(cfg, "board_partner", partner)
    _set(cfg, "gpu_board_revision", _match(r"(?:GPU\s+)?(?:PCB|board)\s*(?:rev(?:ision)?\.?)?\s*[:#-]?\s*([A-Za-z0-9._-]+)", normalized))
    _set(cfg, "vbios_version", _match(r"\bVBIOS(?:\s+version)?\s*[:#-]?\s*([A-Za-z0-9._-]+)", normalized))

    # RAM topology.
    modules = re.search(r"\b(\d+)\s*[x×]\s*(\d+)\s*GB\s*(DDR[345]|LPDDR\dX?)?\b", normalized, re.I)
    if modules:
        topology = dict(cfg.get("ram_topology") or {})
        topology.setdefault("module_count", int(modules.group(1)))
        topology.setdefault("module_capacity_gb", int(modules.group(2)))
        topology.setdefault("total_gb", int(modules.group(1)) * int(modules.group(2)))
        if modules.group(3):
            topology.setdefault("memory_type", modules.group(3).upper())
        cfg["ram_topology"] = topology
    channel = _match(r"\b(single|dual|triple|quad)[ -]?channel\b", normalized)
    if channel:
        topology = dict(cfg.get("ram_topology") or {})
        topology.setdefault("channels", {"single": 1, "dual": 2, "triple": 3, "quad": 4}[channel.casefold()])
        cfg["ram_topology"] = topology

    # Mobile exact model/SKU/SoC variants.
    _set(cfg, "device_sku", _match(r"\b(?:SKU|model number|model no\.?|part number)\s*[:#-]?\s*([A-Za-z0-9._/-]{3,40})", normalized))
    soc = _match(r"\b((?:Snapdragon|Dimensity|Tensor|Exynos|Apple)\s+[A-Za-z0-9+._ -]{2,30})\b", normalized)
    _set(cfg, "soc", soc)
    _set(cfg, "soc_variant", _match(r"\b(?:SoC|chip)\s+variant\s*[:#-]?\s*([A-Za-z0-9+._-]+)", normalized))

    # Host context for accelerator measurements/listings.
    _set(cfg, "host_cpu", _match(r"\b(?:host CPU|CPU)\s*[:#-]\s*([^,;|]{3,60})", normalized))
    _set(cfg, "host_motherboard", _match(r"\b(?:motherboard|mainboard)\s*[:#-]\s*([^,;|]{3,60})", normalized))
    _set(cfg, "host_psu", _match(r"\b(?:PSU|power supply)\s*[:#-]\s*([^,;|]{3,60})", normalized))
    host_ram = _match(r"\bhost RAM\s*[:#-]?\s*(\d+)\s*GB\b", normalized)
    if host_ram:
        _set(cfg, "host_ram_gb", int(host_ram))

    # Physical board provenance that may support vendor-published factory-firmware rules.
    _set(cfg, "serial_number", _match(r"\b(?:serial(?: number)?|S/N|SN)\s*[:#-]\s*([A-Za-z0-9._/-]{5,40})", normalized))
    _set(cfg, "manufacture_batch", _match(r"\b(?:manufacture|manufacturing|factory|production)\s*(?:batch|lot|code)\s*[:#-]?\s*([A-Za-z0-9._/-]{2,40})", normalized))
    _set(cfg, "factory_bios_label", _match(r"\b(?:factory|default|bios chip)\s*(?:BIOS|UEFI)?\s*(?:sticker|label|version)?\s*[:#-]\s*([A-Za-z0-9._-]{2,30})", normalized))

    return cfg


def extract_seller_firmware_evidence(text: str) -> dict[str, Any]:
    """Extract seller-stated board revision/current BIOS as lower-confidence evidence."""
    normalized = " ".join(str(text or "").split())
    revision = _match(r"\b(?:PCB|board|hardware)\s*(?:rev(?:ision)?\.?)\s*[:#-]?\s*([A-Za-z0-9._-]+)", normalized)
    bios = _match(r"\b(?:current|installed|running)\s+(?:BIOS|UEFI)(?:\s+version)?\s*[:#-]?\s*([A-Za-z0-9._-]+)", normalized)
    serial = _match(r"\b(?:serial(?: number)?|S/N|SN)\s*[:#-]\s*([A-Za-z0-9._/-]{5,40})", normalized)
    batch = _match(r"\b(?:manufacture|manufacturing|factory|production)\s*(?:batch|lot|code)\s*[:#-]?\s*([A-Za-z0-9._/-]{2,40})", normalized)
    factory_label = _match(r"\b(?:factory|default|bios chip)\s*(?:BIOS|UEFI)?\s*(?:sticker|label|version)?\s*[:#-]\s*([A-Za-z0-9._-]{2,30})", normalized)
    return {
        "board_revision": revision,
        "installed_bios_version": bios,
        "serial_number": serial,
        "manufacture_batch": batch,
        "factory_bios_label": factory_label,
        "source_type": "seller_listing_text",
        "confidence": "medium" if revision or bios or serial or batch or factory_label else "unknown",
    }


def extract_marketplace_condition_evidence(text: str) -> dict[str, Any]:
    """Preserve explicit used-hardware condition/warranty statements without inferring condition."""
    normalized = " ".join(str(text or "").split())
    applecare = _match(r"\b(AppleCare\+?(?:\s+(?:until|through|expires?|expiry)\s+[^,;|]{3,40})?)", normalized)
    warranty = _match(r"\b((?:manufacturer |remaining |seller )?warranty(?:\s+(?:until|through|expires?|expiry)\s+[^,;|]{3,40})?)", normalized)
    fan_note = _match(r"\b((?:GPU\s+)?fans?\s+(?:replaced|new|noisy|quiet|working|tested|failed|not working|damaged)[^,;|]{0,40})", normalized)
    cooler_note = _match(r"\b((?:GPU\s+)?cooler\s+(?:original|stock|replaced|new|damaged|modified|tested)[^,;|]{0,40})", normalized)
    return {
        "applecare_statement": applecare,
        "warranty_statement": warranty,
        "gpu_fan_statement": fan_note,
        "gpu_cooler_statement": cooler_note,
        "source_type": "seller_listing_text",
        "confidence": "medium" if any((applecare, warranty, fan_note, cooler_note)) else "unknown",
    }
