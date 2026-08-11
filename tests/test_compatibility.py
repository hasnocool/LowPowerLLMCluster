from __future__ import annotations

from lowpower_llm_cluster.compatibility import construct_compatible_builds, evaluate_build_compatibility, evaluate_cpu_bios_pair, gpu_requirements, infer_listing_facts


def row(component: str, facts: dict, cost: float = 100.0, title: str | None = None):
    return {"component": component, "compatibility_facts": facts, "landed": {"landed_cad": cost}, "listing": {"title": title or component}}


def gpu():
    return {
        "id": "gpu",
        "category": "gpu_accelerator",
        "name": "Test GPU",
        "host_requirements": "PCIe 4.0 x16-class host; reference card power 350W; 750W required system power.",
        "length_mm": 313,
        "slot_width": 3,
    }


def compatible_build():
    cpu = row("cpu_host", {"socket": "AM4", "memory_types": ["DDR4"], "cpu_model": "Ryzen 5 5600"}, title="AMD Ryzen 5 5600")
    board = row("motherboard", {"socket": "AM4", "memory_type": "DDR4", "gpu_slot": "PCIe x16", "gpu_slot_lanes": 16, "form_factors": ["ATX"], "supports_nvme_m2": True})
    board["spec_enrichment"] = {
        "structured_document": {
            "cpu_support_matrix": [{
                "cpu_model": "Ryzen 5 5600",
                "minimum_bios_version": "7C56vA9",
                "support_status": "supported",
                "source_url": "https://vendor.example/support",
                "source_type": "manufacturer_support_table",
                "confidence": "exact",
            }],
            "cpu_support_matrix_complete": False,
        }
    }
    return {
        "cpu_host": cpu,
        "motherboard": board,
        "host_ram_32gb": row("host_ram_32gb", {"memory_type": "DDR4", "capacity_gb": 32}),
        "storage_1tb": row("storage_1tb", {"interface": "NVMe", "form_factor": "M.2", "capacity_gb": 1000}),
        "psu_750w": row("psu_750w", {"wattage_w": 750}),
        "cooling": row("cooling", {"supported_sockets": ["AM4", "LGA1700"], "height_mm": 155}),
        "chassis": row("chassis", {"motherboard_form_factors": ["ATX", "mATX"], "max_gpu_length_mm": 360, "max_gpu_slots": 4, "max_cpu_cooler_height_mm": 160}),
    }


def test_gpu_requirement_uses_system_psu_not_board_power():
    req = gpu_requirements(gpu())
    assert req["minimum_psu_w"] == 750
    assert req["minimum_pcie_lanes"] == 16


def test_compatible_build_checks_all_major_dimensions_and_bios_pair():
    result = evaluate_build_compatibility(compatible_build(), gpu())
    assert result["status"] == "compatible"
    assert result["failures"] == []
    assert result["cpu_bios"]["status"] == "supported"
    assert result["cpu_bios"]["minimum_bios_version"] == "7C56vA9"
    assert any("7C56vA9" in warning for warning in result["warnings"])


def test_socket_mismatch_rejected():
    build = compatible_build()
    build["motherboard"]["compatibility_facts"]["socket"] = "LGA1700"
    result = evaluate_build_compatibility(build, gpu())
    assert result["status"] == "incompatible"
    assert any("cpu_socket" in item for item in result["failures"])


def test_ddr_generation_mismatch_rejected():
    build = compatible_build()
    build["host_ram_32gb"]["compatibility_facts"]["memory_type"] = "DDR5"
    result = evaluate_build_compatibility(build, gpu())
    assert result["status"] == "incompatible"
    assert any("memory_type" in item for item in result["failures"])


def test_psu_too_small_rejected():
    build = compatible_build()
    build["psu_750w"]["compatibility_facts"]["wattage_w"] = 650
    result = evaluate_build_compatibility(build, gpu())
    assert result["status"] == "incompatible"
    assert any("psu_wattage" in item for item in result["failures"])


def test_gpu_clearance_and_cooler_height_rejected():
    build = compatible_build()
    build["chassis"]["compatibility_facts"]["max_gpu_length_mm"] = 300
    build["chassis"]["compatibility_facts"]["max_cpu_cooler_height_mm"] = 150
    result = evaluate_build_compatibility(build, gpu())
    assert result["status"] == "incompatible"
    assert any("gpu_clearance" in item for item in result["failures"])
    assert any("cooler_height" in item for item in result["failures"])


def test_unknown_board_partner_dimensions_are_provisional_not_assumed():
    part = {"id": "gpu", "category": "gpu_accelerator", "name": "Partner GPU", "host_requirements": "PCIe 4.0 x16 host; recommended PSU 750W"}
    result = evaluate_build_compatibility(compatible_build(), part)
    assert result["status"] == "provisionally_compatible"
    assert "exact_gpu_length" in result["unknowns"]
    assert "exact_gpu_slot_width" in result["unknowns"]


def test_listing_variant_facts_are_normalized():
    spec = {"variants": [{"id": "b550", "match_terms": ["b550"], "facts": {"socket": "AM4", "memory_type": "DDR4"}}]}
    facts = infer_listing_facts("motherboard", "Example B550 DDR4 ATX Motherboard", spec)
    assert facts["variant"] == "b550"
    assert facts["socket"] == "AM4"


def test_explicit_unsupported_cpu_bios_pair_is_rejected():
    build = compatible_build()
    matrix = build["motherboard"]["spec_enrichment"]["structured_document"]["cpu_support_matrix"]
    matrix[0]["support_status"] = "unsupported"
    pair = evaluate_cpu_bios_pair(build["cpu_host"], build["motherboard"])
    assert pair["status"] == "unsupported"
    result = evaluate_build_compatibility(build, gpu())
    assert result["status"] == "incompatible"
    assert any("cpu_bios_support" in item for item in result["failures"])


def test_partial_matrix_absence_is_unresolved_not_false_unsupported():
    build = compatible_build()
    build["cpu_host"]["compatibility_facts"]["cpu_model"] = "Ryzen 7 5700X"
    build["cpu_host"]["listing"]["title"] = "AMD Ryzen 7 5700X"
    pair = evaluate_cpu_bios_pair(build["cpu_host"], build["motherboard"])
    assert pair["status"] == "unresolved"
    result = evaluate_build_compatibility(build, gpu())
    assert result["status"] == "provisionally_compatible"
    assert "cpu_bios_support" in result["unknowns"]


def test_complete_matrix_absence_is_unsupported():
    build = compatible_build()
    build["cpu_host"]["compatibility_facts"]["cpu_model"] = "Ryzen 7 5700X"
    build["cpu_host"]["listing"]["title"] = "AMD Ryzen 7 5700X"
    build["motherboard"]["spec_enrichment"]["structured_document"]["cpu_support_matrix_complete"] = True
    pair = evaluate_cpu_bios_pair(build["cpu_host"], build["motherboard"])
    assert pair["status"] == "unsupported"


def test_solver_rejects_cheaper_incompatible_path():
    good = compatible_build()
    components = {name: {"candidates": [value]} for name, value in good.items()}
    bad_board = row("motherboard", {"socket": "LGA1700", "memory_type": "DDR4", "gpu_slot": "PCIe x16", "gpu_slot_lanes": 16, "form_factors": ["ATX"], "supports_nvme_m2": True}, 10)
    bad_board["spec_enrichment"] = {"structured_document": {"cpu_support_matrix": [], "cpu_support_matrix_complete": False}}
    components["motherboard"]["candidates"].insert(0, bad_board)
    builds = construct_compatible_builds(components, gpu_part=gpu(), maximum_builds=5)
    assert builds
    assert all(build["components"]["motherboard"]["compatibility_facts"]["socket"] == "AM4" for build in builds)
