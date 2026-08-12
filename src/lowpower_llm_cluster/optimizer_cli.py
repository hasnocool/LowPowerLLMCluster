# src/lowpower_llm_cluster/optimizer_cli.py
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .normalized_scoring import TaskRequirements, WORKLOAD_PROFILES, pareto_frontier, rank_devices
from .scoring_inputs import benchmark_result_to_device, merge_device_records


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_devices(paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        data = _load_json(path)
        items = data if isinstance(data, list) else data.get("devices", data.get("results", [data]))
        if not isinstance(items, list):
            raise SystemExit(f"Unsupported input shape in {path}")
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("schema_version") == 2 and "hardware_id" in item and "metrics" in item:
                records.append(benchmark_result_to_device(item))
            else:
                records.append(item)
    return merge_device_records(records)


def requirements_from_args(args: argparse.Namespace) -> TaskRequirements:
    return TaskRequirements(
        workload=args.workload,
        model_params_b=args.model_params_b,
        bits_per_weight=args.bits,
        context_tokens=args.context_tokens,
        min_decode_tokens_s=args.min_decode,
        min_prefill_tokens_s=args.min_prefill,
        max_system_power_w=args.max_power,
        max_energy_wh=args.max_energy_wh,
        budget_usd=args.budget,
        required_runtime=args.runtime,
        required_precision=args.precision,
        expected_output_tokens=args.output_tokens,
        expected_prompt_tokens=args.prompt_tokens,
        usable_battery_wh=args.battery_wh,
        available_solar_w=args.solar_w,
    )


def _print_table(rows: list[dict[str, Any]], *, limit: int) -> None:
    print("Rank  Eligible  Score  Overall  Device")
    print("----  --------  -----  -------  ------------------------------------------")
    for index, row in enumerate(rows[:limit], start=1):
        overall = row["overall_score"]
        overall_text = f"{overall:7.2f}" if overall is not None else "    n/a"
        print(f"{index:>4}  {str(row['eligible']):8}  {row['score']:5.2f}  {overall_text}  {row['name']}")
        if row["gates"]:
            print("      gates: " + "; ".join(row["gates"]))
        derived = row.get("derived", {})
        details = []
        for key, label, suffix in (
            ("task_seconds", "task", "s"),
            ("wh_per_task", "energy", "Wh"),
            ("tokens_per_kwh", "tokens/kWh", ""),
            ("battery_runtime_hours", "battery", "h"),
            ("solar_recovery_hours", "solar recovery", "h"),
        ):
            value = derived.get(key) if isinstance(derived, dict) else None
            if isinstance(value, (int, float)):
                details.append(f"{label}={value:.2f}{suffix}")
        if details:
            print("      " + ", ".join(details))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize and rank heterogeneous AI hardware using measured evidence, capacity, power, cost and workload constraints."
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="device JSON or benchmark-schema-v2 result JSON")
    parser.add_argument("--workload", choices=sorted(WORKLOAD_PROFILES), default="interactive_chat")
    parser.add_argument("--model-params-b", type=float)
    parser.add_argument("--bits", type=float, default=4.0)
    parser.add_argument("--context-tokens", type=int)
    parser.add_argument("--min-decode", type=float)
    parser.add_argument("--min-prefill", type=float)
    parser.add_argument("--max-power", type=float)
    parser.add_argument("--max-energy-wh", type=float)
    parser.add_argument("--budget", type=float)
    parser.add_argument("--runtime")
    parser.add_argument("--precision")
    parser.add_argument("--prompt-tokens", type=int)
    parser.add_argument("--output-tokens", type=int)
    parser.add_argument("--battery-wh", type=float)
    parser.add_argument("--solar-w", type=float)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--pareto", action="store_true", help="show only non-dominated task-time/energy candidates")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    devices = load_devices(args.inputs)
    if not devices:
        raise SystemExit("No device records found")
    rows = rank_devices(devices, requirements_from_args(args))
    if args.pareto:
        rows = list(pareto_frontier(rows))
    if args.json:
        print(json.dumps(rows[: args.limit], indent=2, sort_keys=True))
    else:
        _print_table(rows, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
