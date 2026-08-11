# src/lowpower_llm_cluster/refresh_cli.py
from __future__ import annotations

import argparse
import asyncio
import json

from .catalog import project_root
from .ops import run_profile, stale_listings, write_current_reports


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous LowPowerLLMCluster market refresh")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a named scheduled discovery profile")
    run.add_argument("profile")
    stale = sub.add_parser("stale", help="show active listings not observed recently")
    stale.add_argument("--hours", type=float, default=48.0)
    sub.add_parser("reports", help="regenerate all current-market buying reports")
    sub.add_parser("health", help="show latest source health state")
    args = parser.parse_args()

    if args.command == "run":
        result = asyncio.run(run_profile(args.profile))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "stale":
        rows = stale_listings(stale_after_hours=args.hours)
        for row in rows:
            print(f"{row['stale_hours']:7.1f}h  {row['source']:<20} {row['title']}")
        if not rows:
            print("No active listings exceed the staleness threshold.")
        return 0
    if args.command == "reports":
        print(json.dumps(write_current_reports(), indent=2, sort_keys=True))
        return 0
    if args.command == "health":
        path = project_root() / "data" / "market" / "source-health.json"
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"sources": {}}
        for source, state in sorted(payload.get("sources", {}).items()):
            print(f"{source:<22} failures={state.get('consecutive_failures', 0):<3} last_success={state.get('last_success', '-')} last_error={state.get('last_error', '-')}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
