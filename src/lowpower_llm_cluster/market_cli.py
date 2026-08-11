# src/lowpower_llm_cluster/market_cli.py
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .catalog import load_catalog
from .market import JsonFeedAdapter, Listing, append_price_observations, discover_all, ingest_performance, landed_cost_cad, load_fx, price_history


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LowPowerLLMCluster market intelligence")
    sub = parser.add_subparsers(dest="command", required=True)
    discover = sub.add_parser("discover", help="ingest product listings from one or more discovery feeds")
    discover.add_argument("--feed", action="append", type=Path, required=True)
    discover.add_argument("--query", action="append", default=[])
    history = sub.add_parser("history", help="show price history for a catalog part")
    history.add_argument("part_id")
    landed = sub.add_parser("landed", help="estimate Canadian landed cost for a listing JSON object")
    landed.add_argument("listing", type=Path)
    landed.add_argument("--tax-rate", type=float, default=0.12)
    landed.add_argument("--duty-rate", type=float, default=0.0)
    landed.add_argument("--brokerage-cad", type=float, default=0.0)
    perf = sub.add_parser("ingest-performance", help="ingest sourced vendor/community performance records")
    perf.add_argument("file", type=Path)
    return parser


async def _discover(args: argparse.Namespace) -> int:
    parts = load_catalog()["parts"]
    adapters = [JsonFeedAdapter(path, name=f"json:{path.stem}") for path in args.feed]
    listings = await discover_all(adapters, args.query)
    result = await asyncio.to_thread(append_price_observations, listings, parts)
    print(f"Discovered {len(listings)} listings; added {result['added']} price observations ({result['total']} total).")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "discover":
        return asyncio.run(_discover(args))
    if args.command == "history":
        rows = price_history(args.part_id)
        print("Observed                  Price      Source              Confidence  Listing")
        print("------------------------  ---------  ------------------  ----------  --------------------------------")
        for row in rows:
            confidence = row.get("configuration_confidence", {}).get("label", "unknown")
            print(f"{row['observed_at'][:24]:24}  {row['price']:7.2f} {row['currency']:3}  {row['source'][:18]:18}  {confidence:10}  {row['title'][:32]}")
        return 0
    if args.command == "landed":
        payload = json.loads(args.listing.read_text(encoding="utf-8"))
        listing = Listing.from_mapping(payload, str(payload.get("source", "manual")))
        result = landed_cost_cad(listing, load_fx(), tax_rate=args.tax_rate, duty_rate=args.duty_rate, brokerage_cad=args.brokerage_cad)
        for key, value in result.items():
            print(f"{key:15}: ${value:,.2f} CAD")
        print("Estimate only: verify tax, tariff classification, courier brokerage and seller shipping before purchase.")
        return 0
    if args.command == "ingest-performance":
        payload = json.loads(args.file.read_text(encoding="utf-8"))
        records = payload.get("records", payload if isinstance(payload, list) else [])
        result = ingest_performance(records)
        print(f"Added {result['added']} performance records ({result['total']} total).")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
