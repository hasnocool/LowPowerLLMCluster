from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

from .discovery import utc_now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_type TEXT NOT NULL,
    discovered_from TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'candidate',
    active INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(source_type, source_url)
);
CREATE INDEX IF NOT EXISTS idx_source_candidates_active_score
ON source_candidates(active, status, score DESC);
CREATE INDEX IF NOT EXISTS idx_source_candidates_domain
ON source_candidates(domain);
"""


class SourceCandidateStore:
    """Small SQLite registry for sources learned by the continuous scanner."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.executescript(_SCHEMA)
        return connection

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        with self._connect() as connection:
            connection.commit()

    async def upsert(self, records: Sequence[Mapping[str, Any]]) -> int:
        if not records:
            return 0
        return await asyncio.to_thread(self._upsert_sync, tuple(records))

    def _upsert_sync(self, records: Sequence[Mapping[str, Any]]) -> int:
        now = utc_now_iso()
        rows: list[tuple[object, ...]] = []
        for item in records:
            metadata = item.get("metadata", {})
            rows.append((
                str(item.get("domain", "")), str(item.get("source_url", "")),
                str(item.get("source_type", "")), str(item.get("discovered_from", "")),
                now, now, float(item.get("score", 0.0)), str(item.get("status", "candidate")),
                int(bool(item.get("active", False))),
                json.dumps(metadata if isinstance(metadata, Mapping) else {}, sort_keys=True, separators=(",", ":"), default=str),
            ))
        with self._connect() as connection:
            connection.executemany(
                """INSERT INTO source_candidates(
                       domain, source_url, source_type, discovered_from,
                       first_seen_at, last_seen_at, score, status, active, metadata_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_type, source_url) DO UPDATE SET
                       domain=excluded.domain,
                       discovered_from=excluded.discovered_from,
                       last_seen_at=excluded.last_seen_at,
                       score=MAX(source_candidates.score, excluded.score),
                       status=CASE WHEN source_candidates.status='verified' THEN 'verified' ELSE excluded.status END,
                       active=MAX(source_candidates.active, excluded.active),
                       metadata_json=excluded.metadata_json""",
                rows,
            )
            connection.commit()
        return len(rows)

    async def active(self, *, limit: int = 100, min_score: float = 0.0) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._active_sync, max(1, int(limit)), float(min_score))

    def _active_sync(self, limit: int, min_score: float) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT domain, source_url, source_type, discovered_from, score, status, active, metadata_json
                   FROM source_candidates
                   WHERE active=1 AND status='verified' AND score >= ?
                   ORDER BY score DESC, last_seen_at DESC LIMIT ?""",
                (min_score, limit),
            ).fetchall()
        values: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(str(item.pop("metadata_json", "{}")))
            except json.JSONDecodeError:
                item["metadata"] = {}
            item["active"] = bool(item.get("active"))
            values.append(item)
        return values

    async def summary(self) -> dict[str, int]:
        return await asyncio.to_thread(self._summary_sync)

    def _summary_sync(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, active, COUNT(*) AS count FROM source_candidates GROUP BY status, active"
            ).fetchall()
        summary = {"total": 0, "verified": 0, "candidate": 0, "active": 0}
        for row in rows:
            count = int(row["count"])
            summary["total"] += count
            summary[str(row["status"])] = summary.get(str(row["status"]), 0) + count
            if row["active"]:
                summary["active"] += count
        return summary
