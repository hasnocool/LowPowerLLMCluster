from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .content_store import ContentAddressedStore

_SECURE_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS secure_cycles(
  cycle_id TEXT PRIMARY KEY, created_at REAL NOT NULL, canceled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS secure_tasks(
  task_id TEXT PRIMARY KEY, task_key TEXT NOT NULL UNIQUE, cycle_id TEXT NOT NULL,
  source_name TEXT NOT NULL, payload_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
  lease_owner TEXT, lease_expires_at REAL, heartbeat_at REAL, attempts INTEGER NOT NULL DEFAULT 0,
  lease_epoch INTEGER, error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_secure_tasks_state_created ON secure_tasks(state, created_at);
CREATE INDEX IF NOT EXISTS idx_secure_tasks_cycle ON secure_tasks(cycle_id);
CREATE TABLE IF NOT EXISTS secure_batches(
  task_id TEXT NOT NULL, batch_id TEXT NOT NULL, sha256 TEXT NOT NULL, observation_count INTEGER NOT NULL,
  byte_count INTEGER NOT NULL, created_at REAL NOT NULL,
  PRIMARY KEY(task_id,batch_id)
);
CREATE TABLE IF NOT EXISTS secure_workers(
  worker_id TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT 'active', capabilities_json TEXT NOT NULL DEFAULT '[]',
  labels_json TEXT NOT NULL DEFAULT '{}', resources_json TEXT NOT NULL DEFAULT '{}', last_seen REAL NOT NULL,
  failures INTEGER NOT NULL DEFAULT 0, quarantine_until REAL
);
CREATE TABLE IF NOT EXISTS secure_leader(
  singleton INTEGER PRIMARY KEY CHECK(singleton=1), leader_id TEXT, epoch INTEGER NOT NULL DEFAULT 0,
  lease_expires_at REAL NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO secure_leader(singleton,leader_id,epoch,lease_expires_at) VALUES (1,NULL,0,0);
"""


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _decode_json_bytes(value: bytes) -> Any:
    return json.loads(value.decode("utf-8"))


@dataclass(frozen=True, slots=True)
class LeaderState:
    leader_id: str | None
    epoch: int
    lease_expires_at: float

    @property
    def active(self) -> bool:
        return bool(self.leader_id) and self.lease_expires_at > time.time()


class SecureStoreBase:
    """Durable v2 coordinator store with capability leases and epoch fencing."""

    def __init__(self, path: Path | str, artifact_store: ContentAddressedStore) -> None:
        self.path = Path(path)
        self.artifacts = artifact_store
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lpllm-secure-sqlite")
        self._connection: sqlite3.Connection | None = None
        self._closed = False

    async def __aenter__(self) -> "SecureDistributedStore":
        await self.initialize()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def _run(self, fn: Callable[..., Any], *args: Any) -> Any:
        if self._closed:
            raise RuntimeError("secure distributed store closed")
        return await asyncio.get_running_loop().run_in_executor(self._executor, partial(fn, *args))

    def _conn(self) -> sqlite3.Connection:
        if self._connection is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=30.0)
            connection.row_factory = sqlite3.Row
            connection.executescript(_SECURE_SCHEMA)
            connection.commit()
            self._connection = connection
        return self._connection

    async def initialize(self) -> None:
        await self.artifacts.initialize()
        await self._run(lambda: self._conn().commit())

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

    async def acquire_leader(self, node_id: str, *, lease_s: float = 10.0) -> LeaderState:
        return await self._run(self._acquire_leader_sync, node_id, float(lease_s))

    def _acquire_leader_sync(self, node_id: str, lease_s: float) -> LeaderState:
        connection = self._conn()
        now = time.time()
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute("SELECT leader_id,epoch,lease_expires_at FROM secure_leader WHERE singleton=1").fetchone()
            leader_id, epoch, expires = row["leader_id"], int(row["epoch"]), float(row["lease_expires_at"])
            if leader_id == node_id and expires > now:
                connection.execute("UPDATE secure_leader SET lease_expires_at=? WHERE singleton=1", (now + lease_s,))
                connection.commit()
                return LeaderState(node_id, epoch, now + lease_s)
            if leader_id is None or expires <= now:
                epoch += 1
                connection.execute("UPDATE secure_leader SET leader_id=?,epoch=?,lease_expires_at=? WHERE singleton=1", (node_id, epoch, now + lease_s))
                connection.commit()
                return LeaderState(node_id, epoch, now + lease_s)
            connection.commit()
            return LeaderState(str(leader_id), epoch, expires)
        except BaseException:
            connection.rollback()
            raise

    async def leader_state(self) -> LeaderState:
        return await self._run(self._leader_state_sync)

    def _leader_state_sync(self) -> LeaderState:
        row = self._conn().execute("SELECT leader_id,epoch,lease_expires_at FROM secure_leader WHERE singleton=1").fetchone()
        return LeaderState(None if row["leader_id"] is None else str(row["leader_id"]), int(row["epoch"]), float(row["lease_expires_at"]))

    async def register_worker(self, worker_id: str, *, capabilities: Sequence[str], labels: Mapping[str, str], resources: Mapping[str, Any]) -> dict[str, Any]:
        return await self._run(self._register_worker_sync, worker_id, tuple(capabilities), dict(labels), dict(resources))

    def _register_worker_sync(self, worker_id: str, capabilities: Sequence[str], labels: Mapping[str, str], resources: Mapping[str, Any]) -> dict[str, Any]:
        connection = self._conn()
        now = time.time()
        existing = connection.execute("SELECT state,quarantine_until FROM secure_workers WHERE worker_id=?", (worker_id,)).fetchone()
        state = "active" if existing is None else str(existing["state"])
        quarantine = None if existing is None else existing["quarantine_until"]
        if state == "quarantined" and quarantine is not None and float(quarantine) <= now:
            state, quarantine = "active", None
        connection.execute(
            """INSERT INTO secure_workers(worker_id,state,capabilities_json,labels_json,resources_json,last_seen,failures,quarantine_until)
               VALUES (?,?,?,?,?,?,0,?)
               ON CONFLICT(worker_id) DO UPDATE SET state=?,capabilities_json=?,labels_json=?,resources_json=?,last_seen=?,quarantine_until=?""",
            (worker_id, state, _json_text(sorted(set(capabilities))), _json_text(labels), _json_text(resources), now, quarantine,
             state, _json_text(sorted(set(capabilities))), _json_text(labels), _json_text(resources), now, quarantine),
        )
        connection.commit()
        return {"worker_id": worker_id, "state": state, "quarantine_until": quarantine}

    async def list_workers(self) -> list[dict[str, Any]]:
        return await self._run(self._list_workers_sync)

    def _list_workers_sync(self) -> list[dict[str, Any]]:
        rows = self._conn().execute("SELECT * FROM secure_workers ORDER BY worker_id").fetchall()
        return [{
            "worker_id": row["worker_id"], "state": row["state"], "capabilities": json.loads(row["capabilities_json"]),
            "labels": json.loads(row["labels_json"]), "resources": json.loads(row["resources_json"]),
            "last_seen": row["last_seen"], "failures": row["failures"], "quarantine_until": row["quarantine_until"],
        } for row in rows]

    async def set_worker_state(self, worker_id: str, state: str) -> bool:
        if state not in {"active", "draining", "quarantined"}:
            raise ValueError("invalid worker state")
        return bool(await self._run(self._set_worker_state_sync, worker_id, state))

    def _set_worker_state_sync(self, worker_id: str, state: str) -> bool:
        connection = self._conn()
        cursor = connection.execute("UPDATE secure_workers SET state=?,last_seen=? WHERE worker_id=?", (state, time.time(), worker_id))
        connection.commit()
        return cursor.rowcount == 1
