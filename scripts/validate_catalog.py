from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lowpower_llm_cluster.catalog import load_catalog  # noqa: E402

CATALOG = ROOT / "data/parts.json"
REQUIRED = {
    "id", "category", "name", "vendor", "price_min_usd", "price_max_usd",
    "price_status", "moq", "url", "verified_on", "listing_status", "plain_language",
}
LLM_REQUIRED = {"hardware_class", "software_maturity", "risk_level", "memory_config_status"}
ACCELERATOR_CATEGORIES = {
    "gpu_accelerator", "npu_accelerator", "tpu_accelerator", "ai_asic_accelerator", "fpga_accelerator",
    "adaptive_soc", "decommissioned_accelerator",
}
MOBILE_ENDPOINT_CATEGORIES = {"mobile_phone", "tablet", "media_device"}
ACCELERATOR_REQUIRED = {
    "hardware_class", "accelerator_family", "accelerator", "host_mode", "llm_support",
    "workload_role", "software_stack", "software_maturity", "risk_level", "lifecycle_status",
}
VALID_RISK = {"low", "medium", "high"}
VALID_MEMORY_STATUS = {"included", "fixed", "configurable", "unknown"}
VALID_PERFORMANCE_SOURCE = {"measured_local", "community_measured", "vendor_measured", "derived_estimate", "spec_based_estimate", "unknown"}
VALID_CONFIDENCE = {"high", "medium", "low", "unknown"}
UNRESOLVED_PRICE_MARKERS = {"watch", "not_resolved", "live_market_required"}


def main() -> int:
    data = load_catalog(CATALOG)
    seen: set[str] = set()
    errors: list[str] = []
    valid_categories = set(data.get("candidate_categories", []))

    if data.get("schema_version") != 3:
        errors.append("catalog schema_version must be 3")
    if not data.get("part_files"):
        errors.append("catalog v3 manifest must define part_files")

    for part in data.get("parts", []):
        missing = REQUIRED - part.keys()
        if missing:
            errors.append(f"{part.get('id', '<missing-id>')}: missing {sorted(missing)}")
        part_id = part.get("id")
        if part_id in seen:
            errors.append(f"duplicate id: {part_id}")
        seen.add(part_id)

        if valid_categories and part.get("category") not in valid_categories:
            errors.append(f"{part_id}: unknown category {part.get('category')!r}")

        low = part.get("price_min_usd")
        high = part.get("price_max_usd")
        if (low is None) != (high is None):
            errors.append(f"{part_id}: price_min_usd and price_max_usd must both be null or both numeric")
        if low is not None and high is not None:
            if float(low) > float(high):
                errors.append(f"{part_id}: minimum price exceeds maximum")
            if float(low) <= 0:
                errors.append(f"{part_id}: known price must be positive; use null when unresolved")
        else:
            status = str(part.get("price_status", "")).casefold()
            if not any(marker in status for marker in UNRESOLVED_PRICE_MARKERS):
                errors.append(f"{part_id}: unresolved price needs an explicit watch/not_resolved/live_market_required price_status")

        try:
            date.fromisoformat(part.get("verified_on", ""))
        except ValueError:
            errors.append(f"{part_id}: verified_on must be YYYY-MM-DD")
        if not str(part.get("url", "")).startswith("https://"):
            errors.append(f"{part_id}: URL must use https://")

        if part.get("risk_level") is not None and part.get("risk_level") not in VALID_RISK:
            errors.append(f"{part_id}: risk_level must be one of {sorted(VALID_RISK)}")

        if part.get("llm_candidate", False):
            llm_missing = LLM_REQUIRED - part.keys()
            if llm_missing:
                errors.append(f"{part_id}: LLM candidate missing {sorted(llm_missing)}")
            if part.get("memory_config_status") not in VALID_MEMORY_STATUS:
                errors.append(f"{part_id}: invalid memory_config_status")
            installed = part.get("memory_capacity_gb")
            board_max = part.get("max_memory_gb")
            cpu_max = part.get("cpu_max_memory_gb")
            memory_unknown_mobile = (
                part.get("category") in MOBILE_ENDPOINT_CATEGORIES
                and part.get("memory_config_status") == "unknown"
                and installed is None and board_max is None and cpu_max is None
            )
            if installed is None and board_max is None and cpu_max is None and not memory_unknown_mobile:
                errors.append(f"{part_id}: LLM candidate needs installed, board-max, or CPU-max memory evidence")
            if part.get("memory_config_status") in {"included", "fixed"} and installed is None:
                errors.append(f"{part_id}: included/fixed memory status requires memory_capacity_gb")
            if part.get("memory_config_status") == "configurable" and installed is not None:
                errors.append(f"{part_id}: configurable/barebone entry should not present memory_capacity_gb as included")

        evidence = part.get("performance_evidence")
        if evidence:
            if evidence.get("source_type") not in VALID_PERFORMANCE_SOURCE:
                errors.append(f"{part_id}: invalid performance_evidence.source_type")
            if evidence.get("confidence") not in VALID_CONFIDENCE:
                errors.append(f"{part_id}: invalid performance_evidence.confidence")

        if part.get("category") in ACCELERATOR_CATEGORIES:
            accel_missing = ACCELERATOR_REQUIRED - part.keys()
            if accel_missing:
                errors.append(f"{part_id}: accelerator entry missing {sorted(accel_missing)}")
            if not part.get("precision_formats") and part.get("lifecycle_status") != "discontinued":
                errors.append(f"{part_id}: accelerator entry needs precision_formats")
            if part.get("category") == "gpu_accelerator":
                if part.get("memory_config_status") != "fixed" or part.get("memory_capacity_gb") is None:
                    errors.append(f"{part_id}: discrete GPU entries must record fixed VRAM capacity")
                if not part.get("power_scope"):
                    errors.append(f"{part_id}: GPU board power must include an explicit power_scope")

    if errors:
        print("Catalog validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(seen)} catalog entries from snapshot {data['snapshot_date']} (schema v3).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
