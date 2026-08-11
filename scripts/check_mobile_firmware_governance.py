from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    required = [
        "data/catalog/apple-low-power.json", "data/catalog/mobile-devices.json", "data/power/evidence.json",
        "src/lowpower_llm_cluster/mobile_platform.py", "src/lowpower_llm_cluster/apple_resolution.py",
        "src/lowpower_llm_cluster/firmware_readiness.py", "src/lowpower_llm_cluster/manufacturer_support.py",
        "src/lowpower_llm_cluster/firmware_discovery.py", "src/lowpower_llm_cluster/firmware_history.py",
        "src/lowpower_llm_cluster/bios_versioning.py", "src/lowpower_llm_cluster/power_evidence.py",
        "src/lowpower_llm_cluster/power_identity.py", "src/lowpower_llm_cluster/power_ingestion.py",
        "src/lowpower_llm_cluster/identity_extraction.py",
        "docs/APPLE_MOBILE_NODES.md", "docs/FIRMWARE_BOOT_READINESS.md", "docs/POWER_ESTIMATION.md",
        "docs/AUTOMATIC_IDENTITY_ENRICHMENT.md",
        "tests/test_mobile_platform.py", "tests/test_apple_resolution.py", "tests/test_firmware_readiness.py",
        "tests/test_manufacturer_support.py", "tests/test_firmware_discovery.py", "tests/test_firmware_history.py",
        "tests/test_bios_versioning.py", "tests/test_power_evidence.py", "tests/test_power_ingestion.py",
        "tests/test_identity_extraction.py",
    ]
    for rel in required:
        if not (ROOT / rel).exists(): errors.append(f"required mobile/firmware/power artifact missing: {rel}")

    manifest=json.loads((ROOT/"data/parts.json").read_text(encoding="utf-8")); categories=set(manifest.get("candidate_categories") or [])
    for category in ("apple_silicon_system","mobile_phone","tablet","media_device"):
        if category not in categories: errors.append(f"catalog manifest lost mobile category: {category}")

    firmware_source=(ROOT/"src/lowpower_llm_cluster/firmware_readiness.py").read_text(encoding="utf-8")
    for term in ("def discover_support_endpoints","def detect_bios_flashback","def boot_readiness_score","shipped_bios_meets_requirement"):
        if term not in firmware_source: errors.append(f"firmware readiness lost invariant: {term}")
    if '"performance_claim": False' not in firmware_source and '"performance_claim":False' not in firmware_source: errors.append("boot-readiness score must not become a performance claim")

    bios_source=(ROOT/"src/lowpower_llm_cluster/bios_versioning.py").read_text(encoding="utf-8")
    for term in ("def compare_bios_versions","msi_base36_suffix_order","gigabyte_f_release_order","asus_numeric_release_order","asrock_same_series_numeric_order","vendor_version_order_unresolved"):
        if term not in bios_source: errors.append(f"BIOS versioning lost conservative vendor comparator: {term}")
    history_source=(ROOT/"src/lowpower_llm_cluster/firmware_history.py").read_text(encoding="utf-8")
    for term in ("def normalize_revision_scoped_bios_history","def bios_history_for_revision","unscoped_rows_ignored"):
        if term not in history_source: errors.append(f"revision-scoped BIOS history lost invariant: {term}")

    discovery_source=(ROOT/"src/lowpower_llm_cluster/firmware_discovery.py").read_text(encoding="utf-8")
    for term in ("def discover_unlinked_support_surfaces","def probe_unlinked_support_candidates","revision_bios_history","normalize_revision_scoped_bios_history","bios_history"):
        if term not in discovery_source: errors.append(f"deep firmware discovery lost revision/API evidence: {term}")
    if "MAX_DISCOVERY_FETCHES = 8" not in discovery_source: errors.append("deep firmware discovery must remain bounded")

    power_source=(ROOT/"src/lowpower_llm_cluster/power_evidence.py").read_text(encoding="utf-8")
    for term in ("def hardware_power_identity","def aggregate_power_observations","power_evidence_distribution","eligible_for_device_power"):
        if term not in power_source: errors.append(f"self-improving power evidence lost invariant: {term}")
    identity_source=(ROOT/"src/lowpower_llm_cluster/power_identity.py").read_text(encoding="utf-8")
    for term in ("storage_controller","nand_type","gpu_board_revision","host_motherboard","apple_model_identifier","ram_topology","mobile_soc_variant","def identity_specificity"):
        if term not in identity_source: errors.append(f"hardware-specific power identity lost field: {term}")
    extraction_source=(ROOT/"src/lowpower_llm_cluster/identity_extraction.py").read_text(encoding="utf-8")
    for term in ("def enrich_hardware_identity","ssd_controller","nand_type","gpu_board_revision","vbios_version","ram_topology","device_sku","soc_variant","host_motherboard","def extract_seller_firmware_evidence","installed_bios_version","seller_listing_text"):
        if term not in extraction_source: errors.append(f"automatic identity extraction lost field/guardrail: {term}")
    market_source=(ROOT/"src/lowpower_llm_cluster/market.py").read_text(encoding="utf-8")
    for term in ("enrich_hardware_identity","extract_seller_firmware_evidence","seller_firmware_evidence","structured_marketplace"):
        if term not in market_source: errors.append(f"listing normalization lost automatic identity/seller firmware integration: {term}")

    if errors:
        print("Mobile/firmware governance checks failed:",file=sys.stderr)
        for error in errors: print(f"- {error}",file=sys.stderr)
        return 1
    print("Mobile/firmware governance checks passed."); return 0


if __name__=="__main__": raise SystemExit(main())
