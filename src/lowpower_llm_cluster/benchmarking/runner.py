# src/lowpower_llm_cluster/benchmarking/runner.py
from __future__ import annotations

import asyncio
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..catalog import load_catalog, midpoint_price
from .adapters import AdapterContext, build_adapter
from .power import build_power_probe, measure_idle

CANONICAL_COMPLETE_NODE_SCOPE = "complete_node_input"


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_profile(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        profile = json.load(handle)
    validate_profile(profile)
    return profile


def validate_profile(profile: dict[str, Any]) -> None:
    required = ["schema_version", "hardware_id", "workload_class", "adapter", "model", "workload"]
    missing = [key for key in required if key not in profile]
    if missing:
        raise ValueError(f"benchmark profile missing required keys: {', '.join(missing)}")
    if int(profile["schema_version"]) != 1:
        raise ValueError("benchmark profile schema_version must be 1")
    workload_class = str(profile["workload_class"])
    if workload_class not in {"llm", "vision", "audio", "embedding", "other"}:
        raise ValueError(f"unsupported workload_class: {workload_class}")
    workload = profile["workload"]
    if int(workload.get("runs", 0)) < 3:
        raise ValueError("benchmark profiles require at least 3 measured runs")
    if workload_class == "llm":
        for key in ("prompt_tokens", "generated_tokens", "context_tokens"):
            if int(workload.get(key, 0)) <= 0:
                raise ValueError(f"LLM benchmark workload requires positive {key}")
    adapter_type = str(profile["adapter"].get("type", ""))
    if adapter_type == "llama_cpp" and not profile["model"].get("path"):
        raise ValueError("llama_cpp adapter requires model.path")


def _part_by_id(hardware_id: str) -> dict[str, Any] | None:
    for part in load_catalog()["parts"]:
        if part["id"] == hardware_id:
            return part
    return None


async def _sha256_file(path: Path) -> str:
    def calculate() -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    return await asyncio.to_thread(calculate)


async def _model_identity(model: dict[str, Any]) -> dict[str, Any]:
    result = dict(model)
    raw_path = model.get("path")
    if not raw_path:
        return result
    path = Path(str(raw_path)).expanduser()
    exists = await asyncio.to_thread(path.is_file)
    result["path"] = str(path)
    result["file_exists"] = exists
    if not exists:
        return result
    stat = await asyncio.to_thread(path.stat)
    result["size_bytes"] = int(stat.st_size)
    calculated = await _sha256_file(path)
    expected = model.get("sha256")
    if expected and str(expected).lower() != calculated.lower():
        raise ValueError(f"model hash mismatch for {path}: expected {expected}, got {calculated}")
    result["sha256"] = calculated
    return result


def _preflight_fit(part: dict[str, Any] | None, model: dict[str, Any], headroom: float) -> dict[str, Any]:
    if not part or "size_bytes" not in model:
        return {"status": "unknown", "basis": "insufficient_data"}
    memory_gb = part.get("memory_capacity_gb") or part.get("max_ram_gb")
    if memory_gb is None:
        return {"status": "unknown", "basis": "catalog_memory_unknown"}
    capacity = float(memory_gb) * (1024**3) * headroom
    fits = float(model["size_bytes"]) <= capacity
    return {
        "status": "estimated_fit" if fits else "estimated_no_fit",
        "basis": "model_file_size_vs_catalog_memory_only",
        "catalog_memory_gb": float(memory_gb),
        "headroom_fraction": headroom,
        "warning": "File-size screening is not a runtime memory benchmark.",
    }


def _metric_median(metrics: dict[str, Any], name: str) -> float | None:
    item = metrics.get(name)
    if not item:
        return None
    return float(item["median"])


def _power_average(power: dict[str, Any], phase: str) -> float | None:
    item = power.get(phase)
    if not item or item.get("scope") != CANONICAL_COMPLETE_NODE_SCOPE:
        return None
    duration = item.get("duration_s")
    energy = item.get("energy_j")
    if duration is not None and energy is not None and float(duration) > 0:
        return float(energy) / float(duration)
    value = item.get("mean_w")
    return float(value) if value is not None else None


def _system_cost(profile: dict[str, Any], part: dict[str, Any] | None) -> tuple[float | None, str]:
    if profile.get("system_cost_usd") is not None:
        return float(profile["system_cost_usd"]), "profile_complete_system_cost"
    if not part:
        return None, "unknown"
    host_mode = str(part.get("host_mode", "standalone"))
    if host_mode not in {"standalone", "soc", "complete_node", "onboard"} and part.get("category", "").endswith("accelerator"):
        return None, "host_attached_accelerator_requires_complete_system_cost"
    mid = midpoint_price(part)
    return (float(mid), "catalog_midpoint") if mid is not None else (None, "catalog_price_unresolved")


def _efficiency(
    *,
    workload_class: str,
    metrics: dict[str, Any],
    power: dict[str, Any],
    cost_usd: float | None,
    primary_metric: str | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "power_policy": "canonical energy efficiency requires power scope complete_node_input",
        "system_cost_usd": cost_usd,
    }
    if workload_class == "llm":
        prompt_tps = _metric_median(metrics, "prompt_tokens_per_second")
        generation_tps = _metric_median(metrics, "generation_tokens_per_second")
        prefill_w = _power_average(power, "prefill")
        decode_w = _power_average(power, "decode")
        if prompt_tps is not None and prefill_w and prefill_w > 0:
            result["prompt_tokens_per_joule"] = prompt_tps / prefill_w
        if generation_tps is not None and decode_w and decode_w > 0:
            result["generation_tokens_per_joule"] = generation_tps / decode_w
        if cost_usd and cost_usd > 0:
            if prompt_tps is not None:
                result["prompt_tps_per_purchase_usd"] = prompt_tps / cost_usd
            if generation_tps is not None:
                result["generation_tps_per_purchase_usd"] = generation_tps / cost_usd
        return result

    metric_name = primary_metric or next(iter(metrics), None)
    if metric_name is None:
        return result
    throughput = _metric_median(metrics, metric_name)
    active_w = _power_average(power, "active")
    result["primary_metric"] = metric_name
    if throughput is not None and active_w and active_w > 0:
        result["primary_units_per_joule"] = throughput / active_w
    if throughput is not None and cost_usd and cost_usd > 0:
        result["primary_units_per_purchase_usd"] = throughput / cost_usd
    return result


async def run_profile(profile: dict[str, Any]) -> dict[str, Any]:
    validate_profile(profile)
    part = _part_by_id(str(profile["hardware_id"]))
    model = await _model_identity(profile["model"])
    if profile["adapter"].get("type") == "llama_cpp" and not model.get("file_exists"):
        raise FileNotFoundError(f"llama.cpp model file not found: {model.get('path')}")

    power_config = profile.get("power", {})
    probe = build_power_probe(power_config)
    interval_s = float(power_config.get("sample_interval_s", 1.0))
    if interval_s <= 0:
        raise ValueError("power.sample_interval_s must be positive")
    idle_window = await measure_idle(
        probe,
        duration_s=float(power_config.get("idle_duration_s", 0.0)),
        interval_s=interval_s,
    )

    adapter = build_adapter(profile["adapter"])
    context = AdapterContext(
        profile=profile,
        power_probe=probe,
        power_interval_s=interval_s,
        timeout_s=float(profile["adapter"]["timeout_s"]) if profile["adapter"].get("timeout_s") else None,
    )
    adapter_result = await adapter.run(context)
    power_windows = {phase: window.to_dict() for phase, window in adapter_result.power_windows.items()}
    if idle_window is not None:
        power_windows["idle"] = idle_window.to_dict()

    metrics = {name: summary.to_dict() for name, summary in adapter_result.metrics.items()}
    cost_usd, cost_basis = _system_cost(profile, part)
    fit = {
        "preflight": _preflight_fit(part, model, float(profile.get("fit_headroom_fraction", 0.85))),
        "runtime": {"status": adapter_result.fit_status},
    }
    result = {
        "schema_version": 2,
        "result_id": f"bench-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hardware_id": profile["hardware_id"],
        "hardware_snapshot": {
            "name": part.get("name") if part else None,
            "category": part.get("category") if part else None,
            "hardware_class": part.get("hardware_class") if part else None,
            "accelerator_family": part.get("accelerator_family") if part else None,
        },
        "configuration_id": profile.get("configuration_id", "default"),
        "system": {
            "os": platform.system(),
            "os_release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "runtime": adapter_result.metadata,
        "model": model,
        "workload_class": profile["workload_class"],
        "workload": profile["workload"],
        "fit": fit,
        "metrics": metrics,
        "power": power_windows,
        "cost": {"system_cost_usd": cost_usd, "basis": cost_basis},
        "efficiency": _efficiency(
            workload_class=str(profile["workload_class"]),
            metrics=metrics,
            power=power_windows,
            cost_usd=cost_usd,
            primary_metric=profile.get("primary_metric"),
        ),
        "raw": adapter_result.raw,
    }
    return result


def comparable_signature(result: dict[str, Any]) -> tuple[Any, ...]:
    model = result.get("model", {})
    workload = result.get("workload", {})
    workload_class = result.get("workload_class")
    primary = result.get("efficiency", {}).get("primary_metric")
    return (
        workload_class,
        model.get("sha256") or model.get("name"),
        model.get("quantization"),
        workload.get("context_tokens"),
        workload.get("prompt_tokens"),
        workload.get("generated_tokens"),
        primary,
    )


def comparison_row(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("metrics", {})
    efficiency = result.get("efficiency", {})
    workload_class = result.get("workload_class")
    if workload_class == "llm":
        return {
            "hardware_id": result.get("hardware_id"),
            "generation_tps": _metric_median(metrics, "generation_tokens_per_second"),
            "prompt_tps": _metric_median(metrics, "prompt_tokens_per_second"),
            "generation_tokens_per_joule": efficiency.get("generation_tokens_per_joule"),
            "generation_tps_per_purchase_usd": efficiency.get("generation_tps_per_purchase_usd"),
        }
    primary = efficiency.get("primary_metric") or next(iter(metrics), None)
    return {
        "hardware_id": result.get("hardware_id"),
        "primary_metric": primary,
        "throughput": _metric_median(metrics, primary) if primary else None,
        "units_per_joule": efficiency.get("primary_units_per_joule"),
        "units_per_purchase_usd": efficiency.get("primary_units_per_purchase_usd"),
    }


def write_result(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
