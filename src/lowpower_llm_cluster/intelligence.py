# src/lowpower_llm_cluster/intelligence.py
from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .catalog import load_catalog, project_root
from .market import load_fx


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _watchlists(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or project_root() / "data" / "market" / "watchlists.json"
    return list(_load(target, {"watchlists": []}).get("watchlists", []))


def _matches_watchlist(part: dict[str, Any] | None, listing: dict[str, Any] | None, watch: dict[str, Any]) -> bool:
    match = watch.get("match") or {}
    if not match:
        return True
    if part is not None:
        if match.get("part_ids") and part.get("id") not in set(match["part_ids"]):
            return False
        if match.get("categories") and part.get("category") not in set(match["categories"]):
            return False
        if match.get("max_power_w") is not None:
            watts = part.get("power_target_w")
            if watts is None or float(watts) > float(match["max_power_w"]):
                return False
        if match.get("min_memory_gb") is not None:
            memory = part.get("memory_capacity_gb") or part.get("max_memory_gb")
            if memory is None or float(memory) < float(match["min_memory_gb"]):
                return False
    text = " ".join(str(value or "") for value in ((part or {}).get("name"), (listing or {}).get("title"))).casefold()
    keywords = [str(value).casefold() for value in match.get("keywords", [])]
    if keywords and not any(keyword in text for keyword in keywords):
        return False
    sources = set(match.get("sources", []))
    if sources and (listing or {}).get("source") not in sources:
        return False
    return True


def _cad_total(row: dict[str, Any], fx: dict[str, float], tax_rate: float) -> float | None:
    currency = str(row.get("currency") or "").upper()
    shipping_currency = str(row.get("shipping_currency") or currency).upper()
    if currency not in fx or shipping_currency not in fx:
        return None
    item = float(row.get("price") or 0.0) * fx[currency]
    shipping = float(row.get("shipping") or 0.0) * fx[shipping_currency]
    return round((item + shipping) * (1.0 + tax_rate), 2)


def _price_alerts(
    parts: dict[str, dict[str, Any]],
    observations: list[dict[str, Any]],
    watchlists: list[dict[str, Any]],
    fx: dict[str, float],
    default_drop_pct: float,
    default_landed_change_pct: float,
    tax_rate: float,
) -> list[dict[str, Any]]:
    by_listing: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        by_listing[(str(row.get("source")), str(row.get("source_id")))].append(row)
    alerts: list[dict[str, Any]] = []
    for rows in by_listing.values():
        rows.sort(key=lambda row: str(row.get("observed_at", "")))
        if len(rows) < 2:
            continue
        previous, current = rows[-2], rows[-1]
        part = parts.get(str(current.get("part_id")))
        old_price = float(previous.get("price") or 0.0)
        new_price = float(current.get("price") or 0.0)
        if old_price <= 0:
            continue
        price_change_pct = ((new_price - old_price) / old_price) * 100.0
        old_landed = _cad_total(previous, fx, tax_rate)
        new_landed = _cad_total(current, fx, tax_rate)
        landed_change_pct = None
        if old_landed and new_landed:
            landed_change_pct = ((new_landed - old_landed) / old_landed) * 100.0

        watches = [watch for watch in watchlists if watch.get("enabled", True) and _matches_watchlist(part, current, watch)]
        if not watches:
            watches = [{"id": "default", "alerts": {}}]
        for watch in watches:
            settings = watch.get("alerts") or {}
            drop_threshold = float(settings.get("price_drop_pct", default_drop_pct))
            landed_threshold = float(settings.get("landed_cost_change_pct", default_landed_change_pct))
            if price_change_pct <= -drop_threshold:
                alerts.append({
                    "type": "price_drop", "severity": "high", "watchlist": watch.get("id", "default"),
                    "part_id": current.get("part_id"), "source": current.get("source"), "source_id": current.get("source_id"),
                    "title": current.get("title"), "old_price": old_price, "new_price": new_price, "currency": current.get("currency"),
                    "change_pct": round(price_change_pct, 2), "observed_at": current.get("observed_at"),
                    "reason": f"price dropped {abs(price_change_pct):.1f}% (threshold {drop_threshold:g}%)",
                })
            if landed_change_pct is not None and abs(landed_change_pct) >= landed_threshold:
                alerts.append({
                    "type": "landed_cost_change", "severity": "medium" if landed_change_pct > 0 else "high",
                    "watchlist": watch.get("id", "default"), "part_id": current.get("part_id"), "source": current.get("source"),
                    "source_id": current.get("source_id"), "title": current.get("title"), "old_landed_cad": old_landed,
                    "new_landed_cad": new_landed, "change_pct": round(landed_change_pct, 2), "observed_at": current.get("observed_at"),
                    "reason": f"landed cost changed {landed_change_pct:+.1f}% (threshold {landed_threshold:g}%)",
                })
    return alerts


def _lifecycle_alerts(parts: dict[str, dict[str, Any]], events: list[dict[str, Any]], observations: list[dict[str, Any]], watchlists: list[dict[str, Any]], since: str | None) -> list[dict[str, Any]]:
    latest_listing: dict[tuple[str, str], dict[str, Any]] = {}
    for row in observations:
        latest_listing[(str(row.get("source")), str(row.get("source_id")))] = row
    alerts: list[dict[str, Any]] = []
    for event in events:
        if since and str(event.get("observed_at", "")) <= since:
            continue
        if event.get("event") not in {"discovered", "reappeared"}:
            continue
        listing = latest_listing.get((str(event.get("source")), str(event.get("source_id"))), {})
        part = parts.get(str(listing.get("part_id")))
        watches = [watch for watch in watchlists if watch.get("enabled", True) and _matches_watchlist(part, listing, watch)]
        if not watches:
            watches = [{"id": "default", "alerts": {}}]
        for watch in watches:
            settings = watch.get("alerts") or {}
            alert_type = "stock_return" if event.get("event") == "reappeared" else "new_product"
            if settings.get(alert_type, True) is False:
                continue
            alerts.append({
                "type": alert_type, "severity": "high" if alert_type == "stock_return" else "medium",
                "watchlist": watch.get("id", "default"), "part_id": listing.get("part_id"), "source": event.get("source"),
                "source_id": event.get("source_id"), "title": listing.get("title") or event.get("title"),
                "url": listing.get("url") or event.get("url"), "observed_at": event.get("observed_at"),
                "reason": "listing returned after being absent" if alert_type == "stock_return" else "new listing appeared in a watched source/query scope",
            })
    return alerts


def _benchmark_signature(record: dict[str, Any]) -> tuple[Any, ...]:
    keys = (
        "part_id", "model", "model_variant", "quantization", "model_hash", "runtime", "runtime_version", "backend",
        "workload", "metric", "unit", "context_length", "prompt_length", "generation_length", "batch_size", "hardware_configuration",
    )
    return tuple(record.get(key) for key in keys)


def _benchmark_alerts(records: list[dict[str, Any]], watchlists: list[dict[str, Any]], parts: dict[str, dict[str, Any]], threshold_pct: float) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("source_type") not in {"measured_local", "community_measured", "vendor_measured"}:
            continue
        grouped[_benchmark_signature(record)].append(record)
    alerts: list[dict[str, Any]] = []
    for rows in grouped.values():
        rows.sort(key=lambda row: str(row.get("published_on") or row.get("ingested_at") or ""))
        if len(rows) < 2:
            continue
        old, new = rows[-2], rows[-1]
        old_value, new_value = float(old.get("value") or 0.0), float(new.get("value") or 0.0)
        if old_value == 0:
            continue
        change = ((new_value - old_value) / old_value) * 100.0
        part = parts.get(str(new.get("part_id")))
        watches = [watch for watch in watchlists if watch.get("enabled", True) and _matches_watchlist(part, None, watch)]
        if not watches:
            watches = [{"id": "default", "alerts": {}}]
        for watch in watches:
            local_threshold = float((watch.get("alerts") or {}).get("benchmark_change_pct", threshold_pct))
            if abs(change) < local_threshold:
                continue
            kind = "benchmark_improvement" if change > 0 else "benchmark_regression"
            alerts.append({
                "type": kind, "severity": "medium" if change > 0 else "high", "watchlist": watch.get("id", "default"),
                "part_id": new.get("part_id"), "model": new.get("model"), "runtime": new.get("runtime"), "workload": new.get("workload"),
                "metric": new.get("metric"), "unit": new.get("unit"), "old_value": old_value, "new_value": new_value,
                "change_pct": round(change, 2), "source_url": new.get("source_url"),
                "observed_at": new.get("published_on") or new.get("ingested_at"),
                "reason": f"compatible measured result changed {change:+.1f}% (threshold {local_threshold:g}%)",
            })
    return alerts


def generate_change_intelligence(
    *,
    price_path: Path | None = None,
    listing_state_path: Path | None = None,
    performance_path: Path | None = None,
    watchlists_path: Path | None = None,
    state_path: Path | None = None,
    output_path: Path | None = None,
    default_price_drop_pct: float = 10.0,
    default_landed_change_pct: float = 8.0,
    default_benchmark_change_pct: float = 10.0,
    tax_rate: float = 0.12,
) -> dict[str, Any]:
    root = project_root()
    price_path = price_path or root / "data" / "market" / "price-history.json"
    listing_state_path = listing_state_path or root / "data" / "market" / "listing-state.json"
    performance_path = performance_path or root / "data" / "evidence" / "performance.json"
    state_path = state_path or root / "data" / "market" / "intelligence-state.json"
    output_path = output_path or root / "reports" / "current" / "daily-changes.json"

    catalog = load_catalog()["parts"]
    parts = {str(part["id"]): part for part in catalog}
    prices = _load(price_path, {"observations": []}).get("observations", [])
    listing_state = _load(listing_state_path, {"events": []})
    performance = _load(performance_path, {"records": []}).get("records", [])
    watches = _watchlists(watchlists_path)
    prior = _load(state_path, {"last_generated_at": None})
    since = prior.get("last_generated_at")
    fx = load_fx()

    alerts = []
    alerts.extend(_price_alerts(parts, prices, watches, fx, default_price_drop_pct, default_landed_change_pct, tax_rate))
    alerts.extend(_lifecycle_alerts(parts, listing_state.get("events", []), prices, watches, since))
    alerts.extend(_benchmark_alerts(performance, watches, parts, default_benchmark_change_pct))

    # Price/benchmark history comparisons are inherently repeatable; dedupe by a stable event fingerprint.
    prior_fingerprints = set(prior.get("emitted_fingerprints", []))
    fresh: list[dict[str, Any]] = []
    for alert in alerts:
        fingerprint = json.dumps({key: alert.get(key) for key in ("type", "watchlist", "part_id", "source", "source_id", "observed_at", "old_price", "new_price", "old_value", "new_value")}, sort_keys=True)
        if fingerprint in prior_fingerprints:
            continue
        alert["fingerprint"] = fingerprint
        fresh.append(alert)
        prior_fingerprints.add(fingerprint)

    severity_order = {"high": 0, "medium": 1, "low": 2}
    fresh.sort(key=lambda alert: (severity_order.get(str(alert.get("severity")), 9), str(alert.get("type")), str(alert.get("title") or alert.get("part_id") or "")))
    generated_at = _now()
    summary = {
        "generated_at": generated_at,
        "since": since,
        "alert_count": len(fresh),
        "counts": dict(sorted({kind: sum(1 for row in fresh if row.get("type") == kind) for kind in {row.get("type") for row in fresh}}.items())),
        "alerts": fresh,
    }
    _write(output_path, summary)
    _write(state_path, {"last_generated_at": generated_at, "emitted_fingerprints": list(prior_fingerprints)[-5000:]})
    return summary


def render_daily_change_report(summary: dict[str, Any], *, max_items: int = 20) -> str:
    alerts = list(summary.get("alerts", []))
    lines = ["# Daily Market Changes", "", f"Generated: **{summary.get('generated_at')}**", ""]
    if not alerts:
        lines.extend(["No significant watched changes were detected in this refresh.", ""])
        return "\n".join(lines)
    lines.extend([f"**{len(alerts)} significant change(s)** detected.", "", "## Worth looking at", ""])
    for alert in alerts[:max_items]:
        subject = alert.get("title") or alert.get("part_id") or alert.get("source_id") or "unknown item"
        lines.append(f"- **{alert.get('type', 'change').replace('_', ' ').title()}** — {subject}: {alert.get('reason', '')}")
    if len(alerts) > max_items:
        lines.extend(["", f"_{len(alerts) - max_items} additional alert(s) are available in `daily-changes.json`._"])
    lines.extend(["", "Alerts are evidence-derived. Verify the live listing, shipping, tax and exact SKU before purchasing.", ""])
    return "\n".join(lines)
