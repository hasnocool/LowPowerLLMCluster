from __future__ import annotations

import argparse
import re

from .promotion_state import STATES, build_promotion_snapshot, filter_promotion_items

_TERMINAL_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _terminal_text(value: object) -> str:
    return _TERMINAL_CONTROL.sub("", str(value))


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect discovery-to-canonical promotion state")
    parser.add_argument("--discovery", default="results/discovery-latest.json")
    parser.add_argument("--report", default="results/promotion-latest.json")
    parser.add_argument("--catalog", default="data/catalog/auto-promoted.json")
    parser.add_argument("--state", choices=STATES)
    parser.add_argument("--reason", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    snapshot = build_promotion_snapshot(
        discovery_path=args.discovery,
        report_path=args.report,
        catalog_path=args.catalog,
    )
    counts = snapshot["counts"]
    print(
        "Promotion state: "
        + " | ".join(f"{state}={counts.get(state, 0)}" for state in STATES)
        + f" | total={snapshot['total']}"
    )
    if snapshot.get("reason_counts"):
        print("Top hold reasons:")
        for reason, count in list(snapshot["reason_counts"].items())[:10]:
            print(f"  {count:>5}  {_terminal_text(reason)}")

    rows = filter_promotion_items(
        snapshot["items"],
        state=args.state or "",
        reason=args.reason,
        query=args.query,
        source=args.source,
    )
    print(f"\nShowing {min(len(rows), max(1, args.limit))} of {len(rows)} matching records")
    for row in rows[: max(1, args.limit)]:
        reasons = ",".join(_terminal_text(value) for value in row.get("promotion_reasons", [])) or "-"
        identity = row.get("mpn") or row.get("sku") or row.get("source_id") or "-"
        print(
            f"{_terminal_text(row.get('promotion_state', '-')):<16} "
            f"{_terminal_text(row.get('source', '-')):<28} "
            f"{_terminal_text(identity):<24} "
            f"{_terminal_text(row.get('title', ''))[:70]}  [{reasons}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
