# src/lowpower_llm_cluster/market_cli.py
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .catalog import load_catalog, project_root
from .landed_history import LandedCostHistory, TariffEvidence, make_landed_snapshot
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
from .notifications import adapters_from_config, deliver_alerts
from .owned_host import validate_owned_host
from .pricing import FxTable
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

    landed_snapshot = sub.add_parser(
        "landed-snapshot",
        help="persist an evidence-backed Canadian landed-cost snapshot without rewriting historical FX",
    )
    landed_snapshot.add_argument("listing", type=Path)
    landed_snapshot.add_argument("--province", default="BC")
    landed_snapshot.add_argument("--brokerage-cad", type=float, default=0.0)
    landed_snapshot.add_argument("--tariff-evidence", type=Path)
    landed_snapshot.add_argument("--history-path", type=Path)

    landed_history = sub.add_parser("landed-history", help="show stored landed-CAD snapshots")
    landed_history.add_argument("--source")
    landed_history.add_argument("--source-id")
    landed_history.add_argument("--history-path", type=Path)

    owned_host = sub.add_parser("owned-host", help="validate an already-owned host against GPU compatibility requirements")
    owned_host.add_argument("gpu_part", type=Path, help="JSON catalog-style GPU record")
    owned_host.add_argument("host_facts", type=Path, help="JSON owned-host PCIe/PSU/chassis/cooling facts")
    owned_host.add_argument("--exact-gpu-facts", type=Path, help="optional exact-SKU manufacturer facts")
    owned_host.add_argument("--minimum-psu-headroom-w", type=float, default=100.0)

    notify = sub.add_parser("notify", help="deliver generated alert evidence through configured email/webhook/chat adapters")
    notify.add_argument("--input", type=Path, default=project_root() / "reports" / "current" / "daily-changes.json")
    notify.add_argument("--config", type=Path, default=project_root() / "data" / "market" / "notifications.json")
    notify.add_argument("--maximum-priority", choices=["P1", "P2", "P3", "P4"], default="P4")

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


def _read_json_sync(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


async def _read_json(path: Path) -> object:
    return await asyncio.to_thread(_read_json_sync, path)


def _performance_records(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        records = payload.get("records", [])
        if not isinstance(records, list):
            raise ValueError("performance input 'records' must be an array")
        return records
    raise ValueError("performance input must be an object or array")


def _fx_table_from_payload(payload: object) -> FxTable:
    if not isinstance(payload, dict):
        raise ValueError("FX snapshot must be a JSON object")
    return FxTable(
        target_currency="CAD",
        rates={str(key).upper(): float(value) for key, value in payload.get("rates_to_cad", {}).items()},
        as_of=str(payload.get("as_of") or "unknown"),
    )


def _tariff_evidence_from_payload(payload: object | None) -> TariffEvidence | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("tariff evidence must be a JSON object")
    return TariffEvidence(
        hs_code=str(payload["hs_code"]),
        duty_rate=float(payload["duty_rate"]),
        source_url=str(payload["source_url"]),
        verified_on=str(payload["verified_on"]),
        origin_country=str(payload["origin_country"]) if payload.get("origin_country") else None,
        description=str(payload.get("description") or ""),
        confidence=str(payload.get("confidence") or "medium"),
    )


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


async def _landed_snapshot(args: argparse.Namespace) -> int:
    payload, fx_payload, tariff_payload = await asyncio.gather(
        _read_json(args.listing),
        _read_json(project_root() / "data" / "market" / "fx-cad.json"),
        _read_json(args.tariff_evidence) if args.tariff_evidence else asyncio.sleep(0, result=None),
    )
    if not isinstance(payload, dict):
        raise ValueError("listing input must be a JSON object")
    listing = Listing.from_mapping(payload, str(payload.get("source", "manual")))
    snapshot = make_landed_snapshot(
        source=listing.source,
        source_id=listing.source_id,
        listing_url=listing.url,
        listing_observed_at=listing.observed_at,
        item_price=listing.price,
        source_currency=listing.currency,
        shipping=listing.shipping or 0.0,
        shipping_currency=listing.shipping_currency,
        fx=_fx_table_from_payload(fx_payload),
        province=args.province,
        brokerage_cad=args.brokerage_cad,
        tariff=_tariff_evidence_from_payload(tariff_payload),
    )
    history = LandedCostHistory(args.history_path)
    added = await history.append(snapshot)
    print(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True))
    print(f"\n{'Stored' if added else 'Already stored'} snapshot {snapshot.snapshot_id}.")
    print("Planning evidence only: verify origin, exact HS classification, tax treatment, carrier brokerage and seller terms before purchase.")
    return 0


async def _landed_history(args: argparse.Namespace) -> int:
    rows = await LandedCostHistory(args.history_path).snapshots(source=args.source, source_id=args.source_id)
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


async def _owned_host(args: argparse.Namespace) -> int:
    gpu_payload, host_payload, exact_payload = await asyncio.gather(
        _read_json(args.gpu_part),
        _read_json(args.host_facts),
        _read_json(args.exact_gpu_facts) if args.exact_gpu_facts else asyncio.sleep(0, result=None),
    )
    if not isinstance(gpu_payload, dict) or not isinstance(host_payload, dict):
        raise ValueError("GPU and host inputs must be JSON objects")
    if exact_payload is not None and not isinstance(exact_payload, dict):
        raise ValueError("exact GPU facts must be a JSON object")
    result = validate_owned_host(
        gpu_payload,
        host_payload,
        exact_gpu_facts=exact_payload,
        minimum_psu_headroom_w=args.minimum_psu_headroom_w,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 1 if result.status == "incompatible" else 0


async def _notify(args: argparse.Namespace) -> int:
    if not args.config.exists():
        raise SystemExit(f"notification config not found: {args.config}")
    if not args.input.exists():
        raise SystemExit(f"alert evidence not found: {args.input}")
    config, summary = await asyncio.gather(_read_json(args.config), _read_json(args.input))
    if not isinstance(config, dict) or not isinstance(summary, dict):
        raise ValueError("notification config and alert input must be JSON objects")
    adapters = adapters_from_config(config)
    if not adapters:
        print("No enabled notification adapters have usable environment-backed credentials/URLs.")
        return 0
    deliveries = await deliver_alerts(summary.get("alerts", []), adapters, maximum_priority=args.maximum_priority)
    for delivery in deliveries:
        state = "OK" if delivery.ok else "FAIL"
        suffix = f" — {delivery.error}" if delivery.error else ""
        print(f"{delivery.adapter:<20} {state:<4} {delivery.alert_fingerprint}{suffix}")
    failures = sum(1 for delivery in deliveries if not delivery.ok)
    print(f"Delivered {len(deliveries) - failures}/{len(deliveries)} notification attempts.")
    return 1 if failures else 0


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
    if args.command == "landed-snapshot":
        return asyncio.run(_landed_snapshot(args))
    if args.command == "landed-history":
        return asyncio.run(_landed_history(args))
    if args.command == "owned-host":
        return asyncio.run(_owned_host(args))
    if args.command == "notify":
        return asyncio.run(_notify(args))
    if args.command == "refresh-fx":
        return asyncio.run(_refresh_fx(args))
    if args.command == "ingest-performance":
        payload = json.loads(args.file.read_text(encoding="utf-8"))
        result = ingest_performance(_performance_records(payload))
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
