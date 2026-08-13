from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict
from typing import Any, Mapping, Sequence

from .discovery import ProductObservation
from .resource_runtime import SchedulingRequirements
from .secure_store_base import _json_text


class SecureStoreTaskMixin:
    async def submit_cycle(self, sources: Sequence[dict[str, Any]], *, cycle_id: str | None = None) -> dict[str, Any]:
        return await self._run(self._submit_cycle_sync, tuple(sources), cycle_id or uuid.uuid4().hex)

    def _submit_cycle_sync(self, sources: Sequence[dict[str, Any]], cycle_id: str) -> dict[str, Any]:
        connection = self._conn()
        now = time.time()
        connection.execute("INSERT OR IGNORE INTO secure_cycles(cycle_id,created_at,canceled) VALUES (?,?,0)", (cycle_id, now))
        task_ids: list[str] = []
        for source in sources:
            name = str(source["name"])
            task_key = f"{cycle_id}:{name}"
            task_id = uuid.uuid5(uuid.NAMESPACE_URL, "secure:" + task_key).hex
            connection.execute(
                """INSERT OR IGNORE INTO secure_tasks(task_id,task_key,cycle_id,source_name,payload_json,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (task_id, task_key, cycle_id, name, _json_text(source), now, now),
            )
            task_ids.append(task_id)
        connection.commit()
        return {"cycle_id": cycle_id, "task_ids": task_ids}

    def _reclaim_expired(self, connection: sqlite3.Connection, now: float) -> None:
        connection.execute(
            """UPDATE secure_tasks SET state='queued',lease_owner=NULL,lease_expires_at=NULL,lease_epoch=NULL,updated_at=?
               WHERE state='leased' AND lease_expires_at IS NOT NULL AND lease_expires_at<?""",
            (now, now),
        )

    async def lease(
        self, worker_id: str, *, epoch: int, lease_s: float, capabilities: Sequence[str], labels: Mapping[str, str],
        resources: Mapping[str, Any], work_steal_after_s: float = 60.0,
    ) -> dict[str, Any] | None:
        return await self._run(
            self._lease_sync, worker_id, int(epoch), float(lease_s), tuple(capabilities), dict(labels), dict(resources), float(work_steal_after_s)
        )

    def _lease_sync(self, worker_id: str, epoch: int, lease_s: float, capabilities: Sequence[str], labels: Mapping[str, str], resources: Mapping[str, Any], work_steal_after_s: float) -> dict[str, Any] | None:
        connection = self._conn()
        now = time.time()
        connection.execute("BEGIN IMMEDIATE")
        try:
            leader = connection.execute("SELECT epoch,lease_expires_at FROM secure_leader WHERE singleton=1").fetchone()
            if int(leader["epoch"]) != epoch or float(leader["lease_expires_at"]) <= now:
                raise PermissionError("stale coordinator epoch")
            worker = connection.execute("SELECT state,quarantine_until FROM secure_workers WHERE worker_id=?", (worker_id,)).fetchone()
            if worker is None:
                raise PermissionError("worker is not registered")
            state = str(worker["state"])
            quarantine_until = worker["quarantine_until"]
            if state == "quarantined" and quarantine_until is not None and float(quarantine_until) <= now:
                state = "active"
                connection.execute("UPDATE secure_workers SET state='active',quarantine_until=NULL WHERE worker_id=?", (worker_id,))
            if state != "active":
                connection.commit()
                return None
            connection.execute("UPDATE secure_workers SET resources_json=?,last_seen=? WHERE worker_id=?", (_json_text(resources), now, worker_id))
            self._reclaim_expired(connection, now)
            rows = connection.execute(
                """SELECT t.* FROM secure_tasks t JOIN secure_cycles c ON c.cycle_id=t.cycle_id
                   WHERE t.state='queued' AND c.canceled=0 ORDER BY t.created_at,t.task_id LIMIT 256"""
            ).fetchall()
            candidates: list[tuple[float, sqlite3.Row, dict[str, Any], str]] = []
            caps = set(str(item) for item in capabilities)
            for row in rows:
                source = json.loads(row["payload_json"])
                requirements = SchedulingRequirements.from_source(source)
                allow_steal = now - float(row["created_at"]) >= work_steal_after_s
                matched, score, reason = requirements.matches(worker_id=worker_id, capabilities=caps, labels=labels, resources=resources, allow_steal=allow_steal)
                if matched:
                    candidates.append((score, row, source, reason))
            if not candidates:
                connection.commit()
                return None
            candidates.sort(key=lambda item: (-item[0], float(item[1]["created_at"]), str(item[1]["task_id"])))
            _, row, source, _ = candidates[0]
            expires = now + lease_s
            connection.execute(
                """UPDATE secure_tasks SET state='leased',lease_owner=?,lease_expires_at=?,heartbeat_at=?,attempts=attempts+1,lease_epoch=?,updated_at=? WHERE task_id=?""",
                (worker_id, expires, now, epoch, now, row["task_id"]),
            )
            connection.commit()
            return {
                "task_id": row["task_id"], "task_key": row["task_key"], "cycle_id": row["cycle_id"],
                "source_name": row["source_name"], "payload": source, "attempt": int(row["attempts"]) + 1,
                "lease_expires_at": expires, "epoch": epoch,
            }
        except BaseException:
            connection.rollback()
            raise

    def _lease_valid(self, connection: sqlite3.Connection, task_id: str, worker_id: str, epoch: int, now: float) -> bool:
        row = connection.execute(
            "SELECT state,lease_owner,lease_expires_at,lease_epoch FROM secure_tasks WHERE task_id=?", (task_id,)
        ).fetchone()
        leader = connection.execute("SELECT epoch,lease_expires_at FROM secure_leader WHERE singleton=1").fetchone()
        return bool(
            row and row["state"] == "leased" and row["lease_owner"] == worker_id and
            float(row["lease_expires_at"] or 0) > now and int(row["lease_epoch"] or -1) == epoch and
            int(leader["epoch"]) == epoch and float(leader["lease_expires_at"]) > now
        )

    async def heartbeat(self, task_id: str, worker_id: str, *, epoch: int, lease_s: float, resources: Mapping[str, Any]) -> bool:
        return bool(await self._run(self._heartbeat_sync, task_id, worker_id, int(epoch), float(lease_s), dict(resources)))

    def _heartbeat_sync(self, task_id: str, worker_id: str, epoch: int, lease_s: float, resources: Mapping[str, Any]) -> bool:
        connection = self._conn()
        now = time.time()
        cycle = connection.execute("SELECT c.canceled FROM secure_tasks t JOIN secure_cycles c ON c.cycle_id=t.cycle_id WHERE t.task_id=?", (task_id,)).fetchone()
        if cycle is None or bool(cycle["canceled"]) or not self._lease_valid(connection, task_id, worker_id, epoch, now):
            return False
        connection.execute("UPDATE secure_workers SET resources_json=?,last_seen=? WHERE worker_id=?", (_json_text(resources), now, worker_id))
        connection.execute("UPDATE secure_tasks SET heartbeat_at=?,lease_expires_at=?,updated_at=? WHERE task_id=?", (now, now + lease_s, now, task_id))
        connection.commit()
        return True

    async def add_batch(self, task_id: str, worker_id: str, batch_id: str, observations: Sequence[ProductObservation | dict[str, Any]], *, epoch: int) -> bool:
        allowed = bool(await self._run(self._can_mutate_lease_sync, task_id, worker_id, int(epoch)))
        if not allowed:
            raise PermissionError("worker does not hold current epoch task lease")
        payload = [asdict(item) if isinstance(item, ProductObservation) else dict(item) for item in observations]
        ref = await self.artifacts.put_json(payload)
        return bool(await self._run(self._add_batch_ref_sync, task_id, worker_id, batch_id, ref.sha256, len(payload), ref.size, int(epoch)))

    def _can_mutate_lease_sync(self, task_id: str, worker_id: str, epoch: int) -> bool:
        return self._lease_valid(self._conn(), task_id, worker_id, epoch, time.time())

    def _add_batch_ref_sync(self, task_id: str, worker_id: str, batch_id: str, sha256: str, count: int, byte_count: int, epoch: int) -> bool:
        connection = self._conn()
        now = time.time()
        if not self._lease_valid(connection, task_id, worker_id, epoch, now):
            raise PermissionError("worker does not hold current epoch task lease")
        cursor = connection.execute(
            "INSERT OR IGNORE INTO secure_batches(task_id,batch_id,sha256,observation_count,byte_count,created_at) VALUES (?,?,?,?,?,?)",
            (task_id, batch_id, sha256, count, byte_count, now),
        )
        connection.commit()
        return cursor.rowcount == 1

    async def complete(self, task_id: str, worker_id: str, *, epoch: int) -> bool:
        return bool(await self._run(self._complete_sync, task_id, worker_id, int(epoch)))

    def _complete_sync(self, task_id: str, worker_id: str, epoch: int) -> bool:
        connection = self._conn()
        now = time.time()
        if not self._lease_valid(connection, task_id, worker_id, epoch, now):
            return False
        connection.execute(
            "UPDATE secure_tasks SET state='completed',lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE task_id=?",
            (now, task_id),
        )
        connection.execute("UPDATE secure_workers SET failures=0,last_seen=? WHERE worker_id=?", (now, worker_id))
        connection.commit()
        return True

    async def fail(self, task_id: str, worker_id: str, error: str, *, epoch: int, requeue: bool, quarantine_after: int = 3, quarantine_s: float = 300.0) -> bool:
        return bool(await self._run(self._fail_sync, task_id, worker_id, error, int(epoch), bool(requeue), int(quarantine_after), float(quarantine_s)))

    def _fail_sync(self, task_id: str, worker_id: str, error: str, epoch: int, requeue: bool, quarantine_after: int, quarantine_s: float) -> bool:
        connection = self._conn()
        now = time.time()
        if not self._lease_valid(connection, task_id, worker_id, epoch, now):
            return False
        state = "queued" if requeue else "failed"
        connection.execute(
            "UPDATE secure_tasks SET state=?,error=?,lease_owner=NULL,lease_expires_at=NULL,lease_epoch=NULL,updated_at=? WHERE task_id=?",
            (state, error[:2000], now, task_id),
        )
        connection.execute("UPDATE secure_workers SET failures=failures+1,last_seen=? WHERE worker_id=?", (now, worker_id))
        failures = int(connection.execute("SELECT failures FROM secure_workers WHERE worker_id=?", (worker_id,)).fetchone()["failures"])
        if failures >= quarantine_after:
            connection.execute("UPDATE secure_workers SET state='quarantined',quarantine_until=? WHERE worker_id=?", (now + quarantine_s, worker_id))
        connection.commit()
        return True
