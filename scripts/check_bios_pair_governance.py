from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    compatibility = (ROOT / "src/lowpower_llm_cluster/compatibility.py").read_text(encoding="utf-8")
    structured = (ROOT / "src/lowpower_llm_cluster/structured_specs.py").read_text(encoding="utf-8")
    tests = (ROOT / "tests/test_compatibility.py").read_text(encoding="utf-8")
    doc = ROOT / "docs/BIOS_PAIR_COMPATIBILITY.md"

    required_compatibility = (
        "def evaluate_cpu_bios_pair",
        '"cpu_bios_support"',
        '"cpu_bios"',
        '"minimum_bios_version"',
        '"cpu_support_matrix_complete"',
    )
    required_structured = (
        "def extract_cpu_support_rows",
        '"cpu_support_matrix"',
        '"cpu_support_matrix_complete"',
        '"manufacturer_support_table"',
        '"cpu_bios_support_matrix"',
    )
    required_tests = (
        "test_explicit_unsupported_cpu_bios_pair_is_rejected",
        "test_partial_matrix_absence_is_unresolved_not_false_unsupported",
        "test_complete_matrix_absence_is_unsupported",
    )

    errors: list[str] = []
    for token in required_compatibility:
        if token not in compatibility:
            errors.append(f"compatibility engine lost BIOS pair invariant: {token}")
    for token in required_structured:
        if token not in structured:
            errors.append(f"structured ingestion lost BIOS matrix invariant: {token}")
    for token in required_tests:
        if token not in tests:
            errors.append(f"BIOS pair regression test missing: {token}")
    if not doc.exists():
        errors.append("docs/BIOS_PAIR_COMPATIBILITY.md is required")

    if errors:
        print("BIOS pair governance checks failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("BIOS pair governance checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
