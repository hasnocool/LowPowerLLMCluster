# src/lowpower_llm_cluster/refresh_cli.py
from __future__ import annotations

import argparse
import asyncio
import json

from .catalog import project_root
from .decision import generate_daily_recommendations, render_daily_recommendations
from .intelligence import generate_change_intelligence, render_daily_change_report
from .ops import run_profile, stale_listings, write_current_reports
from .tco import apply_tco_to_summary, load_tco_scenarios, render_tco_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous LowPowerLLMCluster market refresh")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a named scheduled discovery profile")
    run.add_argument("profile")
    stale = sub.add_parser("stale", help="show active listings not observed recently")
    stale.add_argument("--hours", type=float, default=48.0)
    sub.add_parser("reports", help="regenerate all current-market buying reports")
    recommendations = sub.add_parser("recommendations", help="regenerate the TCO-aware Buy/Watch/Ignore/Experimental decision report")
    recommendations.add_argument("--scenario", default="mixed-3yr")
    tco = sub.add_parser("tco", help="show complete-node acquisition and operating-cost ranking")
    tco.add_argument("--scenario", default="mixed-3yr")
    sub.add_parser("health", help="show latest source health state")
    sub.add_parser("budgets", help="show today's source request-budget usage")
    sub.add_parser("alerts", help="regenerate and show significant change intelligence")
    sub.add_parser("watchlists", help="show configured market watchlists")
    sub.add_parser("tco-scenarios", help="show editable TCO component and electricity assumptions")
    args = parser.parse_args()

    if args.command == "run":
        print(json.dumps(asyncio.run(run_profile(args.profile)), indent=2, sort_keys=True)); return 0
    if args.command == "stale":
        rows = stale_listings(stale_after_hours=args.hours)
        for row in rows: print(f"{row['stale_hours']:7.1f}h  {row['source']:<20} {row['title']}")
        if not rows: print("No active listings exceed the staleness threshold.")
        return 0
    if args.command == "reports":
        print(json.dumps(write_current_reports(), indent=2, sort_keys=True)); return 0
    if args.command in {"recommendations", "tco"}:
        summary = apply_tco_to_summary(generate_daily_recommendations(), scenario_name=args.scenario)
        print(render_daily_recommendations(summary) if args.command == "recommendations" else render_tco_report(summary), end="")
        return 0
    if args.command == "tco-scenarios":
        print(json.dumps(load_tco_scenarios(), indent=2, sort_keys=True)); return 0
    if args.command == "health":
        path = project_root() / "data" / "market" / "source-health.json"; payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"sources": {}}
        for source, state in sorted(payload.get("sources", {}).items()): print(f"{source:<22} failures={state.get('consecutive_failures', 0):<3} last_success={state.get('last_success', '-')} last_error={state.get('last_error', '-')}")
        return 0
    if args.command == "budgets":
        path = project_root() / "data" / "market" / "source-budgets.json"; payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"date": None, "sources": {}}
        print(f"Budget date: {payload.get('date') or '-'}")
        for source, state in sorted(payload.get("sources", {}).items()): print(f"{source:<14} estimated_requests={state.get('estimated_requests', 0):<5} skipped={state.get('skipped', 0):<5}")
        return 0
    if args.command == "alerts":
        print(render_daily_change_report(generate_change_intelligence()), end=""); return 0
    if args.command == "watchlists":
        path = project_root() / "data" / "market" / "watchlists.json"; payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"watchlists": []}
        for watch in payload.get("watchlists", []):
            state = "ON" if watch.get("enabled", True) else "OFF"; print(f"{state:3}  {watch.get('id', '-'):<22} {watch.get('description', '')}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
