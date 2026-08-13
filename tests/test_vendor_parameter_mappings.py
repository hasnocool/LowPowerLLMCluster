# tests/test_vendor_parameter_mappings.py
from __future__ import annotations

from lowpower_llm_cluster.structured_identity import extract_structured_identity


def test_vendor_aliases_map_explicit_values_without_inference() -> None:
    mappings = {
        "schema_version": 1,
        "generic": {},
        "vendors": {
            "ExampleStorage": {
                "ssd_controller": ["Controller IC"],
                "nand_type": ["NAND Technology"],
            }
        },
    }
    cfg = extract_structured_identity(
        [("Controller IC", "Phison E18"), ("NAND Technology", "176L TLC")],
        existing={"manufacturer": "ExampleStorage"},
        mappings=mappings,
    )
    assert cfg["ssd_controller"] == "Phison E18"
    assert cfg["nand_type"] == "176L TLC"


def test_vendor_alias_does_not_invent_missing_value() -> None:
    mappings = {
        "schema_version": 1,
        "generic": {"vbios_version": ["Graphics BIOS Version"]},
        "vendors": {},
    }
    cfg = extract_structured_identity([], existing={"manufacturer": "ExampleGPU"}, mappings=mappings)
    assert "vbios_version" not in cfg
