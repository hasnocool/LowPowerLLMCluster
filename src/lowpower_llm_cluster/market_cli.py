# src/lowpower_llm_cluster/market_cli.py
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .catalog import load_catalog, project_root
from .market import (
    JsonFeedAdapter,
    Listing,
    aggregate_compatible_performance,
    append_price_observations,
    discover_with_status,
    ingest_performance,
    landed_cost_cad,
    load_fx,
    price_history,
    refresh_bank_of_canada_fx,
    update_listing_presence,
)
from .reports import build_report_rows, named_reports, render_report
from .sources import DigiKeyAdapter, EbayBrowseAdapter, ManufacturerJsonLdAdapter, MouserAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LowPowerLLMCluster market intelligence")
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover", help="discover products from fixture and/or live structured sources")
    discover.add_argument("--feed", action="append", type=Path, default=[])
    discover.add_argument("--source", action="append", choices=["manufacturer", "mouser", "digikey", "ebay"], default=[])
    discover.add_argument("--query", action="append", default=[])
    discover.add_argument("--sources-config", type=Path, default=project_root() / "data" / "market" / "sources.json")

    history = sub.add_parser("history", help="show price history for a catalog part")
    history.add_argument("part_id")

    landed = sub.add_parser("landed", help="estimate Canadian landed cost for a listing JSON object")
    landed.add_argument("listing", type=Path)
    landed.add_argument("--tax-rate", type=float, default=0.12)
    landed.add_argument("--duty-rate", type=float, default=0.0)
    landed.add_argument("--brokerage-cad", type=float, default=0.0)

    fx = sub.add_parser("refresh-fx", help="refresh sourced CAD exchange-rate snapshots from Bank of Canada")
    fx.add_argument("--currency", action="append", default=[])

    perf = sub.add_parser("ingest-performance", help="ingest sourced vendor/community performance records")
    perf.add_argument("file", type=Path)

    aggregate = sub.add_parser("aggregate-performance", help="aggregate only compatible measured benchmark records")
    aggregate.add_argument("part_id")
    aggregate.add_argument("--include-estimates", action="store_true")

    report = sub.add_parser("report", help="render CAD buying reports from live market evidence plus labelled catalog fallbacks")
    report.add_argument("name", choices=["under-100", "under-250", "under-500", "32gb-plus", "low-power", "weird-bargains", "eol-bargains", "measured-evidence", "all"])
    report.add_argument("--tax-rate", type=float, default=0.12, help="planning tax rate; default 12%% for a BC-style planning view")
    report.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def _load_sources_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


async def _discover(args: argparse.Namespace) -> int:
    parts = load_catalog()["parts"]
    adapters = [JsonFeedAdapter(path, name=f"json:{path.stem}") for path in args.feed]
    config = _load_sources_config(args.sources_config)
    selected = set(args.source)
    if "manufacturer" in selected:
        adapters.append(ManufacturerJsonLdAdapter(list(config.get("manufacturer_jsonld_urls", []))))
    if "mouser" in selected:
        adapters.append(MouserAdapter())
    if "digikey" in selected:
        adapters.append(DigiKeyAdapter())
    if "ebay" in selected:
        adapters.append(EbayBrowseAdapter())
    if not adapters:
        raise SystemExit("No discovery sources selected. Use --feed and/or --source manufacturer|mouser|digikey|ebay.")

    listings, statuses = await discover_with_status(adapters, args.query)
    successful_sources = [row["source"] for row in statuses if row["ok"]]
    prices = await asyncio.to_thread(append_price_observations, listings, parts)
    presence = await asyncio.to_thread(update_listing_presence, listings, successful_sources, args.query)

    for row in statuses:
        if row["ok"]:
            print(f"{row['source']:<22} OK   {row['count']:>4} listings")
        else:
            print(f"{row['source']:<22} FAIL      {row['error']}")
    print(f"\nDiscovered {len(listings)} unique listings; added {prices['added']} price observations ({prices['total']} total).")
    print(f"Presence events: {presence['discovered']} discovered, {presence['reappeared']} reappeared, {presence['disappeared']} disappeared.")
    disabled = [adapter.name for adapter in adapters if not bool(getattr(adapter, "enabled", True))]
    if disabled:
        print(f"Credential-disabled sources skipped: {', '.join(disabled)}")
    return 0


async def _refresh_fx(args: argparse.Namespace) -> int:
    snapshot = await refresh_bank_of_canada_fx(args.currency or None)
    print(f"Bank of Canada FX snapshot: {snapshot['as_of']}")
    for currency, value in sorted(snapshot["rates_to_cad"].items()):
        print(f"1 {currency} = {value:g} CAD")
    print(f"Source: {snapshot['source_url']}")
    return 0


def _report(args: argparse.Namespace) -> int:
    rows = build_report_rows(load_catalog()["parts"], tax_rate=args.tax_rate)
    reports = named_reports(rows)
    selected = reports if args.name == "all" else {args.name: reports[args.name]}
    if args.json:
        print(json.dumps(selected, indent=2, sort_keys=True))
        return 0
    for index, (name, values) in enumerate(selected.items()):
        if index:
            print()
        title = name.replace("-", " ").title()
        print(render_report(values, title))
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "discover":
        return asyncio.run(_discover(args))
    if args.command == "history":
        rows = price_history(args.part_id)
        print("Observed                  Price      Source              SKU conf    Seller conf  Listing")
        print("------------------------  ---------  ------------------  ----------  -----------  --------------------------------")
        for row in rows:
            sku_conf = row.get("configuration_confidence", {}).get("label", "unknown")
            seller_conf = row.get("seller_confidence", {}).get("label", "unknown")
            print(f"{row['observed_at'][:24]:24}  {row['price']:7.2f} {row['currency']:3}  {row['source'][:18]:18}  {sku_conf:10}  {seller_conf:11}  {row['title'][:32]}")
        return 0
    if args.command == "landed":
        payload = json.loads(args.listing.read_text(encoding="utf-8"))
        listing = Listing.from_mapping(payload, str(payload.get("source", "manual")))
        result = landed_cost_cad(listing, load_fx(), tax_rate=args.tax_rate, duty_rate=args.duty_rate, brokerage_cad=args.brokerage_cad)
        for key, value in result.items():
            print(f"{key:15}: ${value:,.2f} CAD")
        print("Estimate only: verify tax, tariff classification, courier brokerage and seller shipping before purchase.")
        return 0
    if args.command == "refresh-fx":
        return asyncio.run(_refresh_fx(args))
    if args.command == "ingest-performance":
        payload = json.loads(args.file.read_text(encoding="utf-8"))
        records = payload.get("records", payload if isinstance(payload, list) else [])
        result = ingest_performance(records)
        print(f"Added {result['added']} performance records ({result['total']} total).")
        return 0
    if args.command == "aggregate-performance":
        groups = aggregate_compatible_performance(args.part_id, measured_only=not args.include_estimates)
        print("Count  Median       Range                  Confidence  Model / runtime / workload")
        print("-----  -----------  ---------------------  ----------  ------------------------------------------")
        for group in groups:
            value_range = f"{group['min']:g}..{group['max']:g} {group['unit']}"
            label = f"{group['model']} / {group['runtime']} / {group['workload']}"
            print(f"{group['count']:5}  {group['median']:11g}  {value_range:21}  {group['mean_confidence']:10.3f}  {label}")
        if not groups:
            print("No compatible records found.")
        return 0
    if args.command == "report":
        return _report(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
