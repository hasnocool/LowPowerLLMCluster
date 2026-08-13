# src/lowpower_llm_cluster/catalog.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .compute_units import enrich_catalog_compute_topology


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    """Load the catalog manifest, merge fragments, and attach architecture-native compute topology."""
    catalog_path = path or project_root() / "data" / "parts.json"
    with catalog_path.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)

    if "parts" in data:
        return enrich_catalog_compute_topology(data)

    parts: list[dict[str, Any]] = []
    for relative_path in data.get("part_files", []):
        fragment_path = catalog_path.parent / str(relative_path)
        with fragment_path.open("r", encoding="utf-8") as handle:
            fragment = json.load(handle)
        parts.extend(fragment.get("parts", []))

    return enrich_catalog_compute_topology({**data, "parts": parts})


def midpoint_price(part: dict[str, Any]) -> float | None:
    low = part.get("price_min_usd")
    high = part.get("price_max_usd")
    if low is None or high is None:
        return None
    return (float(low) + float(high)) / 2.0


def llm_candidates(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [part for part in parts if part.get("llm_candidate", part.get("category") == "compute_node")]


def catalog_index(parts: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Create an ID index and reject duplicate IDs instead of silently replacing records."""
    result: dict[str, dict[str, Any]] = {}
    for part in parts:
        part_id = str(part["id"])
        if part_id in result:
            raise ValueError(f"duplicate catalog id: {part_id}")
        result[part_id] = part
    return result


def exact_sku_confidence(part: dict[str, Any]) -> float:
    """Return explicit SKU confidence when present, otherwise a conservative catalog estimate."""
    explicit = part.get("sku_confidence")
    if explicit is not None:
        return round(max(0.0, min(1.0, float(explicit))), 3)
    score = 0.18
    if part.get("manufacturer") or part.get("vendor"):
        score += 0.12
    if part.get("mpn"):
        score += 0.28
    if part.get("sku"):
        score += 0.20
    if part.get("memory_config_status") in {"included", "fixed"} and part.get("memory_capacity_gb") is not None:
        score += 0.12
    if part.get("storage") and "variant" not in str(part.get("storage", "")).lower():
        score += 0.05
    if "verify_variant" in str(part.get("listing_status", "")):
        score -= 0.15
    return round(max(0.0, min(1.0, score)), 3)
