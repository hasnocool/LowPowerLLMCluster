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
        "src/lowpower_llm_cluster/firmware_discovery.py", "src/lowpower_llm_cluster/power_evidence.py",
        "src/lowpower_llm_cluster/power_ingestion.py",
        "docs/APPLE_MOBILE_NODES.md", "docs/FIRMWARE_BOOT_READINESS.md", "docs/POWER_ESTIMATION.md",
        "tests/test_mobile_platform.py", "tests/test_apple_resolution.py", "tests/test_firmware_readiness.py",
        "tests/test_manufacturer_support.py", "tests/test_firmware_discovery.py", "tests/test_power_evidence.py", "tests/test_power_ingestion.py",
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

    apple_resolver=(ROOT/"src/lowpower_llm_cluster/apple_resolution.py").read_text(encoding="utf-8")
    for term in ("def resolve_apple_configuration","apple_a_number","model_identifier","apple_part_number","memory_capacity_gb","storage_gb","battery_cycle_count","battery_health_percent","activation_lock","mdm_enrollment","gpu_core_count_explicit","exact_configuration"):
        if term not in apple_resolver: errors.append(f"Apple exact-resolution layer lost evidence field: {term}")
    if '"performance_claim": False' not in apple_resolver: errors.append("Apple exact-resolution metadata must not become a performance claim")
    if "resolve_apple_configuration" not in (ROOT/"src/lowpower_llm_cluster/sources.py").read_text(encoding="utf-8"): errors.append("live adapters lost Apple exact-configuration enrichment")

    firmware_source=(ROOT/"src/lowpower_llm_cluster/firmware_readiness.py").read_text(encoding="utf-8")
    for function in ("def discover_support_endpoints","def detect_bios_flashback","def boot_readiness_score"):
        if function not in firmware_source: errors.append(f"firmware readiness layer lost {function.split()[-1]}")
    for term in ("USB BIOS FlashBack","Q-Flash Plus","Flash BIOS Button","cpu_less_update_explicit"):
        if term not in firmware_source: errors.append(f"firmware readiness lost evidence token: {term}")
    if '"performance_claim": False' not in firmware_source and '"performance_claim":False' not in firmware_source:
        errors.append("boot-readiness score must not become a performance claim")

    support_source=(ROOT/"src/lowpower_llm_cluster/manufacturer_support.py").read_text(encoding="utf-8")
    for term in ("def ingest_support_endpoint","def ingest_ranked_support_endpoints","def pagination_metadata","MAX_SUPPORT_PAGES = 64","explicit_total_pages","explicit_total_count","explicit_has_more_false","endpoint_not_on_expected_official_host"):
        if term not in support_source: errors.append(f"manufacturer support ingestion lost completeness/host guardrail: {term}")

    discovery_source=(ROOT/"src/lowpower_llm_cluster/firmware_discovery.py").read_text(encoding="utf-8")
    for term in ("def discover_unlinked_support_surfaces","def probe_unlinked_support_candidates","def normalize_bios_history_payload","def extract_board_revision_evidence","def shipped_bios_evidence","official_sitemap","inline_script_endpoint"):
        if term not in discovery_source: errors.append(f"deep firmware discovery lost evidence/guardrail: {term}")
    if "MAX_DISCOVERY_FETCHES = 8" not in discovery_source: errors.append("deep firmware discovery must remain bounded")

    structured_source=(ROOT/"src/lowpower_llm_cluster/structured_specs.py").read_text(encoding="utf-8")
    for term in ("support_endpoints","bios_flashback","discover_support_endpoints","detect_bios_flashback","ingest_ranked_support_endpoints","cpu_support_matrix_completeness_proof","discover_unlinked_support_surfaces","probe_unlinked_support_candidates","bios_history","board_revisions","shipped_bios"):
        if term not in structured_source: errors.append(f"structured motherboard enrichment lost firmware/API evidence: {term}")
    if 'stats["cpu_support_matrix_complete"]=bool(api_result.get("complete"))' not in structured_source and 'stats["cpu_support_matrix_complete"] = bool(api_result.get("complete"))' not in structured_source:
        errors.append("structured motherboard enrichment lost API completeness propagation")

    power_source=(ROOT/"src/lowpower_llm_cluster/power_evidence.py").read_text(encoding="utf-8")
    for term in ("def hardware_power_identity","def aggregate_power_observations","load_p25_w","load_p75_w","exact_sku_or_model_identifier","configuration_conflict","power_evidence_distribution","eligible_for_device_power"):
        if term not in power_source: errors.append(f"self-improving power evidence lost invariant: {term}")
    model_source=(ROOT/"src/lowpower_llm_cluster/power_model.py").read_text(encoding="utf-8")
    for term in ("aggregate_power_observations",'"distribution": learned',"match_level"):
        if term not in model_source: errors.append(f"power model lost learned evidence priority: {term}")
    ingestion_source=(ROOT/"src/lowpower_llm_cluster/power_ingestion.py").read_text(encoding="utf-8")
    for term in ("def catalog_power_observations","def benchmark_power_observations","def refresh_power_evidence","throughput_divided_by_tokens_per_joule","eligible_for_device_power","USABLE_DEVICE_SCOPES"):
        if term not in ingestion_source: errors.append(f"automatic power ingestion lost evidence/scope guardrail: {term}")
    cli_source=(ROOT/"src/lowpower_llm_cluster/refresh_cli.py").read_text(encoding="utf-8")
    for term in ("refresh-power-evidence","power-evidence","refresh_power_evidence"):
        if term not in cli_source: errors.append(f"power evidence CLI lost operator surface: {term}")
    ops_source=(ROOT/"src/lowpower_llm_cluster/ops.py").read_text(encoding="utf-8")
    if "refresh_power_evidence" not in ops_source or '"power_evidence": power_result' not in ops_source:
        errors.append("autonomous refresh must update learned power evidence before decision/TCO reports")

    compatibility_source=(ROOT/"src/lowpower_llm_cluster/compatibility.py").read_text(encoding="utf-8")
    for term in ("boot_readiness_score",'"boot_readiness"'):
        if term not in compatibility_source: errors.append(f"complete-build compatibility lost boot-readiness integration: {term}")

    profiles=(ROOT/"data/market/profiles.json").read_text(encoding="utf-8").casefold()
    for term in ("macbook air m5","mac mini m4","ipad pro m5","iphone 17 pro","pixel 10 pro","galaxy s26 ultra"):
        if term not in profiles: errors.append(f"market profiles lost Apple/mobile query: {term}")

    if errors:
        print("Mobile/firmware governance checks failed:",file=sys.stderr)
        for error in errors: print(f"- {error}",file=sys.stderr)
        return 1
    print("Mobile/firmware governance checks passed."); return 0


if __name__=="__main__": raise SystemExit(main())
