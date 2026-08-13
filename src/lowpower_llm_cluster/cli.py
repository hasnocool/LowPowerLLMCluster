# src/lowpower_llm_cluster/cli.py
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .catalog import exact_sku_confidence, llm_candidates, load_catalog, midpoint_price
from .catalog_refresh import run_discovery_config
from .dashboard import render_catalog_dashboard
from .evidence import board_memory_evidence, memory_basis, performance_evidence, verified_memory_gb
from .estimates import MODEL_PRESETS, model_fit_preset, model_fit_screen
from .performance import confidence_aware_range, load_performance_records, separate_workload_records
from .pricing import FxTable, estimate_canada_landed_cost
from .reports import named_reports, published_power_boundary
from .scoring import catalog_score


def money(value: float) -> str:
    return f"${value:,.2f}"


def display_price(part: dict[str, Any]) -> str:
    mid = midpoint_price(part)
    return money(mid) if mid is not None else "unknown"


def display_memory(part: dict[str, Any]) -> str:
    memory, basis, _ = memory_basis(part)
    if memory is None:
        return "unknown"
    suffix = {
        "included": " included", "fixed": " fixed", "configurable_max": " max",
        "cpu_theoretical_max_unverified_on_board": " CPU-max*",
    }.get(basis, "")
    return f"{memory:g}GB{suffix}"


def list_parts(parts: list[dict[str, Any]], args: argparse.Namespace) -> int:
    rows = list(parts)
    if args.llm_only:
        rows = llm_candidates(rows)
    if args.category:
        rows = [p for p in rows if p.get("category") == args.category]
    if args.max_price is not None:
        rows = [p for p in rows if midpoint_price(p) is not None and midpoint_price(p) <= args.max_price]
    if args.min_memory is not None:
        rows = [p for p in rows if (verified_memory_gb(p) or 0) >= args.min_memory]
    if getattr(args, "min_sku_confidence", None) is not None:
        rows = [p for p in rows if exact_sku_confidence(p) >= args.min_sku_confidence]
    if args.sort == "price":
        rows.sort(key=lambda p: (midpoint_price(p) is None, midpoint_price(p) or float("inf")))
    elif args.sort == "memory":
        rows.sort(key=lambda p: memory_basis(p)[0] or 0, reverse=True)
    else:
        rows.sort(key=catalog_score, reverse=True)

    print("Score  Price      Memory          SKU     Category                 Product")
    print("-----  ---------  --------------  ------  -----------------------  ------------------------------------------")
    for p in rows:
        score = catalog_score(p) if p.get("llm_candidate", False) else 0.0
        print(f"{score:5.2f}  {display_price(p):>9}  {display_memory(p):14}  {exact_sku_confidence(p):.2f}   {str(p['category'])[:23]:23}  {p['name']}")
    print("\n* CPU-max means the processor specification, not a verified board/RAM configuration.")
    return 0


def rank_nodes(parts: list[dict[str, Any]]) -> int:
    nodes = llm_candidates(parts)
    nodes.sort(key=catalog_score, reverse=True)
    print("Catalog  Mid price  Memory          Risk    Candidate")
    print("-------  ---------  --------------  ------  --------------------------------------------")
    for part in nodes:
        print(f"{catalog_score(part):7.2f}  {display_price(part):>9}  {display_memory(part):14}  {str(part.get('risk_level', '?')):6}  {part['name']}")
    print("\nThis is a catalog/buying shortlist score, NOT estimated inference performance.")
    print("TOPS, TFLOPS and invented tokens/sec are not inputs. Use sourced performance evidence separately.")
    return 0


def show_part(parts: list[dict[str, Any]], part_id: str) -> int:
    by_id = {p["id"]: p for p in parts}
    if part_id not in by_id:
        raise SystemExit(f"Unknown part id: {part_id}")
    p = by_id[part_id]
    evidence = performance_evidence(p)
    memory, basis, _ = memory_basis(p)
    board_memory = board_memory_evidence(p)
    power, power_scope = published_power_boundary(p)
    fields = [
        ("ID", p["id"]), ("Product", p["name"]), ("Category", p["category"]),
        ("Price", display_price(p)), ("Price status", p.get("price_status", "unknown")),
        ("Memory", f"{memory:g} GB" if memory is not None else "unknown"),
        ("Memory basis", basis), ("Board RAM source", board_memory.get("source_url") or "unlinked/unknown"),
        ("SKU confidence", f"{exact_sku_confidence(p):.3f}"),
        ("Power boundary", f"{power:g} W" if power is not None else "unknown"), ("Power scope", power_scope),
        ("Software maturity", p.get("software_maturity", "unknown")),
        ("Risk", p.get("risk_level", "unknown")), ("LLM support", p.get("llm_support", "unknown")),
        ("Performance source", evidence["source_type"]), ("Performance confidence", evidence["confidence"]),
        ("URL", p.get("url", "")), ("Verified", p.get("verified_on", "")),
    ]
    width = max(len(k) for k, _ in fields)
    for k, v in fields:
        print(f"{k:<{width}} : {v}")
    print(f"\nWhy it is here:\n{p.get('plain_language', '')}")
    if evidence["notes"]:
        print(f"\nPerformance evidence:\n{evidence['notes']}")
    return 0


def fit(parts: list[dict[str, Any]], args: argparse.Namespace) -> int:
    by_id = {p["id"]: p for p in parts}
    if args.part_id not in by_id:
        raise SystemExit(f"Unknown part id: {args.part_id}")
    if args.preset:
        result = model_fit_preset(by_id[args.part_id], args.preset, runtime_headroom_fraction=args.runtime_headroom, extra_headroom_gb=args.extra_headroom_gb)
    else:
        if args.params_b is None or args.bits is None:
            raise SystemExit("fit requires --preset or both --params-b and --bits")
        result = model_fit_screen(by_id[args.part_id], params_b=args.params_b, bits_per_weight=args.bits, runtime_headroom_fraction=args.runtime_headroom, extra_headroom_gb=args.extra_headroom_gb)
    print(f"Hardware               : {args.part_id}")
    if result.get("preset"):
        print(f"Model preset           : {result['preset']} ({result['preset_description']})")
    print(f"Model parameters       : {result['params_b']}B")
    print(f"Nominal bits/weight    : {result['bits_per_weight']}")
    print(f"Estimated weights only : {result['weights_only_gb']} GB")
    print(f"Planning memory target : {result['planning_memory_gb']} GB")
    print(f"Catalog memory         : {result['catalog_memory_gb'] if result['catalog_memory_gb'] is not None else 'unknown'} GB")
    print(f"Memory evidence        : {result['memory_basis']}")
    print(f"Capacity screen        : {result['status']}")
    print(f"\n{result['warning']}")
    return 0


def bom(parts: list[dict[str, Any]], ids: list[str]) -> int:
    by_id = {part["id"]: part for part in parts}
    counts = Counter(ids)
    total_min = total_max = 0.0
    print("Qty  Part                                         Min       Max")
    print("---  -------------------------------------------  --------  --------")
    for part_id, count in counts.items():
        if part_id not in by_id:
            raise SystemExit(f"Unknown part id: {part_id}")
        part = by_id[part_id]
        if part.get("price_min_usd") is None or part.get("price_max_usd") is None:
            raise SystemExit(f"Part {part_id} has unresolved pricing ({part.get('price_status')}).")
        low = float(part["price_min_usd"]) * count
        high = float(part["price_max_usd"]) * count
        total_min += low
        total_max += high
        print(f"{count:>3}  {part['name'][:43]:43}  {money(low):>8}  {money(high):>8}")
    print(f"\nEstimated parts subtotal: {money(total_min)} - {money(total_max)} USD")
    print("Shipping, tax, duties, memory upgrades, cooling and host requirements may be additional.")
    return 0


def report(parts: list[dict[str, Any]], args: argparse.Namespace) -> int:
    reports = named_reports(parts)
    if args.name == "all":
        names = list(reports)
    elif args.name in reports:
        names = [args.name]
    else:
        raise SystemExit(f"Unknown report {args.name!r}. Choices: all, {', '.join(reports)}")
    if args.json:
        print(json.dumps({name: reports[name] for name in names}, indent=2))
        return 0
    for name in names:
        print(f"\n{name.replace('_', ' ').title()}")
        print("=" * len(name))
        for part in reports[name]:
            power, scope = published_power_boundary(part)
            power_text = f"{power:g}W {scope}" if power is not None else "power unknown"
            print(f"{catalog_score(part):5.2f}  {display_price(part):>9}  {display_memory(part):14}  {power_text:38}  {part['name']}")
    return 0


def landed_cost(args: argparse.Namespace) -> int:
    fx = FxTable(target_currency="CAD", rates={args.currency.upper(): args.fx_rate}, as_of=args.fx_as_of)
    estimate = estimate_canada_landed_cost(
        item_price=args.price, source_currency=args.currency, fx=fx, province=args.province,
        shipping=args.shipping, shipping_currency=args.currency, duty_rate=args.duty_rate,
        brokerage_cad=args.brokerage_cad, tax_rate=args.tax_rate,
    )
    for key, value in estimate.to_dict().items():
        if key == "assumptions":
            continue
        print(f"{key:16}: {value}")
    print("\nAssumptions:")
    for assumption in estimate.assumptions:
        print(f"- {assumption}")
    return 0


def performance_range(args: argparse.Namespace) -> int:
    records = load_performance_records(args.path)
    records = [record for record in records if (not args.hardware_id or record.hardware_id == args.hardware_id) and (not args.model or record.model == args.model) and (not args.runtime or record.runtime == args.runtime) and (not args.workload_class or record.workload_class == args.workload_class) and (not args.metric or record.metric_name == args.metric)]
    buckets = separate_workload_records(records)
    selected = buckets[args.family]
    try:
        result = confidence_aware_range(selected) if selected else None
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2) if result else "No confidence range: at least two independent compatible measured sources are required.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Catalog-first low-power LLM hardware research and buying planner")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rank", help="Rank LLM-capable catalog candidates using a non-performance shopping heuristic")
    lp = sub.add_parser("list", help="Browse/filter the hardware catalog")
    lp.add_argument("--category")
    lp.add_argument("--max-price", type=float)
    lp.add_argument("--min-memory", type=float, help="minimum included/fixed or verified board-max memory; CPU theoretical max does not satisfy this filter")
    lp.add_argument("--min-sku-confidence", type=float)
    lp.add_argument("--llm-only", action="store_true")
    lp.add_argument("--sort", choices=["score", "price", "memory"], default="score")
    sp = sub.add_parser("show", help="Show one catalog record with evidence/provenance")
    sp.add_argument("part_id")
    fp = sub.add_parser("fit", help="Conservative model-weight capacity screen; does not estimate tokens/sec")
    fp.add_argument("part_id")
    fp.add_argument("--preset", choices=sorted(MODEL_PRESETS))
    fp.add_argument("--params-b", type=float)
    fp.add_argument("--bits", type=float)
    fp.add_argument("--runtime-headroom", type=float, default=0.12)
    fp.add_argument("--extra-headroom-gb", type=float, default=2.0)
    bp = sub.add_parser("bom", help="Calculate a subtotal from catalog part IDs")
    bp.add_argument("part_ids", nargs="+")

    rp = sub.add_parser("report", help="Generate budget/high-memory/low-power/weird/EOL catalog reports")
    rp.add_argument("name", nargs="?", default="all")
    rp.add_argument("--json", action="store_true")

    dp = sub.add_parser("dashboard", help="Generate a self-contained interactive HTML catalog dashboard")
    dp.add_argument("--output", default="results/catalog-dashboard.html")

    cp = sub.add_parser("landed-cost", help="Estimate a purchase in CAD using an explicit FX snapshot and assumptions")
    cp.add_argument("--price", type=float, required=True)
    cp.add_argument("--currency", default="USD")
    cp.add_argument("--fx-rate", type=float, required=True, help="CAD per one source-currency unit")
    cp.add_argument("--fx-as-of", required=True, help="date/time label for the supplied FX rate")
    cp.add_argument("--province", default="BC")
    cp.add_argument("--shipping", type=float, default=0.0)
    cp.add_argument("--duty-rate", type=float, default=0.0)
    cp.add_argument("--brokerage-cad", type=float, default=0.0)
    cp.add_argument("--tax-rate", type=float)

    discover = sub.add_parser("discover", help="Run configured asynchronous JSON/JSON-LD product/source adapters and persist history")
    discover.add_argument("--config", required=True)
    discover.add_argument("--history", default="results/catalog-history.sqlite3")
    discover.add_argument("--output", default="results/discovery-latest.json")

    perf = sub.add_parser("performance-range", help="Show a confidence-aware measured range when independent compatible sources exist")
    perf.add_argument("path")
    perf.add_argument("--family", choices=["llm", "specialist"], default="llm")
    perf.add_argument("--hardware-id")
    perf.add_argument("--model")
    perf.add_argument("--runtime")
    perf.add_argument("--workload-class")
    perf.add_argument("--metric")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    parts = load_catalog()["parts"]
    if args.command == "rank": return rank_nodes(parts)
    if args.command == "list": return list_parts(parts, args)
    if args.command == "show": return show_part(parts, args.part_id)
    if args.command == "fit": return fit(parts, args)
    if args.command == "bom": return bom(parts, args.part_ids)
    if args.command == "report": return report(parts, args)
    if args.command == "dashboard":
        output = render_catalog_dashboard(parts, Path(args.output))
        print(output)
        return 0
    if args.command == "landed-cost": return landed_cost(args)
    if args.command == "discover":
        payload = asyncio.run(run_discovery_config(args.config, history_path=args.history, output_path=args.output))
        print(json.dumps({key: payload[key] for key in ("run_id", "observation_count", "errors", "changes")}, indent=2))
        return 0 if not payload["errors"] else 1
    if args.command == "performance-range": return performance_range(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
