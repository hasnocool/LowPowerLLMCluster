# src/lowpower_llm_cluster/history.py
from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import Callable, Iterable, Sequence, TypeVar

from .discovery import ProductObservation, utc_now_iso

R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class ListingChange:
    source: str
    source_id: str
    change_type: str
    previous: str | float | bool | None
    current: str | float | bool | None


_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA temp_store=MEMORY;
PRAGMA cache_size=-8192;
CREATE TABLE IF NOT EXISTS refresh_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    listing_url TEXT NOT NULL,
    title TEXT NOT NULL,
    price REAL,
    currency TEXT NOT NULL,
    shipping REAL,
    in_stock INTEGER,
    payload_json TEXT NOT NULL,
    UNIQUE(run_id, source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_observations_identity_time
ON observations(source, source_id, id DESC);
CREATE TABLE IF NOT EXISTS listing_state (
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    listing_url TEXT NOT NULL,
    title TEXT NOT NULL,
    price REAL,
    currency TEXT NOT NULL,
    in_stock INTEGER,
    last_seen_at TEXT NOT NULL,
    missing_runs INTEGER NOT NULL DEFAULT 0,
    disappeared INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_listing_state_source ON listing_state(source);
"""


class CatalogHistory:
    """Single-writer async SQLite actor with one persistent worker-thread connection.

    SQLite never executes on the event loop. A dedicated one-thread executor avoids
    cross-thread connection sharing and write contention while WAL keeps readers cheap.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lpllm-sqlite")
        self._connection: sqlite3.Connection | None = None
        self._closed = False

    async def __aenter__(self) -> "CatalogHistory":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def _run(self, func: Callable[..., R], *args: object) -> R:
        if self._closed:
            raise RuntimeError("CatalogHistory is closed")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, partial(func, *args))

    def _ensure_connection_sync(self) -> sqlite3.Connection:
        if self._connection is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=30.0)
            connection.row_factory = sqlite3.Row
            connection.executescript(_SCHEMA)
            self._connection = connection
        return self._connection

    async def initialize(self) -> None:
        await self._run(self._initialize_sync)

    def _initialize_sync(self) -> None:
        self._ensure_connection_sync().commit()

    async def close(self) -> None:
        if self._closed:
            return
        await self._run(self._close_sync)
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _close_sync(self) -> None:
        if self._connection is not None:
            self._connection.commit()
            self._connection.close()
            self._connection = None

    async def record_refresh(
        self,
        observations: Sequence[ProductObservation],
        *,
        source_names: Iterable[str] | None = None,
        disappearance_after_runs: int = 2,
    ) -> tuple[str, tuple[ListingChange, ...]]:
        if disappearance_after_runs < 1:
            raise ValueError("disappearance_after_runs must be >= 1")
        return await self._run(
            self._record_refresh_sync,
            tuple(observations),
            tuple(source_names or ()),
            disappearance_after_runs,
        )

    def _record_refresh_sync(
        self,
        observations: Sequence[ProductObservation],
        source_names: Sequence[str],
        disappearance_after_runs: int,
    ) -> tuple[str, tuple[ListingChange, ...]]:
        connection = self._ensure_connection_sync()
        run_id = uuid.uuid4().hex
        started_at = utc_now_iso()
        changes: list[ListingChange] = []
        seen_by_source: dict[str, set[str]] = {}
        for item in observations:
            seen_by_source.setdefault(item.source, set()).add(item.source_id)
        if not source_names:
            source_names = tuple(seen_by_source)

        source_rows: list[sqlite3.Row] = []
        if source_names:
            placeholders = ",".join("?" for _ in source_names)
            source_rows = connection.execute(
                f"SELECT * FROM listing_state WHERE source IN ({placeholders})", source_names
            ).fetchall()
        previous_by_identity = {(row["source"], row["source_id"]): row for row in source_rows}

        observation_rows: list[tuple[object, ...]] = []
        upsert_rows: list[tuple[object, ...]] = []
        for item in observations:
            previous = previous_by_identity.get((item.source, item.source_id))
            current_stock = None if item.in_stock is None else int(item.in_stock)
            payload = json.dumps(asdict(item), sort_keys=True, separators=(",", ":"), default=str)
            observation_rows.append(
                (
                    run_id, item.source, item.source_id, item.observed_at, item.listing_url,
                    item.title, item.price, item.currency, item.shipping, current_stock, payload,
                )
            )
            upsert_rows.append(
                (
                    item.source, item.source_id, item.listing_url, item.title, item.price,
                    item.currency, current_stock, item.observed_at,
                )
            )
            if previous is not None:
                for field, kind in (
                    ("price", "price_changed"),
                    ("currency", "currency_changed"),
                    ("title", "title_changed"),
                    ("in_stock", "stock_changed"),
                ):
                    old = previous[field]
                    new = current_stock if field == "in_stock" else getattr(item, field)
                    if old != new:
                        if field == "in_stock":
                            old = None if old is None else bool(old)
                            new = None if new is None else bool(new)
                        changes.append(ListingChange(item.source, item.source_id, kind, old, new))
                if previous["disappeared"]:
                    changes.append(ListingChange(item.source, item.source_id, "reappeared", True, False))

        missing_updates: list[tuple[int, int, str, str]] = []
        for row in source_rows:
            if row["source_id"] in seen_by_source.get(row["source"], set()):
                continue
            missing_runs = int(row["missing_runs"]) + 1
            disappeared = int(missing_runs >= disappearance_after_runs)
            missing_updates.append((missing_runs, disappeared, row["source"], row["source_id"]))
            if disappeared and not row["disappeared"]:
                changes.append(ListingChange(row["source"], row["source_id"], "disappeared", False, True))

        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute("INSERT INTO refresh_runs(run_id, started_at) VALUES (?, ?)", (run_id, started_at))
            connection.executemany(
                """INSERT INTO observations(run_id, source, source_id, observed_at, listing_url, title, price, currency, shipping, in_stock, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                observation_rows,
            )
            connection.executemany(
                """INSERT INTO listing_state(source, source_id, listing_url, title, price, currency, in_stock, last_seen_at, missing_runs, disappeared)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
                   ON CONFLICT(source, source_id) DO UPDATE SET
                     listing_url=excluded.listing_url, title=excluded.title, price=excluded.price,
                     currency=excluded.currency, in_stock=excluded.in_stock, last_seen_at=excluded.last_seen_at,
                     missing_runs=0, disappeared=0""",
                upsert_rows,
            )
            connection.executemany(
                "UPDATE listing_state SET missing_runs = ?, disappeared = ? WHERE source = ? AND source_id = ?",
                missing_updates,
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        return run_id, tuple(changes)

    async def price_history(self, source: str, source_id: str, *, limit: int = 100) -> list[dict[str, object]]:
        return await self._run(self._price_history_sync, source, source_id, limit)

    def _price_history_sync(self, source: str, source_id: str, limit: int) -> list[dict[str, object]]:
        connection = self._ensure_connection_sync()
        rows = connection.execute(
            """SELECT observed_at, price, currency, shipping, in_stock
               FROM observations WHERE source = ? AND source_id = ?
               ORDER BY id DESC LIMIT ?""",
            (source, source_id, max(1, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]
