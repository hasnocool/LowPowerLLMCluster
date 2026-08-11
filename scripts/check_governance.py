from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(errors: list[str]) -> int:
    if not errors:
        print("Governance checks passed.")
        return 0
    print("Governance checks failed:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    return 1


def main() -> int:
    errors: list[str] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init = (ROOT / "src/lowpower_llm_cluster/__init__.py").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    py_match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE); init_match = re.search(r'__version__ = "([^"]+)"', init); change_match = re.search(r'^## \[([^]]+)\]', changelog, re.MULTILINE)
    found = {"VERSION": version, "pyproject.toml": py_match.group(1) if py_match else None, "package __version__": init_match.group(1) if init_match else None, "CHANGELOG latest": change_match.group(1) if change_match else None}
    for source, value in found.items():
        if value != version: errors.append(f"{source} is {value!r}, expected {version!r}")

    required = [
        "README.md", "PARTS.md", "TODO.md", "CHANGELOG.md", "AGENTS.md",
        "docs/PROJECT_CHARTER.md", "docs/GUARDRAILS.md", "docs/ACCELERATORS.md", "docs/AUTONOMOUS_REFRESH.md", "docs/CHANGE_INTELLIGENCE.md", "docs/DECISION_QUALITY.md", "docs/GPUS.md", "docs/TOTAL_COST_OF_OWNERSHIP.md", "docs/LIVE_BOM_SOURCING.md",
        "specs/HARDWARE_CATALOG.md", "specs/EVIDENCE.md", "specs/MARKET_INTELLIGENCE.md", "specs/BENCHMARKING.md", "specs/SCORING.md", "specs/hardware-catalog.schema.json", "specs/hardware-part.schema.json", "specs/benchmark.schema.json", "specs/benchmark-profile.schema.json", "specs/adapter-output.schema.json", "docs/BENCHMARK_HARNESS.md", "benchmarks/README.md", "results/README.md",
        "src/lowpower_llm_cluster/market.py", "src/lowpower_llm_cluster/sources.py", "src/lowpower_llm_cluster/market_cli.py", "src/lowpower_llm_cluster/ops.py", "src/lowpower_llm_cluster/refresh_cli.py", "src/lowpower_llm_cluster/intelligence.py", "src/lowpower_llm_cluster/decision.py", "src/lowpower_llm_cluster/tco.py", "src/lowpower_llm_cluster/bom_sourcing.py",
        "data/catalog/gpus.json", "data/market/sources.json", "data/market/profiles.json", "data/market/watchlists.json", "data/market/tco-scenarios.json", "data/market/bom-sourcing.json", "data/market/bom-current.json", "data/market/bom-price-history.json", "data/market/price-history.json", "data/market/listing-state.json", "data/market/fx-cad.json", "data/market/fx-history.json", "data/evidence/performance.json", ".github/workflows/autonomous-refresh.yml",
        ".agents/skills/hardware-research/SKILL.md", ".agents/skills/catalog-curation/SKILL.md", ".agents/skills/benchmark-hardware/SKILL.md", ".agents/skills/architecture-review/SKILL.md", ".agents/skills/release-governance/SKILL.md", ".agents/skills/accelerator-research/SKILL.md",
    ]
    for rel in required:
        if not (ROOT / rel).exists(): errors.append(f"required governance artifact missing: {rel}")

    catalog = json.loads((ROOT / "data/parts.json").read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 3: errors.append("data/parts.json schema_version must be 3")
    if "gpu_accelerator" not in set(catalog.get("candidate_categories", [])): errors.append("data/parts.json must keep gpu_accelerator as a first-class candidate category")
    if "catalog/gpus.json" not in set(catalog.get("part_files", [])): errors.append("data/parts.json must include catalog/gpus.json")

    source_config = json.loads((ROOT / "data/market/sources.json").read_text(encoding="utf-8"))
    if source_config.get("schema_version") != 1: errors.append("data/market/sources.json schema_version must be 1")
    if not source_config.get("gpu_reference_urls"): errors.append("data/market/sources.json must retain official GPU reference coverage")

    profiles = json.loads((ROOT / "data/market/profiles.json").read_text(encoding="utf-8"))
    if profiles.get("schema_version") != 1 or not profiles.get("profiles"): errors.append("data/market/profiles.json must define schema_version 1 and at least one profile")
    profile_text = json.dumps(profiles).casefold()
    for required_gpu in ("rtx 5060 ti", "rtx 3090", "rx 9070", "arc b580"):
        if required_gpu not in profile_text: errors.append(f"autonomous profiles lost GPU sourcing query: {required_gpu}")
    for profile_name, profile in profiles.get("profiles", {}).items():
        if not profile.get("tco_scenario"): errors.append(f"refresh profile {profile_name} must select a TCO scenario")

    tco = json.loads((ROOT / "data/market/tco-scenarios.json").read_text(encoding="utf-8"))
    if tco.get("schema_version") != 3 or not tco.get("energy_scenarios"): errors.append("data/market/tco-scenarios.json must define schema_version 3 and energy scenarios")
    component_costs = tco.get("component_costs_cad") or {}
    required_components = ("cpu_host", "motherboard", "host_ram_32gb", "storage_1tb", "psu_750w", "pcie_adapter", "cooling", "chassis")
    for required_component in required_components:
        if required_component not in component_costs: errors.append(f"TCO scenario lost required discrete-GPU BOM component: {required_component}")
    ownership_profiles = tco.get("ownership_profiles") or {}
    for required_profile in ("new-build", "reuse-host-core", "reuse-complete-host", "reuse-everything"):
        if required_profile not in ownership_profiles: errors.append(f"TCO scenario lost ownership profile: {required_profile}")

    bom = json.loads((ROOT / "data/market/bom-sourcing.json").read_text(encoding="utf-8"))
    if bom.get("schema_version") != 1: errors.append("data/market/bom-sourcing.json schema_version must be 1")
    for required_component in required_components:
        if required_component not in (bom.get("components") or {}): errors.append(f"live BOM sourcing lost component query: {required_component}")
    if not set(bom.get("sources") or []) & {"mouser", "digikey", "ebay"}: errors.append("live BOM sourcing must retain at least one structured online source")

    tco_source = (ROOT / "src/lowpower_llm_cluster/tco.py").read_text(encoding="utf-8"); cli_source = (ROOT / "src/lowpower_llm_cluster/refresh_cli.py").read_text(encoding="utf-8"); bom_source = (ROOT / "src/lowpower_llm_cluster/bom_sourcing.py").read_text(encoding="utf-8")
    for required_function in ("def break_even_analysis", "def ownership_components"):
        if required_function not in tco_source: errors.append(f"TCO engine must retain {required_function.split()[-1]}")
    if "sourced_component_costs" not in tco_source: errors.append("TCO engine must consume sourced BOM costs when available")
    if '"break-even"' not in cli_source or '"--ownership"' not in cli_source or '"refresh-bom"' not in cli_source: errors.append("refresh CLI must retain break-even, ownership and refresh-bom workflows")
    if "async def refresh_bom_market" not in bom_source: errors.append("live BOM source engine must retain refresh_bom_market")

    watchlists = json.loads((ROOT / "data/market/watchlists.json").read_text(encoding="utf-8"))
    if watchlists.get("schema_version") != 1 or not isinstance(watchlists.get("watchlists"), list): errors.append("data/market/watchlists.json must define schema_version 1 and a watchlists array")
    if "gpu-value" not in {str(row.get("id")) for row in watchlists.get("watchlists", [])}: errors.append("data/market/watchlists.json must retain the gpu-value watchlist")

    source_text = (ROOT / "data/market/sources.json").read_text(encoding="utf-8")
    for forbidden in ("api_key", "client_secret", "access_token"):
        if re.search(rf'"{forbidden}"\s*:\s*"[^\"]+"', source_text, re.IGNORECASE): errors.append(f"data/market/sources.json must not contain credential value {forbidden}")
    return fail(errors)


if __name__ == "__main__":
    raise SystemExit(main())
