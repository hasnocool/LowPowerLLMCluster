# src/lowpower_llm_cluster/reports.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalog import midpoint_price, project_root
from .evidence import verified_memory_gb
from .market import aggregate_compatible_performance, load_fx


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


def named_reports(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    priced = [row for row in rows if row["price_cad"] is not None]
    by_price = lambda items: sorted(items, key=lambda row: (float(row["price_cad"]), -(row.get("memory_gb") or 0)))
    weird_categories = {"specialty_board", "decommissioned_accelerator", "fpga_accelerator", "adaptive_soc", "ai_asic_accelerator", "tpu_accelerator", "npu_accelerator"}
    reports = {
        "under-100": by_price([row for row in priced if row["price_cad"] <= 100]),
        "under-250": by_price([row for row in priced if row["price_cad"] <= 250]),
        "under-500": by_price([row for row in priced if row["price_cad"] <= 500]),
        "32gb-plus": by_price([row for row in priced if (row.get("memory_gb") or 0) >= 32]),
        "low-power": by_price([row for row in priced if row.get("power_target_w") is not None and float(row["power_target_w"]) <= 25]),
        "weird-bargains": by_price([row for row in priced if row.get("category") in weird_categories]),
        "eol-bargains": by_price([row for row in priced if row.get("category") == "decommissioned_accelerator" or str(row.get("lifecycle_status", "")).lower() in {"eol", "end_of_life", "discontinued", "decommissioned"}]),
        "measured-evidence": by_price([row for row in priced if row.get("measured_group_count", 0) > 0]),
    }
    return reports


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
