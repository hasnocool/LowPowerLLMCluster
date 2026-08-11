# scripts/validate_benchmark_profiles.py
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from lowpower_llm_cluster.benchmarking.adapters import adapter_names  # noqa: E402
from lowpower_llm_cluster.benchmarking.runner import validate_profile  # noqa: E402


def main() -> int:
    errors: list[str] = []
    schema_files = [
        ROOT / "specs/benchmark.schema.json",
        ROOT / "specs/benchmark-profile.schema.json",
        ROOT / "specs/adapter-output.schema.json",
    ]
    for path in schema_files:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid JSON schema {path.relative_to(ROOT)}: {exc}")

    profiles = sorted((ROOT / "benchmarks/profiles").glob("*.json"))
    if not profiles:
        errors.append("no benchmark example profiles found")
    for path in profiles:
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
            validate_profile(profile)
            adapter = str(profile["adapter"]["type"])
            if adapter not in adapter_names():
                errors.append(f"{path.name}: unsupported adapter {adapter}")
        except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
            errors.append(f"{path.name}: {exc}")

    if errors:
        print("Benchmark contract validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(profiles)} benchmark profiles and {len(schema_files)} schemas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
