# src/lowpower_llm_cluster/catalog.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    catalog_path = path or project_root() / "data" / "parts.json"
    with catalog_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def midpoint_price(part: dict[str, Any]) -> float:
    low = float(part["price_min_usd"])
    high = float(part["price_max_usd"])
    return (low + high) / 2.0


def llm_candidates(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [part for part in parts if part.get("llm_candidate", part.get("category") == "compute_node")]
