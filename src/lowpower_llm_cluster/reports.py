# src/lowpower_llm_cluster/reports.py
from __future__ import annotations

from typing import Any, Iterable

from .catalog import llm_candidates, midpoint_price
from .evidence import verified_memory_gb
from .scoring import catalog_score


def published_power_boundary(part: dict[str, Any]) -> tuple[float | None, str]:
    """Return an explicitly scoped published/estimated boundary, never guessed node watts."""
    if part.get("power_max_w") is not None:
        return float(part["power_max_w"]), str(part.get("power_scope", "published_unspecified_scope"))
    if part.get("power_target_w") is not None:
        return float(part["power_target_w"]), str(part.get("power_scope", "published_or_estimated_target_scope"))
    if part.get("ctdp_min_w") is not None:
        return float(part["ctdp_min_w"]), "processor_ctdp_not_complete_node"
    if part.get("default_tdp_w") is not None:
        return float(part["default_tdp_w"]), "processor_tdp_not_complete_node"
    return None, "unknown"


def filter_catalog(
    parts: Iterable[dict[str, Any]], *, max_price: float | None = None, min_memory_gb: float | None = None,
    max_power_w: float | None = None, lifecycle: str | None = None, weird_only: bool = False,
) -> list[dict[str, Any]]:
    rows = list(parts)
    if max_price is not None:
        rows = [part for part in rows if midpoint_price(part) is not None and midpoint_price(part) <= max_price]
    if min_memory_gb is not None:
        rows = [part for part in rows if (verified_memory_gb(part) or 0) >= min_memory_gb]
    if max_power_w is not None:
        rows = [part for part in rows if (published_power_boundary(part)[0] or float("inf")) <= max_power_w]
    if lifecycle:
        rows = [part for part in rows if lifecycle.lower() in str(part.get("lifecycle_status", "")).lower()]
    if weird_only:
        mainstream = {"mini_pc", "edge_ai_developer_kit", "control_plane"}
        rows = [part for part in rows if str(part.get("hardware_class", "")) not in mainstream]
    rows.sort(key=lambda part: (catalog_score(part), -(midpoint_price(part) or 1e12)), reverse=True)
    return rows


def named_reports(parts: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    candidates = llm_candidates(list(parts))
    return {
        "best_under_100": filter_catalog(candidates, max_price=100)[:20],
        "best_under_200": filter_catalog(candidates, max_price=200)[:20],
        "best_under_500": filter_catalog(candidates, max_price=500)[:20],
        "high_memory_bargains": filter_catalog(candidates, max_price=500, min_memory_gb=32)[:20],
        "low_power_nodes": filter_catalog(candidates, max_power_w=25)[:20],
        "weird_hardware": filter_catalog(candidates, weird_only=True)[:20],
        "eol_bargains": [part for part in filter_catalog(candidates) if any(token in str(part.get("lifecycle_status", "")).lower() for token in ("eol", "discontinued", "legacy", "secondary"))][:20],
    }
