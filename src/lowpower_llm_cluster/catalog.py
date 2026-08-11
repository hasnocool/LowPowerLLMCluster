# src/lowpower_llm_cluster/catalog.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    """Load the catalog manifest and transparently merge its part fragments."""
    catalog_path = path or project_root() / "data" / "parts.json"
    with catalog_path.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)

    if "parts" in data:
        return data

    parts: list[dict[str, Any]] = []
    for relative_path in data.get("part_files", []):
        fragment_path = catalog_path.parent / str(relative_path)
        with fragment_path.open("r", encoding="utf-8") as handle:
            fragment = json.load(handle)
        parts.extend(fragment.get("parts", []))

    return {**data, "parts": parts}


def midpoint_price(part: dict[str, Any]) -> float | None:
    low = part.get("price_min_usd")
    high = part.get("price_max_usd")
    if low is None or high is None:
        return None
    return (float(low) + float(high)) / 2.0


def llm_candidates(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [part for part in parts if part.get("llm_candidate", part.get("category") == "compute_node")]
