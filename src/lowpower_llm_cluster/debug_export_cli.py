from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from .debug_artifacts import export_repo_debug_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a sanitized LowPowerLLMCluster debug bundle that can be committed to GitHub")
    parser.add_argument("--debug-dir", default="results/debug")
    parser.add_argument("--history", default="results/catalog-history.sqlite3")
    parser.add_argument("--config", default="config/discovery.example.json")
    parser.add_argument("--event-log", default="results/events.jsonl")
    parser.add_argument("--latest-output", default="results/discovery-latest.json")
    parser.add_argument("--destination", default="debug-artifacts")
    parser.add_argument("--name", help="bundle directory name; defaults to UTC timestamp")
    parser.add_argument("--tail-lines", type=int, default=500)
    args = parser.parse_args()
    if args.tail_lines < 1:
        parser.error("--tail-lines must be >= 1")
    name = args.name or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = Path(args.destination).expanduser() / name
    result = export_repo_debug_bundle(
        destination=destination,
        debug_dir=args.debug_dir,
        history=args.history,
        config=args.config,
        event_log=args.event_log,
        latest_output=args.latest_output,
        tail_lines=args.tail_lines,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
