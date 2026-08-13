from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
from typing import Any


def hardware_class() -> str:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return f"github-hosted-{platform.system().lower()}-{platform.machine().lower()}"
    return f"local-{platform.system().lower()}-{platform.machine().lower()}"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check synthetic discovery performance against a hardware-class baseline")
    parser.add_argument("--baselines", default="benchmarks/hardware-class-baselines.json")
    parser.add_argument("--current", required=True)
    parser.add_argument("--hardware-class")
    args = parser.parse_args()
    name = args.hardware_class or hardware_class()
    baselines = load(Path(args.baselines)).get("classes", {})
    baseline = baselines.get(name)
    if baseline is None:
        print(f"No committed hardware-class baseline for {name}; generic regression gate remains authoritative.")
        return 0
    current = load(Path(args.current)).get("results", [])
    by_count = {int(item["observations"]): item for item in current}
    failures: list[str] = []
    for expected in baseline.get("results", []):
        count = int(expected["observations"])
        actual = by_count.get(count)
        if actual is None:
            failures.append(f"missing {count}-observation run")
            continue
        if float(actual["observations_per_s"]) < float(expected["min_observations_per_s"]):
            failures.append(f"{count}: throughput {actual['observations_per_s']} below {expected['min_observations_per_s']}")
        if float(actual["peak_rss_mb"]) > float(expected["max_peak_rss_mb"]):
            failures.append(f"{count}: RSS {actual['peak_rss_mb']} above {expected['max_peak_rss_mb']}")
        if float(actual["p95_event_loop_lag_ms"]) > float(expected["max_p95_event_loop_lag_ms"]):
            failures.append(f"{count}: loop lag {actual['p95_event_loop_lag_ms']} above {expected['max_p95_event_loop_lag_ms']}")
    if failures:
        for item in failures:
            print("FAIL:", item)
        return 1
    print(f"Hardware-class baseline passed for {name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
