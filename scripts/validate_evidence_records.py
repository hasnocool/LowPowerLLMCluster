# scripts/validate_evidence_records.py
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PERFORMANCE_DIR = ROOT / "data" / "performance"
VALID_SOURCE_TYPES = {"measured_local", "community_measured", "vendor_measured", "derived_estimate", "spec_based_estimate", "unknown"}
VALID_WORKLOADS = {"llm_prefill", "llm_decode", "vision", "audio", "embedding", "reranking", "other_specialist"}
REQUIRED = {"hardware_id", "source_type", "source_url", "model", "runtime", "workload_class", "metric_name", "value", "unit"}


def main() -> int:
    errors: list[str] = []
    count = 0
    for path in sorted(PERFORMANCE_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("records", []) if isinstance(payload, dict) else []
        if not isinstance(records, list):
            errors.append(f"{path.name}: records must be an array")
            continue
        for index, record in enumerate(records):
            count += 1
            label = f"{path.name}[{index}]"
            missing = REQUIRED - record.keys()
            if missing:
                errors.append(f"{label}: missing {sorted(missing)}")
                continue
            if record["source_type"] not in VALID_SOURCE_TYPES:
                errors.append(f"{label}: invalid source_type {record['source_type']!r}")
            if record["workload_class"] not in VALID_WORKLOADS:
                errors.append(f"{label}: invalid workload_class {record['workload_class']!r}")
            parsed = urlsplit(str(record["source_url"]))
            if parsed.scheme != "https" or not parsed.netloc:
                errors.append(f"{label}: source_url must be an https URL")
            try:
                float(record["value"])
            except (TypeError, ValueError):
                errors.append(f"{label}: value must be numeric")
            power_w = record.get("power_w")
            if power_w is not None and float(power_w) <= 0:
                errors.append(f"{label}: power_w must be positive")
            if power_w is not None and not str(record.get("power_scope", "")).strip():
                errors.append(f"{label}: power_w requires power_scope")
    if errors:
        print("Evidence validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Validated {count} sourced performance records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
