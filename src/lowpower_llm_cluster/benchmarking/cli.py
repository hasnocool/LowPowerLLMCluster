# src/lowpower_llm_cluster/benchmarking/cli.py
from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .adapters import adapter_names
from .runner import comparable_signature, comparison_row, load_profile, run_profile, validate_profile, write_result


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measured-performance harness for heterogeneous LowPowerLLMCluster hardware"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backends", help="List built-in benchmark adapters")

    validate = sub.add_parser("validate", help="Validate a benchmark profile without running hardware")
    validate.add_argument("profile", type=Path)

    run = sub.add_parser("run", help="Run one benchmark profile")
    run.add_argument("profile", type=Path)
    run.add_argument("--output", type=Path, help="Result JSON path; defaults under results/")
    run.add_argument("--print-json", action="store_true", help="Also print the complete result JSON")

    compare = sub.add_parser("compare", help="Compare result files without mixing incompatible workloads")
    compare.add_argument("results", nargs="+", type=Path)
    return parser


async def _run(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    result = await run_profile(profile)
    output = args.output
    if output is None:
        output = Path("results") / f"{result['result_id']}.json"
    write_result(result, output)
    print(f"Wrote {output}")
    if result["workload_class"] == "llm":
        row = comparison_row(result)
        print(
            "generation_tps={generation} prompt_tps={prompt} generation_tokens/J={energy} generation_tps/$={cost}".format(
                generation=_fmt(row["generation_tps"]),
                prompt=_fmt(row["prompt_tps"]),
                energy=_fmt(row["generation_tokens_per_joule"]),
                cost=_fmt(row["generation_tps_per_purchase_usd"], 6),
            )
        )
    else:
        row = comparison_row(result)
        print(
            f"{row.get('primary_metric')}={_fmt(row.get('throughput'))} "
            f"units/J={_fmt(row.get('units_per_joule'))} units/$={_fmt(row.get('units_per_purchase_usd'), 6)}"
        )
    if args.print_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _compare(paths: list[Path]) -> int:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for path in paths:
        result = json.loads(path.read_text(encoding="utf-8"))
        groups[comparable_signature(result)].append(result)

    if len(groups) > 1:
        print("Results contain incompatible workload/model signatures; showing separate comparison groups.")
    for index, (signature, results) in enumerate(groups.items(), start=1):
        workload_class = signature[0]
        print(f"\nGroup {index}: workload={workload_class} signature={signature[1:]}")
        rows = [comparison_row(result) for result in results]
        if workload_class == "llm":
            rows.sort(key=lambda row: row.get("generation_tokens_per_joule") or -1.0, reverse=True)
            print("Hardware                          Gen t/s  Prompt t/s  Gen tok/J  Gen t/s/$")
            print("--------------------------------  -------  ----------  ---------  ---------")
            for row in rows:
                print(
                    f"{str(row['hardware_id'])[:32]:32}  {_fmt(row['generation_tps']):>7}  "
                    f"{_fmt(row['prompt_tps']):>10}  {_fmt(row['generation_tokens_per_joule']):>9}  "
                    f"{_fmt(row['generation_tps_per_purchase_usd'], 6):>9}"
                )
        else:
            rows.sort(key=lambda row: row.get("units_per_joule") or -1.0, reverse=True)
            print("Hardware                          Metric                    Rate       Units/J    Units/$")
            print("--------------------------------  ------------------------  ---------  ---------  ---------")
            for row in rows:
                print(
                    f"{str(row['hardware_id'])[:32]:32}  {str(row.get('primary_metric'))[:24]:24}  "
                    f"{_fmt(row.get('throughput')):>9}  {_fmt(row.get('units_per_joule')):>9}  "
                    f"{_fmt(row.get('units_per_purchase_usd'), 6):>9}"
                )
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "backends":
        print("\n".join(adapter_names()))
        return 0
    if args.command == "validate":
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        validate_profile(profile)
        print(f"Valid benchmark profile: {args.profile}")
        return 0
    if args.command == "run":
        return asyncio.run(_run(args))
    if args.command == "compare":
        return _compare(args.results)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
