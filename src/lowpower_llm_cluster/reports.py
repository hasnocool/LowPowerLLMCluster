# src/lowpower_llm_cluster/reports.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .catalog import llm_candidates, midpoint_price, project_root
from .evidence import verified_memory_gb
from .market import aggregate_compatible_performance, load_fx
from .scoring import catalog_score


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _active_keys(state_path: Path) -> set[tuple[str, str]] | None:
    if not state_path.exists():
        return None
    payload = _load(state_path, {"states": {}})
    return {
        (state.get("source"), state.get("source_id"))
        for state in payload.get("states", {}).values()
        if state.get("active", True)
    }


def _latest_observations(price_path: Path, state_path: Path) -> dict[str, dict[str, Any]]:
    payload = _load(price_path, {"observations": []})
    active = _active_keys(state_path)
    latest: dict[str, dict[str, Any]] = {}
    for row in payload.get("observations", []):
        part_id = row.get("part_id")
        if not part_id:
            continue
        if active is not None and (row.get("source"), row.get("source_id")) not in active:
            continue
        previous = latest.get(part_id)
        if previous is None or str(row.get("observed_at", "")) > str(previous.get("observed_at", "")):
            latest[part_id] = row
    return latest


def _confidence_weight(row: dict[str, Any] | None) -> float:
    if not row:
        return 0.35
    sku = float((row.get("configuration_confidence") or {}).get("score", 0.0))
    seller = float((row.get("seller_confidence") or {}).get("score", 0.0))
    return round((sku * 0.7) + (seller * 0.3), 3)


def _price_cad(part: dict[str, Any], observation: dict[str, Any] | None, fx: dict[str, float], tax_rate: float) -> tuple[float | None, str]:
    if observation:
        currency = str(observation.get("currency", "")).upper()
        shipping_currency = str(observation.get("shipping_currency") or currency).upper()
        if currency in fx and shipping_currency in fx:
            item = float(observation["price"]) * fx[currency]
            shipping = float(observation.get("shipping") or 0.0) * fx[shipping_currency]
            subtotal = item + shipping
            return round(subtotal * (1.0 + tax_rate), 2), "live_listing+shipping+tax"
    mid = midpoint_price(part)
    if mid is not None and "USD" in fx:
        return round(mid * fx["USD"] * (1.0 + tax_rate), 2), "catalog_midpoint+tax"
    return None, "unpriced"


def build_report_rows(
    parts: list[dict[str, Any]],
    *,
    tax_rate: float = 0.12,
    price_path: Path | None = None,
    state_path: Path | None = None,
    performance_path: Path | None = None,
    fx_path: Path | None = None,
) -> list[dict[str, Any]]:
    price_path = price_path or project_root() / "data" / "market" / "price-history.json"
    state_path = state_path or project_root() / "data" / "market" / "listing-state.json"
    performance_path = performance_path or project_root() / "data" / "evidence" / "performance.json"
    fx = load_fx(fx_path)
    latest = _latest_observations(price_path, state_path)
    rows: list[dict[str, Any]] = []
    for part in parts:
        if not part.get("llm_candidate", part.get("category") == "compute_node"):
            continue
        observation = latest.get(part["id"])
        price_cad, price_basis = _price_cad(part, observation, fx, tax_rate)
        groups = aggregate_compatible_performance(part["id"], performance_path, measured_only=True)
        measured = sorted(groups, key=lambda group: (group.get("count", 0), group.get("mean_confidence", 0.0)), reverse=True)
        rows.append({
            "id": part["id"],
            "name": part["name"],
            "category": part.get("category"),
            "price_cad": price_cad,
            "price_basis": price_basis,
            "memory_gb": verified_memory_gb(part),
            "power_target_w": part.get("power_target_w"),
            "risk_level": part.get("risk_level", "unknown"),
            "lifecycle_status": part.get("lifecycle_status", "unknown"),
            "market_confidence": _confidence_weight(observation),
            "live_observation": observation is not None,
            "measured_group_count": len(groups),
            "best_measured_group": measured[0] if measured else None,
        })
    return rows


def _market_named_reports(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    priced = [row for row in rows if row["price_cad"] is not None]

    def by_price(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(items, key=lambda row: (float(row["price_cad"]), -(row.get("memory_gb") or 0)))

    weird_categories = {"specialty_board", "decommissioned_accelerator", "fpga_accelerator", "adaptive_soc", "ai_asic_accelerator", "tpu_accelerator", "npu_accelerator"}
    return {
        "under-100": by_price([row for row in priced if row["price_cad"] <= 100]),
        "under-250": by_price([row for row in priced if row["price_cad"] <= 250]),
        "under-500": by_price([row for row in priced if row["price_cad"] <= 500]),
        "32gb-plus": by_price([row for row in priced if (row.get("memory_gb") or 0) >= 32]),
        "low-power": by_price([row for row in priced if row.get("power_target_w") is not None and float(row["power_target_w"]) <= 25]),
        "weird-bargains": by_price([row for row in priced if row.get("category") in weird_categories]),
        "eol-bargains": by_price([row for row in priced if row.get("category") == "decommissioned_accelerator" or str(row.get("lifecycle_status", "")).lower() in {"eol", "end_of_life", "discontinued", "decommissioned"}]),
        "measured-evidence": by_price([row for row in priced if row.get("measured_group_count", 0) > 0]),
    }


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


def _catalog_named_reports(parts: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
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


def named_reports(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Support both canonical market-report rows and catalog-level dashboard reports."""
    items = list(rows)
    if not items or "price_cad" in items[0]:
        return _market_named_reports(items)
    return _catalog_named_reports(items)


def render_report(rows: list[dict[str, Any]], title: str) -> str:
    lines = [title, "=" * len(title), "CAD price     RAM    W target  Market   Evidence  Candidate", "------------  -----  --------  -------  --------  ------------------------------------------"]
    for row in rows:
        price = f"CA${row['price_cad']:,.2f}" if row["price_cad"] is not None else "unknown"
        memory = f"{row['memory_gb']:g}GB" if row.get("memory_gb") is not None else "?"
        watts = f"{float(row['power_target_w']):g}W" if row.get("power_target_w") is not None else "?"
        market = f"{row['market_confidence']:.2f}" if row.get("live_observation") else "static"
        evidence = str(row.get("measured_group_count", 0))
        lines.append(f"{price:12}  {memory:5}  {watts:8}  {market:7}  {evidence:8}  {row['name']}")
    if not rows:
        lines.append("No candidates currently satisfy this report with the available FX/price evidence.")
    lines.extend(["", "Price basis is shown in machine-readable output; catalog fallbacks are not live quotes."])
    return "\n".join(lines)
