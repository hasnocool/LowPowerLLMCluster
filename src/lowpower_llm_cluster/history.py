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
from typing import Callable, Iterable, Mapping, Sequence, TypeVar

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
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running'
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
    """Single-writer async SQLite actor supporting incremental refresh batches."""

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
            columns = {row[1] for row in connection.execute("PRAGMA table_info(refresh_runs)").fetchall()}
            if "completed_at" not in columns:
                connection.execute("ALTER TABLE refresh_runs ADD COLUMN completed_at TEXT")
            if "status" not in columns:
                connection.execute("ALTER TABLE refresh_runs ADD COLUMN status TEXT NOT NULL DEFAULT 'completed'")
            connection.commit()
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

    async def begin_refresh(self) -> str:
        return await self._run(self._begin_refresh_sync)

    def _begin_refresh_sync(self) -> str:
        connection = self._ensure_connection_sync()
        run_id = uuid.uuid4().hex
        connection.execute(
            "INSERT INTO refresh_runs(run_id, started_at, status) VALUES (?, ?, 'running')",
            (run_id, utc_now_iso()),
        )
        connection.commit()
        return run_id

    async def abort_refresh(self, run_id: str) -> None:
        await self._run(self._abort_refresh_sync, run_id)

    def _abort_refresh_sync(self, run_id: str) -> None:
        connection = self._ensure_connection_sync()
        connection.execute(
            "UPDATE refresh_runs SET completed_at = ?, status = 'aborted' WHERE run_id = ? AND status = 'running'",
            (utc_now_iso(), run_id),
        )
        connection.commit()

    async def record_batch(self, run_id: str, observations: Sequence[ProductObservation]) -> tuple[ListingChange, ...]:
        if not observations:
            return ()
        return await self._run(self._record_batch_sync, run_id, tuple(observations))

    def _record_batch_sync(self, run_id: str, observations: Sequence[ProductObservation]) -> tuple[ListingChange, ...]:
        connection = self._ensure_connection_sync()
        changes: list[ListingChange] = []
        sources = tuple(sorted({item.source for item in observations}))
        previous_rows: list[sqlite3.Row] = []
        if sources:
            placeholders = ",".join("?" for _ in sources)
            previous_rows = connection.execute(
                f"SELECT * FROM listing_state WHERE source IN ({placeholders})", sources
            ).fetchall()
        wanted = {(item.source, item.source_id) for item in observations}
        previous_by_identity = {
            (row["source"], row["source_id"]): row
            for row in previous_rows
            if (row["source"], row["source_id"]) in wanted
        }

        observation_rows: list[tuple[object, ...]] = []
        upsert_rows: list[tuple[object, ...]] = []
        for item in observations:
            previous = previous_by_identity.get((item.source, item.source_id))
            current_stock = None if item.in_stock is None else int(item.in_stock)
            payload = json.dumps(asdict(item), sort_keys=True, separators=(",", ":"), default=str)
            observation_rows.append((
                run_id, item.source, item.source_id, item.observed_at, item.listing_url,
                item.title, item.price, item.currency, item.shipping, current_stock, payload,
            ))
            upsert_rows.append((
                item.source, item.source_id, item.listing_url, item.title, item.price,
                item.currency, current_stock, item.observed_at,
            ))
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

        connection.execute("BEGIN IMMEDIATE")
        try:
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
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        return tuple(changes)

    async def finish_refresh(
        self,
        run_id: str,
        *,
        source_names: Iterable[str],
        seen_by_source: Mapping[str, set[str]],
        disappearance_after_runs: int = 2,
    ) -> tuple[ListingChange, ...]:
        if disappearance_after_runs < 1:
            raise ValueError("disappearance_after_runs must be >= 1")
        frozen_seen = {source: frozenset(ids) for source, ids in seen_by_source.items()}
        return await self._run(
            self._finish_refresh_sync,
            run_id,
            tuple(source_names),
            frozen_seen,
            disappearance_after_runs,
        )

    def _finish_refresh_sync(
        self,
        run_id: str,
        source_names: Sequence[str],
        seen_by_source: Mapping[str, frozenset[str]],
        disappearance_after_runs: int,
    ) -> tuple[ListingChange, ...]:
        connection = self._ensure_connection_sync()
        changes: list[ListingChange] = []
        source_rows: list[sqlite3.Row] = []
        if source_names:
            placeholders = ",".join("?" for _ in source_names)
            source_rows = connection.execute(
                f"SELECT source, source_id, missing_runs, disappeared FROM listing_state WHERE source IN ({placeholders})",
                tuple(source_names),
            ).fetchall()
        missing_updates: list[tuple[int, int, str, str]] = []
        for row in source_rows:
            if row["source_id"] in seen_by_source.get(row["source"], frozenset()):
                continue
            missing_runs = int(row["missing_runs"]) + 1
            disappeared = int(missing_runs >= disappearance_after_runs)
            missing_updates.append((missing_runs, disappeared, row["source"], row["source_id"]))
            if disappeared and not row["disappeared"]:
                changes.append(ListingChange(row["source"], row["source_id"], "disappeared", False, True))

        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.executemany(
                "UPDATE listing_state SET missing_runs = ?, disappeared = ? WHERE source = ? AND source_id = ?",
                missing_updates,
            )
            connection.execute(
                "UPDATE refresh_runs SET completed_at = ?, status = 'completed' WHERE run_id = ?",
                (utc_now_iso(), run_id),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        return tuple(changes)

    async def record_refresh(
        self,
        observations: Sequence[ProductObservation],
        *,
        source_names: Iterable[str] | None = None,
        disappearance_after_runs: int = 2,
    ) -> tuple[str, tuple[ListingChange, ...]]:
        """Compatibility wrapper over the incremental refresh API."""
        observations = tuple(observations)
        names = tuple(source_names or sorted({item.source for item in observations}))
        seen: dict[str, set[str]] = {}
        for item in observations:
            seen.setdefault(item.source, set()).add(item.source_id)
        run_id = await self.begin_refresh()
        changes = list(await self.record_batch(run_id, observations))
        changes.extend(await self.finish_refresh(
            run_id,
            source_names=names,
            seen_by_source=seen,
            disappearance_after_runs=disappearance_after_runs,
        ))
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
