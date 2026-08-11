# src/lowpower_llm_cluster/power_measurements.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalog import project_root

ALLOWED_POWER_SCOPES = {
    "complete_node_input",
    "measured_device_input",
    "device_input",
    "accelerator_board_power",
    "accelerator_board_power_reference",
    "internal_rail",
}

MEASURED_SOURCE_TYPES = {"measured_local", "vendor_measured", "community_measured"}


def load_sourced_power_measurements(path: Path | None = None) -> dict[str, Any]:
    target = path or project_root() / "data" / "evidence" / "power-measurements.json"
    if not target.exists():
        return {"schema_version": 1, "records": []}
    return json.loads(target.read_text(encoding="utf-8"))


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def normalize_sourced_power_record(row: dict[str, Any]) -> dict[str, Any]:
    record_id = str(row.get("id") or "").strip()
    source_type = str(row.get("source_type") or "").strip()
    source_url = str(row.get("source_url") or "").strip()
    scope = str(row.get("power_scope") or "").strip()
    identity = dict(row.get("identity") or {})
    idle = _num(row.get("idle_w"))
    load = _num(row.get("load_w"))

    if not record_id:
        raise ValueError("sourced power record requires id")
    if source_type not in MEASURED_SOURCE_TYPES:
        raise ValueError(f"unsupported measured source_type: {source_type}")
    if not source_url.startswith("https://"):
        raise ValueError("sourced power record requires HTTPS source_url")
    if scope not in ALLOWED_POWER_SCOPES:
        raise ValueError(f"unsupported power_scope: {scope}")
    if not identity:
        raise ValueError("sourced power record requires explicit hardware identity")
    if idle is None and load is None:
        raise ValueError("sourced power record requires idle_w or load_w")

    eligible = scope in {"complete_node_input", "measured_device_input", "device_input", "accelerator_board_power", "accelerator_board_power_reference"}
    return {
        "id": f"sourced-power:{record_id}",
        "part_id": row.get("part_id"),
        "source_type": source_type,
        "source_url": source_url,
        "identity": identity,
        "idle_w": idle,
        "load_w": load,
        "max_w": _num(row.get("max_w")),
        "power_scope": scope,
        "eligible_for_device_power": eligible,
        "evidence_basis": "curated_sourced_exact_power_measurement",
        "measurement_method": row.get("measurement_method"),
        "workload": row.get("workload"),
        "runtime": row.get("runtime"),
        "notes": row.get("notes"),
    }


def sourced_power_observations(path: Path | None = None) -> list[dict[str, Any]]:
    payload = load_sourced_power_measurements(path)
    return [normalize_sourced_power_record(dict(row)) for row in payload.get("records") or []]
