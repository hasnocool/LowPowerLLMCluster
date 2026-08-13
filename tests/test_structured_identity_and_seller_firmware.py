# tests/test_structured_identity_and_seller_firmware.py
from __future__ import annotations

from lowpower_llm_cluster.firmware_readiness import boot_readiness_score
from lowpower_llm_cluster.power_identity import enrich_power_identity
from lowpower_llm_cluster.seller_firmware import correlate_seller_firmware
from lowpower_llm_cluster.structured_identity import extract_structured_identity, structured_property_pairs


def test_structured_properties_extract_storage_gpu_ram_mobile_and_host_identity() -> None:
    pairs = [
        ("SSD Controller", "Phison E18"),
        ("NAND Type", "Micron 176L TLC"),
        ("Storage Interface", "NVMe PCIe 4.0 x4"),
        ("PCB Revision", "B1"),
        ("VBIOS Version", "94.02.42.00.F0"),
        ("Memory Configuration", "2x16GB DDR5"),
        ("Memory Channels", "Dual Channel"),
        ("Device SKU", "SM-S948W"),
        ("SoC", "Snapdragon 8 Elite Gen 5"),
        ("SoC Variant", "for Galaxy"),
        ("Host CPU", "Ryzen 5 5600"),
        ("Host Motherboard", "MSI B550-A PRO"),
        ("Host PSU", "Corsair RM750e"),
        ("Host RAM", "32GB"),
    ]
    cfg = extract_structured_identity(pairs)
    assert cfg["ssd_controller"] == "Phison E18"
    assert cfg["nand_type"] == "Micron 176L TLC"
    assert cfg["gpu_board_revision"] == "B1"
    assert cfg["vbios_version"] == "94.02.42.00.F0"
    assert cfg["ram_topology"]["module_count"] == 2
    assert cfg["ram_topology"]["channels"] == 2
    assert cfg["device_sku"] == "SM-S948W"
    assert cfg["soc_variant"] == "for Galaxy"
    assert cfg["host_ram_gb"] == 32


def test_structured_property_pairs_handle_jsonld_and_distributor_parameter_shapes() -> None:
    jsonld = {
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "SSD Controller", "value": "Phison E18"},
            {"@type": "PropertyValue", "name": "NAND Type", "value": "TLC NAND"},
        ]
    }
    digikey = {
        "Parameters": [
            {"ParameterText": "Memory Configuration", "ValueText": "2x16GB DDR5"},
            {"ParameterText": "Memory Channels", "ValueText": "Dual Channel"},
        ]
    }
    pairs = structured_property_pairs(jsonld, digikey)
    cfg = extract_structured_identity(pairs)
    assert cfg["ssd_controller"] == "Phison E18"
    assert cfg["nand_type"] == "TLC NAND"
    assert cfg["ram_topology"]["total_gb"] == 32
    assert cfg["ram_topology"]["channels"] == 2


def test_power_identity_consumes_verified_structured_facts() -> None:
    part = {
        "name": "Exact SSD",
        "category": "storage",
        "compatibility_facts": {
            "ssd_controller": "Phison E18",
            "nand_type": "Micron 176L TLC",
            "storage_interface": "NVMe PCIe 4.0 x4",
            "ram_topology": {"module_count": 2, "module_capacity_gb": 16, "total_gb": 32, "channels": 2, "memory_type": "DDR5"},
        },
    }
    identity = enrich_power_identity(part)
    assert identity["storage_controller"] == "phison e18"
    assert identity["nand_type"] == "micron 176l tlc"
    assert identity["ram_topology"]["module_count"] == 2


def test_seller_installed_bios_is_correlated_with_revision_scoped_history() -> None:
    cpu_bios = {
        "status": "supported",
        "minimum_bios_version": "F12",
        "source_url": "https://www.gigabyte.com/Motherboard/example/support",
    }
    seller = {
        "board_revision": "1.2",
        "installed_bios_version": "F14",
        "source_type": "seller_listing_text",
        "confidence": "medium",
    }
    history = [
        {
            "version": "F14",
            "release_date": "2026-01-01",
            "board_revisions": ["1.2"],
            "source_url": "https://www.gigabyte.com/api/bios",
            "source_type": "manufacturer_revision_scoped_bios_history",
        }
    ]
    result = correlate_seller_firmware(cpu_bios, seller, history)
    assert result["meets_minimum"] is True
    assert result["installed_bios_in_revision_history"] is True
    assert result["confidence"] == "high"
    assert result["manufacturer_authority"] is False


def test_boot_readiness_uses_correlated_seller_firmware_below_factory_authority() -> None:
    cpu_bios = {
        "status": "supported",
        "minimum_bios_version": "F12",
        "source_url": "https://www.gigabyte.com/Motherboard/example/support",
        "matrix_complete": True,
    }
    flashback = {
        "status": "unknown",
        "cpu_less_update_explicit": None,
        "seller_firmware_evidence": {
            "board_revision": "1.2",
            "installed_bios_version": "F14",
            "source_type": "seller_listing_text",
            "confidence": "medium",
        },
        "revision_bios_history": [
            {
                "version": "F14",
                "release_date": "2026-01-01",
                "board_revisions": ["1.2"],
                "source_url": "https://www.gigabyte.com/api/bios",
            }
        ],
    }
    result = boot_readiness_score(cpu_bios, flashback)
    assert result["readiness"] == "ready_by_correlated_seller_installed_firmware"
    assert result["score"] == 94
    assert result["seller_firmware"]["installed_bios_in_revision_history"] is True
    assert result["performance_claim"] is False
