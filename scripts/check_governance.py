# scripts/check_governance.py
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

    py_match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    init_match = re.search(r'__version__ = "([^"]+)"', init)
    change_match = re.search(r'^## \[([^]]+)\]', changelog, re.MULTILINE)
    found = {
        "VERSION": version,
        "pyproject.toml": py_match.group(1) if py_match else None,
        "package __version__": init_match.group(1) if init_match else None,
        "CHANGELOG latest": change_match.group(1) if change_match else None,
    }
    for source, value in found.items():
        if value != version:
            errors.append(f"{source} is {value!r}, expected {version!r}")

    required = [
        "README.md", "PARTS.md", "TODO.md", "CHANGELOG.md", "AGENTS.md",
        "docs/PROJECT_CHARTER.md", "docs/GUARDRAILS.md", "docs/ACCELERATORS.md", "docs/SOURCING.md", "docs/CONCURRENCY.md",
        "specs/HARDWARE_CATALOG.md", "specs/EVIDENCE.md", "specs/BENCHMARKING.md", "specs/SCORING.md",
        "specs/hardware-catalog.schema.json", "specs/hardware-part.schema.json",
        "specs/benchmark.schema.json", "specs/benchmark-profile.schema.json",
        "specs/adapter-output.schema.json", "specs/discovery-config.schema.json", "specs/performance-record.schema.json",
        "config/discovery.example.json", "data/discovery/watchlist.json",
        "scripts/check_async_blocking.py",
        "docs/BENCHMARK_HARNESS.md", "benchmarks/README.md", "results/README.md",
        ".agents/skills/hardware-research/SKILL.md",
        ".agents/skills/catalog-curation/SKILL.md",
        ".agents/skills/benchmark-hardware/SKILL.md",
        ".agents/skills/architecture-review/SKILL.md",
        ".agents/skills/release-governance/SKILL.md",
        ".agents/skills/accelerator-research/SKILL.md",
    ]
    for rel in required:
        if not (ROOT / rel).exists():
            errors.append(f"required governance artifact missing: {rel}")

    catalog = json.loads((ROOT / "data/parts.json").read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 3:
        errors.append("data/parts.json schema_version must be 3")

    return fail(errors)


if __name__ == "__main__":
    raise SystemExit(main())
