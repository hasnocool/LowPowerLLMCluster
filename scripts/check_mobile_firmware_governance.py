from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    required = [
        "data/catalog/apple-low-power.json",
        "data/catalog/mobile-devices.json",
        "src/lowpower_llm_cluster/mobile_platform.py",
        "src/lowpower_llm_cluster/firmware_readiness.py",
        "docs/APPLE_MOBILE_NODES.md",
        "docs/FIRMWARE_BOOT_READINESS.md",
        "tests/test_mobile_platform.py",
        "tests/test_firmware_readiness.py",
    ]
    for rel in required:
        if not (ROOT / rel).exists():
            errors.append(f"required mobile/firmware artifact missing: {rel}")

    manifest = json.loads((ROOT / "data/parts.json").read_text(encoding="utf-8"))
    categories = set(manifest.get("candidate_categories") or [])
    for category in ("apple_silicon_system", "mobile_phone", "tablet", "media_device"):
        if category not in categories:
            errors.append(f"catalog manifest lost mobile category: {category}")
    part_files = set(manifest.get("part_files") or [])
    for rel in ("catalog/apple-low-power.json", "catalog/mobile-devices.json"):
        if rel not in part_files:
            errors.append(f"catalog manifest lost part file: {rel}")

    apple_text = (ROOT / "data/catalog/apple-low-power.json").read_text(encoding="utf-8").casefold()
    for term in ("m1", "m4", "m5", "mac mini", "mac studio", "macbook air", "macbook pro", "ipad pro", "iphone", "apple tv"):
        if term not in apple_text:
            errors.append(f"Apple catalog lost expected family coverage: {term}")
    mobile_text = (ROOT / "data/catalog/mobile-devices.json").read_text(encoding="utf-8").casefold()
    for term in ("pixel 10 pro", "galaxy s26 ultra"):
        if term not in mobile_text:
            errors.append(f"mobile catalog lost current reference: {term}")

    mobile_source = (ROOT / "src/lowpower_llm_cluster/mobile_platform.py").read_text(encoding="utf-8")
    for function in ("def mobile_runtime_profile", "def model_fit_memory_budget"):
        if function not in mobile_source:
            errors.append(f"mobile runtime layer lost {function.split()[-1]}")
    if '"persistent_daemon": False' not in mobile_source:
        errors.append("mobile runtime policy must not treat phones/tablets as normal persistent daemon hosts")
    if '"performance_claim": False' not in mobile_source:
        errors.append("mobile memory budget must remain capacity-only, not a performance claim")

    firmware_source = (ROOT / "src/lowpower_llm_cluster/firmware_readiness.py").read_text(encoding="utf-8")
    for function in ("def discover_support_endpoints", "def detect_bios_flashback", "def boot_readiness_score"):
        if function not in firmware_source:
            errors.append(f"firmware readiness layer lost {function.split()[-1]}")
    for term in ("USB BIOS FlashBack", "Q-Flash Plus", "Flash BIOS Button", "cpu_less_update_explicit"):
        if term not in firmware_source:
            errors.append(f"firmware readiness lost evidence token: {term}")
    if '"performance_claim": False' not in firmware_source:
        errors.append("boot-readiness score must not become a performance claim")

    structured_source = (ROOT / "src/lowpower_llm_cluster/structured_specs.py").read_text(encoding="utf-8")
    for term in ("support_endpoints", "bios_flashback", "discover_support_endpoints", "detect_bios_flashback"):
        if term not in structured_source:
            errors.append(f"structured motherboard enrichment lost firmware evidence: {term}")

    compatibility_source = (ROOT / "src/lowpower_llm_cluster/compatibility.py").read_text(encoding="utf-8")
    for term in ("boot_readiness_score", '"boot_readiness"'):
        if term not in compatibility_source:
            errors.append(f"complete-build compatibility lost boot-readiness integration: {term}")

    profiles = (ROOT / "data/market/profiles.json").read_text(encoding="utf-8").casefold()
    for term in ("macbook air m5", "mac mini m4", "ipad pro m5", "iphone 17 pro", "pixel 10 pro", "galaxy s26 ultra"):
        if term not in profiles:
            errors.append(f"market profiles lost Apple/mobile query: {term}")

    if errors:
        print("Mobile/firmware governance checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Mobile/firmware governance checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
