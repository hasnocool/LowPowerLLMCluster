from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from .catalog import project_root
from .power_identity import enrich_power_identity, identity_specificity

POWER_SOURCE_WEIGHTS = {
    "measured_local": 1.00,
    "vendor_measured": 0.90,
    "community_measured": 0.85,
    "manufacturer_spec": 0.65,
    "derived_estimate": 0.45,
    "category_baseline": 0.20,
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("-", " ").split())


def hardware_power_identity(part: dict[str, Any]) -> dict[str, Any]:
    return enrich_power_identity(part)


def load_power_evidence(path: Path | None = None) -> dict[str, Any]:
    target = path or project_root() / "data" / "power" / "evidence.json"
    if not target.exists():
        return {"schema_version": 1, "observations": []}
    return json.loads(target.read_text(encoding="utf-8"))


def save_power_evidence(payload: dict[str, Any], path: Path | None = None) -> None:
    target = path or project_root() / "data" / "power" / "evidence.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, dict) and isinstance(right, dict):
        for key, value in right.items():
            if key in left and _norm(left[key]) != _norm(value):
                return False
        return True
    return _norm(left) == _norm(right)


def observation_match_level(part: dict[str, Any], observation: dict[str, Any]) -> tuple[int, str]:
    """Match at the narrowest compatible identity without averaging conflicting hardware."""
    identity = hardware_power_identity(part)
    observed = dict(observation.get("identity") or {})

    conflict_fields = (
        "memory_gb", "storage_gb", "apple_model_identifier", "apple_part_number",
        "apple_gpu_cores", "screen_inches", "storage_controller", "nand_type",
        "gpu_board_mpn", "gpu_board_revision", "gpu_vbios", "host_cpu",
        "host_motherboard", "host_psu", "host_ram_gb", "device_sku",
        "mobile_soc", "mobile_soc_variant", "ram_topology",
    )
    for key in conflict_fields:
        if observed.get(key) not in (None, "", {}) and identity.get(key) not in (None, "", {}) and not _same(identity[key], observed[key]):
            return 0, f"configuration_conflict:{key}"

    exact_keys = (
        "exact_id", "apple_model_identifier", "apple_part_number", "device_sku",
        "gpu_board_mpn", "gpu_board_revision", "storage_controller", "nand_type",
    )
    matched_exact = [key for key in exact_keys if observed.get(key) not in (None, "") and identity.get(key) not in (None, "") and _same(identity[key], observed[key])]
    if matched_exact:
        specificity = min(99, 40 + identity_specificity({key: observed.get(key) for key in observed if key in identity}))
        label = "hardware_specific:" + "+".join(sorted(matched_exact))
        return specificity, label

    if identity.get("model") and observed.get("model") and _same(identity["model"], observed["model"]):
        return 30, "exact_model"
    if identity.get("family") and observed.get("family") and _same(identity["family"], observed["family"]):
        return 20, "hardware_family"
    if identity.get("category") and observed.get("category") and _same(identity["category"], observed["category"]):
        return 10, "category"
    return 0, "no_match"


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("values required")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def aggregate_power_observations(part: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Aggregate only the narrowest compatible power evidence distribution."""
    payload = payload or load_power_evidence()
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for row in payload.get("observations") or []:
        if row.get("eligible_for_device_power") is False:
            continue
        level, label = observation_match_level(part, row)
        if level <= 0 or (row.get("idle_w") is None and row.get("load_w") is None):
            continue
        candidates.append((level, label, row))
    if not candidates:
        return None
    best_level = max(level for level, _, _ in candidates)
    selected = [(label, row) for level, label, row in candidates if level == best_level]
    load_values = [float(row["load_w"]) for _, row in selected if row.get("load_w") is not None]
    idle_values = [float(row["idle_w"]) for _, row in selected if row.get("idle_w") is not None]
    if not load_values:
        return None
    source_weights = [POWER_SOURCE_WEIGHTS.get(str(row.get("source_type") or "derived_estimate"), 0.35) for _, row in selected]
    measured_count = sum(1 for _, row in selected if "measured" in str(row.get("source_type") or ""))
    mean_weight = statistics.fmean(source_weights) if source_weights else 0.0
    confidence = "high" if measured_count >= 2 and mean_weight >= 0.8 else "medium" if mean_weight >= 0.6 else "low"
    idle = statistics.median(idle_values) if idle_values else statistics.median(load_values) * 0.25
    return {
        "idle_w": round(idle, 2),
        "load_w": round(statistics.median(load_values), 2),
        "load_p25_w": round(_percentile(load_values, 0.25), 2),
        "load_p75_w": round(_percentile(load_values, 0.75), 2),
        "idle_p25_w": round(_percentile(idle_values, 0.25), 2) if idle_values else None,
        "idle_p75_w": round(_percentile(idle_values, 0.75), 2) if idle_values else None,
        "sample_count": len(selected),
        "measured_sample_count": measured_count,
        "match_level": best_level,
        "match_basis": selected[0][0],
        "confidence": confidence,
        "basis": "power_evidence_distribution",
        "power_scopes": sorted({str(row.get("power_scope") or "unknown") for _, row in selected}),
        "source_ids": [row.get("id") for _, row in selected if row.get("id")],
        "inferred": confidence != "high",
    }


def add_power_observation(payload: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    """Append a normalized observation; exact duplicates are ignored."""
    result = json.loads(json.dumps(payload))
    result.setdefault("schema_version", 1)
    result.setdefault("observations", [])
    required = ("id", "source_type", "identity")
    if any(not observation.get(key) for key in required):
        raise ValueError("power observation requires id, source_type and identity")
    if observation.get("idle_w") is None and observation.get("load_w") is None:
        raise ValueError("power observation requires idle_w or load_w")
    if any(str(row.get("id")) == str(observation["id"]) for row in result["observations"]):
        return result
    result["observations"].append(dict(observation))
    return result
