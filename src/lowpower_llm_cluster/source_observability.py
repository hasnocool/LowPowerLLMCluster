from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _status(row: dict[str, Any]) -> str:
    failure = str(row.get("failure_class") or "")
    if failure == "access_denied":
        return "access_blocked"
    if failure == "rate_limited":
        return "rate_limited"
    if failure == "tls_error":
        return "tls_failed"
    if failure in {"network_error", "timeout"}:
        return "network_failed"
    if failure:
        return "degraded"
    cycles = max(1, int(row.get("cycles_seen") or 0))
    successful = int(row.get("successful_cycles") or 0)
    unique = int(row.get("unique_observations") or 0)
    raw = max(unique, int(row.get("raw_observations") or 0))
    promotion_yield = float(row.get("promotion_yield") or 0.0)
    relevance = float((row.get("signals") or {}).get("llm_relevance") or 0.0)
    duplicate_rate = 1.0 - (unique / max(1, raw))
    if successful and unique == 0:
        return "healthy_empty"
    if raw >= 20 and duplicate_rate >= 0.85:
        return "duplicate_heavy"
    if unique >= 5 and relevance < 0.05:
        return "low_relevance"
    if promotion_yield > 0 or float(row.get("quality_score") or 0) >= 0.65:
        return "productive"
    if successful / cycles >= 0.8:
        return "healthy"
    return "degraded"


def _read_source_health_sync(history: Path, promotion_report: Path) -> dict[str, Any]:
    promotion = _load_json(promotion_report)
    promotion_by_source = promotion.get("by_source", {}) if isinstance(promotion.get("by_source"), dict) else {}
    if not history.exists():
        return {"total": 0, "summary": {}, "sources": []}
    connection = sqlite3.connect(f"file:{history}?mode=ro", uri=True, timeout=2.0)
    connection.row_factory = sqlite3.Row
    tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    quality_rows = connection.execute("SELECT * FROM source_quality").fetchall() if "source_quality" in tables else []
    cooldown = {
        str(row["source"]): dict(row)
        for row in connection.execute("SELECT * FROM source_cooldown").fetchall()
    } if "source_cooldown" in tables else {}
    connection.close()

    rows: list[dict[str, Any]] = []
    summary: dict[str, int] = {}
    for raw in quality_rows:
        row = dict(raw)
        source = str(row.get("source") or "")
        row.update(cooldown.get(source, {}))
        promo = promotion_by_source.get(source, {}) if isinstance(promotion_by_source.get(source), dict) else {}
        row["promotion_records"] = int(promo.get("records", 0) or 0)
        row["promotion_ready"] = int(promo.get("promotion_ready", 0) or 0)
        row["promotion_held"] = int(promo.get("held", 0) or 0)
        row["promotion_yield"] = float(promo.get("promotion_yield", 0.0) or 0.0)
        cycles = max(1, int(row.get("cycles_seen") or 0))
        unique = int(row.get("unique_observations") or 0)
        raw_count = max(unique, int(row.get("raw_observations") or 0))
        row["success_rate"] = round(int(row.get("successful_cycles") or 0) / cycles, 4)
        row["duplicate_rate"] = round(1.0 - unique / max(1, raw_count), 4)
        row["avg_unique_per_cycle"] = round(unique / cycles, 3)
        row["status"] = _status(row)
        summary[row["status"]] = summary.get(row["status"], 0) + 1
        rows.append(row)
    rows.sort(key=lambda item: (-float(item.get("quality_score") or 0), str(item.get("source") or "")))
    return {
        "total": len(rows),
        "summary": dict(sorted(summary.items())),
        "promotion_generated_at": promotion.get("generated_at"),
        "sources": rows,
    }


async def read_source_health(history: Path, promotion_report: Path) -> dict[str, Any]:
    return await asyncio.to_thread(_read_source_health_sync, history, promotion_report)
