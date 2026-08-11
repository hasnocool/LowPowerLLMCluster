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
        "docs/APPLE_MOBILE_NODES.md", "docs/FIRMWARE_BOOT_READINESS.md", "docs/POWER_ESTIMATION.md",
        "tests/test_mobile_platform.py", "tests/test_apple_resolution.py", "tests/test_firmware_readiness.py",
        "tests/test_manufacturer_support.py", "tests/test_firmware_discovery.py", "tests/test_firmware_history.py",
        "tests/test_bios_versioning.py", "tests/test_power_evidence.py", "tests/test_power_ingestion.py",
    ]
    for rel in required:
        if not (ROOT / rel).exists(): errors.append(f"required mobile/firmware/power artifact missing: {rel}")

    manifest=json.loads((ROOT/"data/parts.json").read_text(encoding="utf-8")); categories=set(manifest.get("candidate_categories") or [])
    for category in ("apple_silicon_system","mobile_phone","tablet","media_device"):
        if category not in categories: errors.append(f"catalog manifest lost mobile category: {category}")
    for rel in ("catalog/apple-low-power.json","catalog/mobile-devices.json"):
        if rel not in set(manifest.get("part_files") or []): errors.append(f"catalog manifest lost part file: {rel}")

    apple_text=(ROOT/"data/catalog/apple-low-power.json").read_text(encoding="utf-8").casefold()
    for term in ("m1","m4","m5","mac mini","mac studio","macbook air","macbook pro","ipad pro","iphone","apple tv"):
        if term not in apple_text: errors.append(f"Apple catalog lost expected family coverage: {term}")
    mobile_text=(ROOT/"data/catalog/mobile-devices.json").read_text(encoding="utf-8").casefold()
    for term in ("pixel 10 pro","galaxy s26 ultra"):
        if term not in mobile_text: errors.append(f"mobile catalog lost current reference: {term}")

    mobile_source=(ROOT/"src/lowpower_llm_cluster/mobile_platform.py").read_text(encoding="utf-8")
    for function in ("def mobile_runtime_profile","def model_fit_memory_budget"):
        if function not in mobile_source: errors.append(f"mobile runtime layer lost {function.split()[-1]}")
    if '"persistent_daemon": False' not in mobile_source: errors.append("mobile runtime policy must not treat phones/tablets as normal persistent daemon hosts")
    if '"performance_claim": False' not in mobile_source: errors.append("mobile memory budget must remain capacity-only, not a performance claim")

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

    support_source=(ROOT/"src/lowpower_llm_cluster/manufacturer_support.py").read_text(encoding="utf-8")
    for term in ("def ingest_support_endpoint","def ingest_ranked_support_endpoints","def pagination_metadata","MAX_SUPPORT_PAGES = 64","explicit_total_pages","explicit_total_count","explicit_has_more_false","endpoint_not_on_expected_official_host"):
        if term not in support_source: errors.append(f"manufacturer support ingestion lost completeness/host guardrail: {term}")

    discovery_source=(ROOT/"src/lowpower_llm_cluster/firmware_discovery.py").read_text(encoding="utf-8")
    for term in ("def discover_unlinked_support_surfaces","def probe_unlinked_support_candidates","def normalize_bios_history_payload","def extract_board_revision_evidence","def shipped_bios_evidence","official_sitemap","inline_script_endpoint"):
        if term not in discovery_source: errors.append(f"deep firmware discovery lost evidence/guardrail: {term}")
    if "MAX_DISCOVERY_FETCHES = 8" not in discovery_source: errors.append("deep firmware discovery must remain bounded")

    power_source=(ROOT/"src/lowpower_llm_cluster/power_evidence.py").read_text(encoding="utf-8")
    for term in ("def hardware_power_identity","def aggregate_power_observations","hardware_specific:","configuration_conflict:","power_evidence_distribution","eligible_for_device_power"):
        if term not in power_source: errors.append(f"self-improving power evidence lost invariant: {term}")
    identity_source=(ROOT/"src/lowpower_llm_cluster/power_identity.py").read_text(encoding="utf-8")
    for term in ("storage_controller","nand_type","gpu_board_revision","host_motherboard","apple_model_identifier","ram_topology","mobile_soc_variant","def identity_specificity"):
        if term not in identity_source: errors.append(f"hardware-specific power identity lost field: {term}")
    ingestion_source=(ROOT/"src/lowpower_llm_cluster/power_ingestion.py").read_text(encoding="utf-8")
    for term in ("def catalog_power_observations","def benchmark_power_observations","def refresh_power_evidence","throughput_divided_by_tokens_per_joule","eligible_for_device_power","USABLE_DEVICE_SCOPES"):
        if term not in ingestion_source: errors.append(f"automatic power ingestion lost evidence/scope guardrail: {term}")

    compatibility_source=(ROOT/"src/lowpower_llm_cluster/compatibility.py").read_text(encoding="utf-8")
    for term in ("boot_readiness_score",'"boot_readiness"'):
        if term not in compatibility_source: errors.append(f"complete-build compatibility lost boot-readiness integration: {term}")

    if errors:
        print("Mobile/firmware governance checks failed:",file=sys.stderr)
        for error in errors: print(f"- {error}",file=sys.stderr)
        return 1
    print("Mobile/firmware governance checks passed."); return 0


if __name__=="__main__": raise SystemExit(main())
