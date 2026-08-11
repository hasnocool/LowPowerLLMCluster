# src/lowpower_llm_cluster/refresh_cli.py
from __future__ import annotations

import argparse
import asyncio
import json

from .bom_sourcing import load_bom_config, refresh_bom_market
from .catalog import load_catalog, project_root
from .compatibility import load_builds
from .decision import generate_daily_recommendations, render_daily_recommendations
from .intelligence import generate_change_intelligence, render_daily_change_report
from .manufacturer_discovery import load_discovery_config
from .ops import run_profile, stale_listings, write_current_reports
from .spec_enrichment import load_spec_enrichment_config
from .tco import apply_tco_to_summary, break_even_analysis, load_tco_scenarios, render_tco_report


def _part(part_id: str) -> dict:
    parts = {str(part["id"]): part for part in load_catalog()["parts"]}
    if part_id not in parts: raise KeyError(f"unknown catalog part: {part_id}")
    return parts[part_id]


def _owned(value: str | None) -> list[str]: return [item.strip() for item in (value or "").split(",") if item.strip()]


def _print_builds() -> None:
    payload = load_builds(); print(f"Generated: {payload.get('generated_at') or '-'}")
    for gpu_id, row in sorted((payload.get("gpus") or {}).items()):
        best = row.get("best_build") or {}; compat = best.get("compatibility") or {}; total = best.get("complete_build_acquisition_cad"); price = f"CA${float(total):,.2f}" if total is not None else "unpriced"; unknowns = ",".join(compat.get("unknowns") or []) or "none"; fields = int(best.get("manufacturer_spec_fields") or 0)
        print(f"{gpu_id:<34} {compat.get('status', 'no-build'):<24} {price:<12} spec_fields={fields:<3} unresolved={unknowns}")


def _print_spec_evidence() -> None:
    path = project_root() / "data" / "market" / "spec-evidence.json"; payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"records": []}
    print(f"Generated: {payload.get('generated_at') or '-'}")
    for row in payload.get("records", []):
        enrichment = row.get("spec_enrichment") or {}; fields = row.get("field_evidence") or {}
        print(f"{str(row.get('component') or '-'):<14} {str(enrichment.get('association_origin') or 'curated'):<10} {str(enrichment.get('association_id') or '-'):<36} fields={len(fields):<3} {row.get('title') or ''}")


def _print_manufacturer_associations() -> None:
    path = project_root() / "data" / "market" / "manufacturer-associations.json"; payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"associations": {}}
    rows = list((payload.get("associations") or {}).values())
    print(f"Associations: {len(rows)}")
    for row in sorted(rows, key=lambda item: (str(item.get("manufacturer") or ""), str(item.get("mpn") or ""))):
        score = row.get("identity_score"); score_text = f"{float(score):.3f}" if score is not None else "-"
        print(f"{str(row.get('status') or '-'):<13} {str(row.get('manufacturer') or '-'):<18} {str(row.get('mpn') or '-'):<24} score={score_text:<5} {row.get('source_url') or ''}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous LowPowerLLMCluster market refresh"); sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a named scheduled discovery profile"); run.add_argument("profile")
    stale = sub.add_parser("stale", help="show active listings not observed recently"); stale.add_argument("--hours", type=float, default=48.0)
    sub.add_parser("reports", help="regenerate all current-market buying reports")
    sub.add_parser("refresh-bom", help="fetch online BOM costs, auto-discover manufacturer specs, enrich exact SKUs, and rebuild compatibility combinations")
    sub.add_parser("bom-config", help="show live BOM product-query and compatibility configuration")
    sub.add_parser("spec-config", help="show exact-SKU manufacturer specification associations and extraction policy")
    sub.add_parser("spec-evidence", help="show persisted field-level manufacturer specification evidence")
    sub.add_parser("manufacturer-config", help="show official manufacturer-domain discovery registry and limits")
    sub.add_parser("manufacturer-associations", help="show cached automatically verified manufacturer product-page associations")
    sub.add_parser("compatible-builds", help="show cheapest compatible/provisional complete build per tracked GPU")
    recommendations = sub.add_parser("recommendations", help="regenerate the ownership/TCO-aware decision report"); recommendations.add_argument("--scenario", default="mixed-3yr"); recommendations.add_argument("--ownership", default="new-build"); recommendations.add_argument("--owned", help="comma-separated extra owned component IDs")
    tco = sub.add_parser("tco", help="show ownership-aware complete-node acquisition and operating-cost ranking"); tco.add_argument("--scenario", default="mixed-3yr"); tco.add_argument("--ownership", default="new-build"); tco.add_argument("--owned", help="comma-separated extra owned component IDs")
    breakeven = sub.add_parser("break-even", help="compare two complete-node options and solve break-even thresholds"); breakeven.add_argument("part_a"); breakeven.add_argument("part_b"); breakeven.add_argument("--price-a", type=float, required=True); breakeven.add_argument("--price-b", type=float, required=True); breakeven.add_argument("--scenario", default="mixed-3yr"); breakeven.add_argument("--ownership-a", default="new-build"); breakeven.add_argument("--ownership-b", default="new-build"); breakeven.add_argument("--owned-a", help="comma-separated extra owned component IDs for A"); breakeven.add_argument("--owned-b", help="comma-separated extra owned component IDs for B")
    sub.add_parser("health", help="show latest source health state"); sub.add_parser("budgets", help="show today's source request-budget usage"); sub.add_parser("alerts", help="regenerate and show significant change intelligence"); sub.add_parser("watchlists", help="show configured market watchlists"); sub.add_parser("tco-scenarios", help="show editable TCO, ownership and electricity assumptions")
    args = parser.parse_args()

    if args.command == "run": print(json.dumps(asyncio.run(run_profile(args.profile)), indent=2, sort_keys=True)); return 0
    if args.command == "refresh-bom":
        result = asyncio.run(refresh_bom_market()); summary = {component: {"candidate_count": row.get("candidate_count", 0), "selected": (row.get("selected") or {}).get("landed", {}).get("landed_cad"), "source": (row.get("selected") or {}).get("listing", {}).get("source"), "spec_enrichment": (row.get("selected") or {}).get("spec_enrichment")} for component, row in result.get("components", {}).items()}
        print(json.dumps({"generated_at": result.get("generated_at"), "spec_enriched_candidate_count": result.get("spec_enriched_candidate_count", 0), "components": summary, "compatible_builds": result.get("compatible_builds", {})}, indent=2, sort_keys=True)); return 0
    if args.command == "bom-config": print(json.dumps(load_bom_config(), indent=2, sort_keys=True)); return 0
    if args.command == "spec-config": print(json.dumps(load_spec_enrichment_config(), indent=2, sort_keys=True)); return 0
    if args.command == "spec-evidence": _print_spec_evidence(); return 0
    if args.command == "manufacturer-config": print(json.dumps(load_discovery_config(), indent=2, sort_keys=True)); return 0
    if args.command == "manufacturer-associations": _print_manufacturer_associations(); return 0
    if args.command == "compatible-builds": _print_builds(); return 0
    if args.command == "stale":
        rows = stale_listings(stale_after_hours=args.hours)
        for row in rows: print(f"{row['stale_hours']:7.1f}h  {row['source']:<20} {row['title']}")
        if not rows: print("No active listings exceed the staleness threshold.")
        return 0
    if args.command == "reports": print(json.dumps(write_current_reports(), indent=2, sort_keys=True)); return 0
    if args.command in {"recommendations", "tco"}:
        summary = apply_tco_to_summary(generate_daily_recommendations(), scenario_name=args.scenario, ownership_profile=args.ownership, owned_components=_owned(args.owned)); print(render_daily_recommendations(summary) if args.command == "recommendations" else render_tco_report(summary), end=""); return 0
    if args.command == "break-even":
        result = break_even_analysis(_part(args.part_a), args.price_a, _part(args.part_b), args.price_b, scenario_name=args.scenario, ownership_profile_a=args.ownership_a, ownership_profile_b=args.ownership_b, owned_components_a=_owned(args.owned_a), owned_components_b=_owned(args.owned_b)); print(json.dumps(result, indent=2, sort_keys=True)); return 0
    if args.command == "tco-scenarios": print(json.dumps(load_tco_scenarios(), indent=2, sort_keys=True)); return 0
    if args.command == "health":
        path = project_root() / "data" / "market" / "source-health.json"; payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"sources": {}}
        for source, state in sorted(payload.get("sources", {}).items()): print(f"{source:<22} failures={state.get('consecutive_failures', 0):<3} last_success={state.get('last_success', '-')} last_error={state.get('last_error', '-')}")
        return 0
    if args.command == "budgets":
        path = project_root() / "data" / "market" / "source-budgets.json"; payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"date": None, "sources": {}}; print(f"Budget date: {payload.get('date') or '-'}")
        for source, state in sorted(payload.get("sources", {}).items()): print(f"{source:<14} estimated_requests={state.get('estimated_requests', 0):<5} skipped={state.get('skipped', 0):<5}")
        return 0
    if args.command == "alerts": print(render_daily_change_report(generate_change_intelligence()), end=""); return 0
    if args.command == "watchlists":
        path = project_root() / "data" / "market" / "watchlists.json"; payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"watchlists": []}
        for watch in payload.get("watchlists", []): print(f"{'ON' if watch.get('enabled', True) else 'OFF':3}  {watch.get('id', '-'):<22} {watch.get('description', '')}")
        return 0
    return 2


if __name__ == "__main__": raise SystemExit(main())
