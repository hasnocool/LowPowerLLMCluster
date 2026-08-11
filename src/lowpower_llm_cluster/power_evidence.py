from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from .catalog import project_root

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


def _token(part: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = part.get(key)
        if value not in (None, ""):
            return _norm(value)
    return None


def hardware_power_identity(part: dict[str, Any]) -> dict[str, Any]:
    """Build increasingly broad power-matching identities without guessing missing SKU data."""
    config = dict(part.get("configuration") or {})
    exact_id = _token(config, "apple_part_number", "model_identifier", "apple_a_number", "mpn") or _token(part, "mpn", "model_number", "sku")
    model = _token(config, "soc", "chip", "model") or _token(part, "name")
    family = _token(part, "accelerator_family", "hardware_class") or _token(config, "soc")
    return {
        "exact_id": exact_id,
        "model": model,
        "family": family,
        "category": _norm(part.get("category")),
        "memory_gb": part.get("memory_capacity_gb") or config.get("memory_capacity_gb"),
        "storage_gb": config.get("storage_gb"),
    }


def load_power_evidence(path: Path | None = None) -> dict[str, Any]:
    target = path or project_root() / "data" / "power" / "evidence.json"
    if not target.exists():
        return {"schema_version": 1, "observations": []}
    return json.loads(target.read_text(encoding="utf-8"))


def save_power_evidence(payload: dict[str, Any], path: Path | None = None) -> None:
    target = path or project_root() / "data" / "power" / "evidence.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def observation_match_level(part: dict[str, Any], observation: dict[str, Any]) -> tuple[int, str]:
    identity = hardware_power_identity(part)
    observed = dict(observation.get("identity") or {})
    if identity.get("exact_id") and _norm(observed.get("exact_id")) == identity["exact_id"]:
        # Exact identifier is strongest; memory/storage tighten exact Apple/system configurations when supplied.
        for key in ("memory_gb", "storage_gb"):
            if observed.get(key) is not None and identity.get(key) is not None and float(observed[key]) != float(identity[key]):
                return 0, "configuration_conflict"
        return 4, "exact_sku_or_model_identifier"
    if identity.get("model") and _norm(observed.get("model")) == identity["model"]:
        return 3, "exact_model"
    if identity.get("family") and _norm(observed.get("family")) == identity["family"]:
        return 2, "hardware_family"
    if identity.get("category") and _norm(observed.get("category")) == identity["category"]:
        return 1, "category"
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
    payload = payload or load_power_evidence()
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for row in payload.get("observations") or []:
        level, label = observation_match_level(part, row)
        if level <= 0:
            continue
        if row.get("idle_w") is None and row.get("load_w") is None:
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
