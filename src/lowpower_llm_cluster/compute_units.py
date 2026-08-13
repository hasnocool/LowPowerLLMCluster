# src/lowpower_llm_cluster/compute_units.py
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ACCELERATOR_CATEGORY_DOMAIN = {
    "gpu_accelerator": "gpu",
    "npu_accelerator": "npu",
    "tpu_accelerator": "tpu",
    "ai_asic_accelerator": "ai_asic",
    "fpga_accelerator": "fpga",
    "adaptive_soc": "adaptive_soc",
    "decommissioned_accelerator": "accelerator",
}

UNKNOWN_UNIT_TYPE = {
    "gpu": "gpu_native_unit",
    "npu": "npu_engine",
    "tpu": "tpu_core",
    "ai_asic": "asic_compute_engine",
    "fpga": "fpga_compute_fabric",
    "adaptive_soc": "adaptive_compute_engine",
    "accelerator": "accelerator_compute_engine",
}


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_compute_unit_registry(path: Path | None = None) -> dict[str, Any]:
    target = path or _root() / "data" / "evidence" / "compute-units.json"
    if not target.exists():
        return {"schema_version": 1, "records": []}
    return json.loads(target.read_text(encoding="utf-8"))


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _apple_gpu_range(part: dict[str, Any]) -> tuple[int | None, int | None]:
    text = " ".join(
        _norm(part.get(key))
        for key in ("igpu", "name", "cpu", "source_notes", "plain_language")
        if part.get(key)
    )
    values = [int(value) for value in re.findall(r"(\d+)\s*[- ]core\s+(?:apple\s+)?gpu", text, flags=re.I)]
    if not values:
        return None, None
    return min(values), max(values)


def _mali_mp_count(part: dict[str, Any]) -> int | None:
    text = " ".join(_norm(part.get(key)) for key in ("igpu", "accelerator", "source_notes") if part.get(key))
    match = re.search(r"Mali[- ]?[A-Z0-9]+\s+MP(\d+)", text, flags=re.I)
    return int(match.group(1)) if match else None


def _registry_by_part(registry: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in registry.get("records") or []:
        part_id = str(row.get("part_id") or "").strip()
        if part_id:
            out.setdefault(part_id, []).append(dict(row))
    return out


def compute_topology(part: dict[str, Any], registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return architecture-native compute domains without pretending cross-architecture unit equivalence."""
    registry = registry or load_compute_unit_registry()
    by_part = _registry_by_part(registry)
    domains: list[dict[str, Any]] = []

    cpu_cores = _positive_int(part.get("cores"))
    if cpu_cores:
        domains.append({
            "domain": "cpu",
            "unit_type": "cpu_core",
            "unit_count": cpu_cores,
            "count_min": cpu_cores,
            "count_max": cpu_cores,
            "basis": "catalog_explicit_core_count",
            "confidence": "high",
            "source_url": part.get("source_url") or part.get("url"),
        })

    for row in by_part.get(str(part.get("id") or ""), []):
        count = _positive_int(row.get("unit_count"))
        if count is None:
            continue
        domains.append({
            "domain": row.get("domain"),
            "unit_type": row.get("unit_type"),
            "unit_count": count,
            "count_min": count,
            "count_max": count,
            "basis": row.get("source_type") or "registry",
            "confidence": row.get("confidence") or "unknown",
            "source_url": row.get("source_url"),
            "notes": row.get("notes"),
        })

    has_gpu = any(row.get("domain") == "gpu" for row in domains)
    if not has_gpu:
        apple_min, apple_max = _apple_gpu_range(part)
        if apple_min is not None:
            domains.append({
                "domain": "gpu",
                "unit_type": "apple_gpu_core",
                "unit_count": apple_min if apple_min == apple_max else None,
                "count_min": apple_min,
                "count_max": apple_max,
                "basis": "catalog_explicit_apple_gpu_core_text",
                "confidence": "high" if apple_min == apple_max else "medium",
                "source_url": part.get("source_url") or part.get("url"),
                "notes": "Configuration range retained when a family row covers multiple GPU-core bins.",
            })
            has_gpu = True

    if not has_gpu:
        mali_count = _mali_mp_count(part)
        if mali_count:
            domains.append({
                "domain": "gpu",
                "unit_type": "mali_gpu_core",
                "unit_count": mali_count,
                "count_min": mali_count,
                "count_max": mali_count,
                "basis": "catalog_explicit_mali_mp_designation",
                "confidence": "medium",
                "source_url": part.get("source_url") or part.get("url"),
            })
            has_gpu = True

    accel_domain = ACCELERATOR_CATEGORY_DOMAIN.get(str(part.get("category") or ""))
    if accel_domain and not any(row.get("domain") == accel_domain for row in domains):
        domains.append({
            "domain": accel_domain,
            "unit_type": UNKNOWN_UNIT_TYPE[accel_domain],
            "unit_count": None,
            "count_min": None,
            "count_max": None,
            "basis": "native_internal_count_not_resolved",
            "confidence": "unknown",
            "source_url": part.get("source_url") or part.get("url"),
            "notes": "The device is compute-capable, but a defensible architecture-native internal unit count has not yet been sourced.",
        })

    known = [row for row in domains if row.get("unit_count") is not None or row.get("count_min") is not None]
    priority = ("gpu", "npu", "tpu", "ai_asic", "fpga", "adaptive_soc", "accelerator", "cpu")
    primary = None
    for domain in priority:
        primary = next((row for row in known if row.get("domain") == domain), None)
        if primary:
            break

    if not domains:
        status = "not_applicable" if part.get("category") in {"memory", "storage"} else "unknown"
    elif len(known) == len(domains):
        status = "known"
    elif known:
        status = "partial"
    else:
        status = "unknown"

    return {
        "status": status,
        "cross_architecture_comparable": False,
        "domains": domains,
        "primary_domain": primary.get("domain") if primary else None,
        "primary_unit_type": primary.get("unit_type") if primary else None,
        "primary_unit_count": primary.get("unit_count") if primary else None,
        "primary_count_min": primary.get("count_min") if primary else None,
        "primary_count_max": primary.get("count_max") if primary else None,
        "warning": "Native compute-unit counts are architecture-specific. Do not rank unlike unit types numerically; use compatible measured LLM performance for cross-device comparisons.",
    }


def enrich_catalog_compute_topology(data: dict[str, Any], registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach compute_topology to every catalog row without mutating the caller's object graph."""
    registry = registry or load_compute_unit_registry()
    result = {**data, "parts": []}
    for original in data.get("parts") or []:
        part = dict(original)
        part["compute_topology"] = compute_topology(part, registry)
        result["parts"].append(part)
    return result


def display_compute_units(part: dict[str, Any]) -> str:
    topology = dict(part.get("compute_topology") or compute_topology(part))
    unit_type = topology.get("primary_unit_type")
    count = topology.get("primary_unit_count")
    low = topology.get("primary_count_min")
    high = topology.get("primary_count_max")
    if count is not None:
        return f"{count} {unit_type}"
    if low is not None and high is not None:
        return f"{low}-{high} {unit_type}"
    return "unknown"
