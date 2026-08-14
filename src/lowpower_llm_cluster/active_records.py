from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from .canonical_promotion import listing_identity


def _active_records_sync(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.exists():
        return {"path": str(path), "total": 0, "sources": [], "items": []}
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """SELECT s.source, s.source_id, s.listing_url, s.title, s.price, s.currency,
                  s.in_stock, s.last_seen_at, s.missing_runs, s.disappeared,
                  (SELECT o.payload_json FROM observations o
                   WHERE o.source=s.source AND o.source_id=s.source_id
                   ORDER BY o.id DESC LIMIT 1) AS payload_json
           FROM listing_state s
           WHERE s.disappeared=0
           ORDER BY s.last_seen_at DESC, s.source, s.source_id"""
    ).fetchall()
    sources = sorted({str(row["source"]) for row in rows})
    connection.close()

    items: list[dict[str, Any]] = []
    for row in rows:
        base = dict(row)
        payload_raw = base.pop("payload_json", None)
        payload: dict[str, Any] = {}
        if payload_raw:
            try:
                decoded = json.loads(str(payload_raw))
                if isinstance(decoded, dict):
                    payload = decoded
            except json.JSONDecodeError:
                payload = {}
        item = dict(payload)
        item.update({
            "source": base["source"],
            "source_id": base["source_id"],
            "listing_url": base["listing_url"],
            "title": base["title"],
            "price": base["price"],
            "currency": base["currency"],
            "in_stock": None if base["in_stock"] is None else bool(base["in_stock"]),
            "last_seen_at": base["last_seen_at"],
            "missing_runs": base["missing_runs"],
            "disappeared": bool(base["disappeared"]),
        })
        source, source_id = listing_identity(item)
        item["source"] = source
        item["source_id"] = source_id
        if not item.get("observed_at"):
            item["observed_at"] = item.get("last_seen_at")
        items.append(item)
    return {"path": str(path), "total": len(items), "sources": sources, "items": items}


async def active_records(path: Path) -> dict[str, Any]:
    return await asyncio.to_thread(_active_records_sync, path)
