# src/lowpower_llm_cluster/power_ingestion.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalog import load_catalog, project_root
from .power_evidence import add_power_observation, hardware_power_identity, load_power_evidence, save_power_evidence
from .power_measurements import sourced_power_observations

USABLE_DEVICE_SCOPES = {
    "complete_node_input",
    "measured_device_input",
    "device_input",
    "accelerator_board_power_reference",
    "accelerator_board_power",
    "published_device_or_board_power",
    "published_device_or_board_limit",
}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _num(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number >= 0:
            return number
    return None


def _benchmark_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(key) for key in (
        "part_id", "model", "quantization", "runtime", "runtime_version", "backend", "workload",
        "prompt_length", "generation_length", "threads", "hardware_configuration",
    ))


def _part_map(catalog: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    catalog = catalog or load_catalog()
    return {str(row.get("id")): row for row in catalog.get("parts") or [] if row.get("id")}


def catalog_power_observations(catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Turn explicit catalog/manufacturer power facts into reusable exact/family evidence."""
    parts = _part_map(catalog)
    out: list[dict[str, Any]] = []
    for part_id, part in parts.items():
        target = _num(part, "power_target_w")
        maximum = _num(part, "power_max_w", "tdp_w", "tbp_w", "tgp_w", "board_power_w")
        if target is None and maximum is None:
            continue
        scope = str(part.get("power_scope") or "published_device_or_board_power")
        load = target if target is not None else maximum
        source_type = "manufacturer_spec" if part.get("source_url") or part.get("url") else "derived_estimate"
        out.append({
            "id": f"catalog:{part_id}:{scope}:{load}",
            "part_id": part_id,
            "source_type": source_type,
            "source_url": part.get("source_url") or part.get("url"),
            "identity": hardware_power_identity(part),
            "load_w": load,
            "max_w": maximum,
            "power_scope": scope,
            "eligible_for_device_power": scope.casefold() in USABLE_DEVICE_SCOPES,
            "evidence_basis": "catalog_explicit_power_field",
            "notes": "Catalog/manufacturer power field; published target/limit is not a wall measurement unless its scope explicitly says complete_node_input.",
        })
    return out


def manufacturer_spec_power_observations(spec_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Promote exact manufacturer-enriched power fields into reusable identity evidence."""
    out: list[dict[str, Any]] = []
    for record in spec_payload.get("records") or []:
        listing = dict(record.get("listing") or {})
        facts = dict(record.get("compatibility_facts") or {})
        evidence = dict(record.get("field_evidence") or {})
        component = str(record.get("component") or "unknown")
        pseudo_part = {
            "category": component,
            "name": record.get("title") or listing.get("title") or component,
            "configuration": listing.get("configuration") or {},
            "compatibility_facts": facts,
            "spec_enrichment": {"facts": facts},
        }
        identity = hardware_power_identity(pseudo_part)
        if not identity:
            continue
        power_fields = (
            ("power_target_w", "published_device_or_board_power"),
            ("board_power_w", "accelerator_board_power_reference"),
            ("tgp_w", "accelerator_board_power_reference"),
            ("tbp_w", "accelerator_board_power_reference"),
            ("tdp_w", "published_device_or_board_limit"),
            ("power_max_w", "published_device_or_board_limit"),
        )
        for field, default_scope in power_fields:
            value = _num(facts, field)
            if value is None:
                continue
            provenance = dict(evidence.get(field) or {})
            source_url = provenance.get("source_url") or (record.get("spec_enrichment") or {}).get("source_url")
            if not source_url:
                continue
            scope = str(provenance.get("power_scope") or facts.get("power_scope") or default_scope)
            source_id = listing.get("source_id") or record.get("title") or component
            out.append({
                "id": f"manufacturer-spec:{source_id}:{field}:{value}",
                "part_id": record.get("part_id"),
                "source_type": "manufacturer_spec",
                "source_url": source_url,
                "identity": identity,
                "load_w": value,
                "max_w": value if field in {"tdp_w", "power_max_w", "tgp_w", "tbp_w", "board_power_w"} else None,
                "power_scope": scope,
                "eligible_for_device_power": scope.casefold() in USABLE_DEVICE_SCOPES,
                "evidence_basis": f"exact_manufacturer_spec_field:{field}",
                "association_id": provenance.get("association_id"),
                "confidence": provenance.get("confidence"),
            })
    return out


def benchmark_power_observations(performance: dict[str, Any], catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Collect explicit benchmark watts and safe same-signature throughput/energy-efficiency derivations."""
    parts = _part_map(catalog)
    records = list(performance.get("records") or [])
    out: list[dict[str, Any]] = []

    for row in records:
        part = parts.get(str(row.get("part_id") or ""))
        if not part:
            continue
        load = _num(row, "measured_load_w", "average_power_w", "power_w", "watts")
        idle = _num(row, "measured_idle_w", "idle_power_w")
        if load is None and idle is None:
            continue
        scope = str(row.get("power_scope") or "unknown")
        identity_source = dict(part)
        if isinstance(row.get("hardware_configuration"), dict):
            identity_source["configuration"] = {**dict(part.get("configuration") or {}), **dict(row["hardware_configuration"])}
        out.append({
            "id": f"benchmark:{row.get('id')}:watts",
            "part_id": row.get("part_id"),
            "source_type": row.get("source_type") or "community_measured",
            "source_url": row.get("source_url"),
            "identity": hardware_power_identity(identity_source),
            "idle_w": idle,
            "load_w": load,
            "power_scope": scope,
            "eligible_for_device_power": scope.casefold() in USABLE_DEVICE_SCOPES,
            "evidence_basis": "benchmark_explicit_watts",
            "benchmark_id": row.get("id"),
            "hardware_configuration": row.get("hardware_configuration"),
        })

    throughput: dict[tuple[Any, ...], dict[str, Any]] = {}
    efficiency: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in records:
        signature = _benchmark_signature(row)
        metric = str(row.get("metric") or "").casefold()
        unit = str(row.get("unit") or "").casefold().replace(" ", "")
        if metric == "throughput" and unit in {"tokens/s", "token/s", "tokens/sec"}:
            throughput[signature] = row
        elif metric == "energy_efficiency" and unit in {"tokens/j", "token/j"}:
            efficiency[signature] = row
    for signature in set(throughput) & set(efficiency):
        speed = throughput[signature]
        eff = efficiency[signature]
        tps = _num(speed, "value")
        tokens_per_j = _num(eff, "value")
        if tps is None or not tokens_per_j:
            continue
        part = parts.get(str(speed.get("part_id") or ""))
        if not part:
            continue
        watts = tps / tokens_per_j
        scope = str(eff.get("power_scope") or speed.get("power_scope") or "unknown")
        identity_source = dict(part)
        if isinstance(speed.get("hardware_configuration"), dict):
            identity_source["configuration"] = {**dict(part.get("configuration") or {}), **dict(speed["hardware_configuration"])}
        out.append({
            "id": f"benchmark-derived:{speed.get('id')}:{eff.get('id')}",
            "part_id": speed.get("part_id"),
            "source_type": eff.get("source_type") or speed.get("source_type") or "community_measured",
            "source_url": eff.get("source_url") or speed.get("source_url"),
            "identity": hardware_power_identity(identity_source),
            "load_w": round(watts, 4),
            "power_scope": scope,
            "eligible_for_device_power": scope.casefold() in USABLE_DEVICE_SCOPES,
            "evidence_basis": "derived_watts_from_exact_signature_throughput_divided_by_tokens_per_joule",
            "benchmark_ids": [speed.get("id"), eff.get("id")],
            "hardware_configuration": speed.get("hardware_configuration"),
            "warning": "Derived watts inherit the published power boundary. Internal-rail values are retained as evidence but are not eligible to train complete-device power.",
        })
    return out


def refresh_power_evidence(
    *,
    performance_path: Path | None = None,
    evidence_path: Path | None = None,
    sourced_measurements_path: Path | None = None,
    spec_evidence_path: Path | None = None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append catalog, benchmark, sourced-measurement and exact manufacturer power evidence."""
    catalog = catalog or load_catalog()
    performance = _load_json(performance_path or project_root() / "data" / "evidence" / "performance.json", {"records": []})
    spec_payload = _load_json(spec_evidence_path or project_root() / "data" / "market" / "spec-evidence.json", {"records": []})
    payload = load_power_evidence(evidence_path)
    before = len(payload.get("observations") or [])
    candidates = [
        *catalog_power_observations(catalog),
        *benchmark_power_observations(performance, catalog),
        *manufacturer_spec_power_observations(spec_payload),
        *sourced_power_observations(sourced_measurements_path),
    ]
    for observation in candidates:
        payload = add_power_observation(payload, observation)
    after = len(payload.get("observations") or [])
    save_power_evidence(payload, evidence_path)
    return {
        "before": before,
        "after": after,
        "added": after - before,
        "candidates": len(candidates),
        "candidate_sources": {
            "catalog": len(catalog_power_observations(catalog)),
            "benchmarks": len(benchmark_power_observations(performance, catalog)),
            "manufacturer_specs": len(manufacturer_spec_power_observations(spec_payload)),
            "sourced_measurements": len(sourced_power_observations(sourced_measurements_path)),
        },
        "eligible_device_observations": sum(1 for row in payload.get("observations") or [] if row.get("eligible_for_device_power") is True),
        "research_only_observations": sum(1 for row in payload.get("observations") or [] if row.get("eligible_for_device_power") is False),
    }
