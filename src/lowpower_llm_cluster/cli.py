# src/lowpower_llm_cluster/cli.py
from __future__ import annotations

import argparse
from collections import Counter
from typing import Any

from .catalog import llm_candidates, load_catalog, midpoint_price
from .scoring import node_score


def money(value: float) -> str:
    return f"${value:,.2f}"


def display_price(part: dict[str, Any]) -> str:
    mid = midpoint_price(part)
    return money(mid) if mid is not None else "unknown"


def rank_nodes(parts: list[dict[str, Any]]) -> int:
    nodes = llm_candidates(parts)
    nodes.sort(key=lambda part: (node_score(part), midpoint_price(part) is not None), reverse=True)
    print("Score  Mid price  Target W  Class                 Candidate")
    print("-----  ---------  --------  --------------------  --------------------------------------------")
    for part in nodes:
        target = part.get("power_target_w") or part.get("ctdp_min_w") or "?"
        print(
            f"{node_score(part):5.2f}  {display_price(part):>9}  {str(target):>8}  "
            f"{str(part.get('hardware_class', part['category']))[:20]:20}  {part['name']}"
        )
    print("\nScores are cross-platform screening heuristics, not measured inference performance.")
    print("TOPS/TFLOPS are discovery metadata and are deliberately excluded from the screening score.")
    print("Use benchmark data before making a purchase decision.")
    return 0


def bom(parts: list[dict[str, Any]], ids: list[str]) -> int:
    by_id = {part["id"]: part for part in parts}
    counts = Counter(ids)
    total_min = 0.0
    total_max = 0.0
    print("Qty  Part                                         Min       Max")
    print("---  -------------------------------------------  --------  --------")
    for part_id, count in counts.items():
        if part_id not in by_id:
            raise SystemExit(f"Unknown part id: {part_id}")
        part = by_id[part_id]
        if part.get("price_min_usd") is None or part.get("price_max_usd") is None:
            raise SystemExit(
                f"Part {part_id} has unresolved pricing ({part.get('price_status')}); "
                "resolve a current price before including it in a BOM."
            )
        low = float(part["price_min_usd"]) * count
        high = float(part["price_max_usd"]) * count
        total_min += low
        total_max += high
        print(f"{count:>3}  {part['name'][:43]:43}  {money(low):>8}  {money(high):>8}")
    print(f"\nEstimated parts subtotal: {money(total_min)} - {money(total_max)} USD")
    print("Shipping, tax, duties, cables and seller-specific configuration changes are not included.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Low-power distributed LLM cluster hardware planner")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rank", help="Rank heterogeneous LLM candidates with the transparent screening heuristic")
    bom_parser = sub.add_parser("bom", help="Calculate a subtotal from catalog part IDs")
    bom_parser.add_argument("part_ids", nargs="+", help="One or more catalog IDs; repeat an ID for quantity")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    catalog = load_catalog()
    parts = catalog["parts"]
    if args.command == "rank":
        return rank_nodes(parts)
    if args.command == "bom":
        return bom(parts, args.part_ids)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
