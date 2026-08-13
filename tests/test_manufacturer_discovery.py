from __future__ import annotations

from datetime import UTC, datetime

from lowpower_llm_cluster.manufacturer_discovery import association_cache_key, cached_association
from lowpower_llm_cluster.spec_enrichment import extract_automatic_spec_fields


def config() -> dict:
    return {
        "policy": {"cache_ttl_days": 30},
        "manufacturers": [
            {"name": "Corsair", "aliases": ["Corsair Components"], "domains": ["corsair.com"]},
            {"name": "MSI", "aliases": ["Micro-Star International"], "domains": ["msi.com"]},
        ],
    }


def test_verified_cached_association_is_reused():
    listing = {"title": "Corsair RM750e ATX PSU", "sku": "CP-9020295-NA", "configuration": {"manufacturer": "Corsair", "mpn": "CP-9020295-NA"}}
    key = association_cache_key("psu_750w", "Corsair", "CP-9020295-NA", listing["title"])
    cache = {"associations": {key: {"status": "verified", "source_url": "https://www.corsair.com/example", "verified_at": datetime.now(UTC).isoformat()}}}
    hit = cached_association("psu_750w", listing, config(), cache)
    assert hit is not None
    assert hit["source_url"].startswith("https://www.corsair.com/")


def test_automatic_psu_parser_extracts_power_and_connectors():
    text = "RM750e Total Power 750 W. ATX 3.1. Native 12V-2x6 connector supports 600 W. PCIe 6+2 connectors included."
    facts, evidence = extract_automatic_spec_fields("psu_750w", text, "https://www.corsair.com/rm750e", "2026-08-11T00:00:00+00:00", "auto:Corsair:CP-9020295-NA", 0.95)
    assert facts["wattage_w"] == 750
    assert facts["atx_standard"] == "ATX 3.1"
    assert "12V-2x6" in facts["gpu_power_connectors"]
    assert facts["native_12v2x6_w"] == 600
    assert evidence["wattage_w"]["source_type"] == "manufacturer_spec"
    assert evidence["wattage_w"]["extraction"] == "automatic_manufacturer_page_parser"


def test_automatic_chassis_parser_extracts_clearance():
    text = "Maximum GPU Length 360 mm. Maximum CPU Cooler Height 170 mm. Maximum PSU Length 220 mm. Supports ATX, Micro-ATX and Mini-ITX. Expansion Slots 7."
    facts, _ = extract_automatic_spec_fields("chassis", text, "https://www.corsair.com/case", "2026-08-11T00:00:00+00:00", "auto:Corsair:CASE", 0.88)
    assert facts["max_gpu_length_mm"] == 360
    assert facts["max_cpu_cooler_height_mm"] == 170
    assert facts["max_psu_length_mm"] == 220
    assert "ATX" in facts["motherboard_form_factors"]
    assert "mATX" in facts["motherboard_form_factors"]
    assert facts["max_gpu_slots"] == 7


def test_automatic_motherboard_parser_keeps_lane_sharing_note():
    text = "B550 AM4 DDR4 ATX motherboard. PCIe 4.0 x16. Two M.2 slots. PCI_E3 is unavailable when a PCIe SSD is installed in M2_2."
    facts, _ = extract_automatic_spec_fields("motherboard", text, "https://www.msi.com/board", "2026-08-11T00:00:00+00:00", "auto:MSI:B550", 0.9)
    assert facts["socket"] == "AM4"
    assert facts["memory_type"] == "DDR4"
    assert facts["gpu_slot"] == "PCIe x16"
    assert facts["pcie_generation"] == 4
    assert facts["supports_nvme_m2"] is True
    assert "unavailable" in facts["lane_sharing_note"].casefold()


def test_automatic_gpu_parser_can_prove_physical_requirements():
    text = "Card Length 313 mm. Slot Width 3 slots. Recommended System Power 750 W. PCIe 4.0 x16. One 8-pin power connector."
    facts, _ = extract_automatic_spec_fields("gpu_accelerator", text, "https://www.nvidia.com/gpu", "2026-08-11T00:00:00+00:00", "auto:NVIDIA:GPU", 0.94)
    assert facts["gpu_length_mm"] == 313
    assert facts["gpu_slots"] == 3
    assert facts["minimum_psu_w"] == 750
    assert facts["minimum_pcie_lanes"] == 16
    assert "8-pin" in facts["power_connectors"]
