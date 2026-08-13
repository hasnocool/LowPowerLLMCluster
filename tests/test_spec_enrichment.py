from __future__ import annotations

from lowpower_llm_cluster.compatibility import evaluate_build_compatibility
from lowpower_llm_cluster.spec_enrichment import associate_spec_source, extract_spec_fields


def candidate_facts() -> dict:
    motherboard = {
        "compatibility_facts": {"socket": "AM4", "memory_type": "DDR4", "gpu_slot": "PCIe x16", "gpu_slot_lanes": 16, "pcie_generation": 4, "form_factors": ["ATX"], "supports_nvme_m2": True},
        "spec_enrichment": {
            "structured_document": {
                "cpu_support_matrix": [{"cpu_model": "Ryzen 5 5600", "minimum_bios_version": "7C56vA9", "support_status": "supported", "source_type": "manufacturer_support_table"}],
                "cpu_support_matrix_complete": False,
            }
        },
    }
    return {
        "cpu_host": {"compatibility_facts": {"socket": "AM4", "memory_types": ["DDR4"], "cpu_model": "Ryzen 5 5600"}, "listing": {"title": "AMD Ryzen 5 5600"}},
        "motherboard": motherboard,
        "host_ram_32gb": {"compatibility_facts": {"memory_type": "DDR4"}},
        "storage_1tb": {"compatibility_facts": {"interface": "NVMe"}},
        "psu_750w": {"compatibility_facts": {"wattage_w": 750, "gpu_power_connectors": ["8-pin", "12V-2x6"]}},
        "cooling": {"compatibility_facts": {"supported_sockets": ["AM4"], "height_mm": 155}},
        "chassis": {"compatibility_facts": {"motherboard_form_factors": ["ATX"], "max_gpu_length_mm": 360, "max_gpu_slots": 4, "max_cpu_cooler_height_mm": 170}},
    }


def test_exact_sku_association_beats_title_only_match():
    config = {"associations": [
        {"id": "generic", "component": "psu_750w", "match_terms": ["rm750e"]},
        {"id": "exact", "component": "psu_750w", "exact_skus": ["CP-9020295-NA"], "match_terms": ["rm750e"]},
    ]}
    listing = {"title": "Corsair RM750e", "sku": "CP-9020295-NA"}
    assert associate_spec_source("psu_750w", listing, config)["id"] == "exact"


def test_extracted_manufacturer_fields_have_field_level_provenance():
    association = {
        "id": "case",
        "exact_skus": ["CASE-1"],
        "fields": {
            "max_gpu_length_mm": {"regex": r"Maximum GPU Length\s*(\d+)mm", "cast": "int"},
            "max_cpu_cooler_height_mm": {"constant": 170},
        },
    }
    facts, evidence = extract_spec_fields("Maximum GPU Length 360mm", association, "https://manufacturer.test/spec", "2026-08-11T00:00:00+00:00")
    assert facts["max_gpu_length_mm"] == 360
    assert facts["max_cpu_cooler_height_mm"] == 170
    assert evidence["max_gpu_length_mm"]["source_type"] == "manufacturer_spec"
    assert evidence["max_cpu_cooler_height_mm"]["confidence"] == "exact"


def test_exact_gpu_specs_can_promote_provisional_build():
    build = candidate_facts()
    gpu_part = {"category": "gpu_accelerator", "host_requirements": "PCIe 4.0 x16 host; 750W required system power"}
    before = evaluate_build_compatibility(build, gpu_part)
    assert before["status"] == "provisionally_compatible"
    exact = {"gpu_length_mm": 313, "gpu_slots": 3, "minimum_psu_w": 750, "power_connectors": ["8-pin"], "minimum_pcie_generation": 4, "minimum_pcie_lanes": 16}
    after = evaluate_build_compatibility(build, gpu_part, exact)
    assert after["status"] == "compatible"
    assert after["gpu_requirement_basis"] == "exact_sku_manufacturer_spec"


def test_exact_gpu_specs_can_reject_physically_too_large_card():
    build = candidate_facts()
    build["chassis"]["compatibility_facts"]["max_gpu_length_mm"] = 300
    gpu_part = {"category": "gpu_accelerator", "host_requirements": "PCIe 4.0 x16 host; 750W required system power"}
    exact = {"gpu_length_mm": 313, "gpu_slots": 3, "minimum_psu_w": 750, "power_connectors": ["8-pin"], "minimum_pcie_generation": 4, "minimum_pcie_lanes": 16}
    result = evaluate_build_compatibility(build, gpu_part, exact)
    assert result["status"] == "incompatible"
    assert any("gpu_clearance" in failure for failure in result["failures"])


def test_exact_gpu_specs_can_reject_underpowered_psu():
    build = candidate_facts()
    build["psu_750w"]["compatibility_facts"]["wattage_w"] = 650
    gpu_part = {"category": "gpu_accelerator"}
    exact = {"gpu_length_mm": 272, "gpu_slots": 2, "minimum_psu_w": 750, "power_connectors": ["8-pin"]}
    result = evaluate_build_compatibility(build, gpu_part, exact)
    assert result["status"] == "incompatible"
    assert any("psu_wattage" in failure for failure in result["failures"])
