# tests/test_identity_extraction.py
from __future__ import annotations

from lowpower_llm_cluster.identity_extraction import enrich_hardware_identity, extract_seller_firmware_evidence
from lowpower_llm_cluster.market import Listing


def test_extracts_storage_controller_nand_and_interface():
    cfg = enrich_hardware_identity("1TB NVMe PCIe 4.0 x4 SSD controller: Phison E18 TLC NAND")
    assert "phison e18" in cfg["ssd_controller"].casefold()
    assert cfg["nand_type"] == "TLC NAND"
    assert cfg["storage_interface"] == "NVMe PCIe 4.0 x4"


def test_extracts_gpu_board_vbios_and_host_context():
    cfg = enrich_hardware_identity("MSI RTX 3090 PCB Rev B1 VBIOS 94.02.42.00.F0 CPU: Ryzen 5 5600 motherboard: B550-A PRO PSU: RM750e host RAM: 32GB")
    assert cfg["board_partner"] == "MSI"
    assert cfg["gpu_board_revision"] == "B1"
    assert cfg["vbios_version"] == "94.02.42.00.F0"
    assert "Ryzen 5 5600" in cfg["host_cpu"]
    assert cfg["host_ram_gb"] == 32


def test_extracts_ram_topology_and_mobile_soc():
    cfg = enrich_hardware_identity("2x16GB DDR5 dual-channel Pixel model number G4QUR Snapdragon 8 Elite")
    assert cfg["ram_topology"]["module_count"] == 2
    assert cfg["ram_topology"]["channels"] == 2
    assert cfg["device_sku"] == "G4QUR"
    assert "snapdragon 8 elite" in cfg["soc"].casefold()


def test_marketplace_listing_captures_seller_firmware_evidence():
    listing = Listing(source="fixture", source_id="1", url="https://example.test", title="B550 board PCB Rev 1.2 installed BIOS F14", price=50, currency="CAD", observed_at="2026-08-11T00:00:00Z", source_kind="structured_marketplace")
    evidence = listing.configuration["seller_firmware_evidence"]
    assert evidence["board_revision"] == "1.2"
    assert evidence["installed_bios_version"] == "F14"
    assert evidence["source_type"] == "seller_listing_text"


def test_seller_firmware_is_not_manufacturer_authority():
    evidence = extract_seller_firmware_evidence("PCB Rev 1.1 current BIOS A9")
    assert evidence["confidence"] == "medium"
    assert evidence["source_type"] == "seller_listing_text"
