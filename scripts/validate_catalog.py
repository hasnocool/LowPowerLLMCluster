# scripts/validate_catalog.py
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "parts.json"
REQUIRED = {
    "id",
    "category",
    "name",
    "vendor",
    "price_min_usd",
    "price_max_usd",
    "moq",
    "url",
    "verified_on",
    "listing_status",
    "plain_language",
}
LLM_REQUIRED = {
    "hardware_class",
    "memory_capacity_gb",
    "software_maturity",
    "risk_level",
}
VALID_RISK = {"low", "medium", "high"}


def main() -> int:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    seen: set[str] = set()
    errors: list[str] = []
    valid_categories = set(data.get("candidate_categories", []))

    if data.get("schema_version") != 2:
        errors.append("catalog schema_version must be 2")

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

        if float(part.get("price_min_usd", 0)) > float(part.get("price_max_usd", 0)):
            errors.append(f"{part_id}: minimum price exceeds maximum")
        try:
            date.fromisoformat(part.get("verified_on", ""))
        except ValueError:
            errors.append(f"{part_id}: verified_on must be YYYY-MM-DD")
        if not str(part.get("url", "")).startswith("https://"):
            errors.append(f"{part_id}: URL must use https://")

        if part.get("llm_candidate", False):
            llm_missing = LLM_REQUIRED - part.keys()
            if llm_missing:
                errors.append(f"{part_id}: LLM candidate missing {sorted(llm_missing)}")
            if part.get("risk_level") not in VALID_RISK:
                errors.append(f"{part_id}: risk_level must be one of {sorted(VALID_RISK)}")
            if float(part.get("memory_capacity_gb", 0)) <= 0:
                errors.append(f"{part_id}: memory_capacity_gb must be positive")

    if errors:
        print("Catalog validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(seen)} catalog entries from snapshot {data['snapshot_date']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
