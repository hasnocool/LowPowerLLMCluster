# scripts/check_staleness.py
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "parts.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    today = date.today()
    stale = []
    for part in data["parts"]:
        age = (today - date.fromisoformat(part["verified_on"])).days
        if age > args.days:
            stale.append((part["id"], age))
    if stale:
        print(f"Listings older than {args.days} days:")
        for part_id, age in stale:
            print(f"- {part_id}: {age} days")
        return 1
    print(f"All listings are <= {args.days} days old.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
