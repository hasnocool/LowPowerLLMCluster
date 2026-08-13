from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any


class SecureStoreResultsMixin:
    async def cancel_cycle(self, cycle_id: str) -> bool:
        return bool(await self._run(self._cancel_cycle_sync, cycle_id))

    def _cancel_cycle_sync(self, cycle_id: str) -> bool:
        connection = self._conn()
        now = time.time()
        cursor = connection.execute("UPDATE secure_cycles SET canceled=1 WHERE cycle_id=?", (cycle_id,))
        connection.execute(
            "UPDATE secure_tasks SET state='canceled',lease_owner=NULL,lease_expires_at=NULL,lease_epoch=NULL,updated_at=? WHERE cycle_id=? AND state IN ('queued','leased')",
            (now, cycle_id),
        )
        connection.commit()
        return cursor.rowcount == 1

    async def cycle_status(self, cycle_id: str) -> dict[str, Any]:
        return await self._run(self._cycle_status_sync, cycle_id)

    def _cycle_status_sync(self, cycle_id: str) -> dict[str, Any]:
        connection = self._conn()
        cycle = connection.execute("SELECT canceled,created_at FROM secure_cycles WHERE cycle_id=?", (cycle_id,)).fetchone()
        rows = connection.execute("SELECT state,COUNT(*) n FROM secure_tasks WHERE cycle_id=? GROUP BY state", (cycle_id,)).fetchall()
        counts = {str(row["state"]): int(row["n"]) for row in rows}
        total = sum(counts.values())
        terminal = sum(counts.get(state, 0) for state in ("completed", "failed", "canceled"))
        return {
            "cycle_id": cycle_id, "counts": counts, "total": total, "terminal": terminal,
            "done": total > 0 and terminal == total, "canceled": bool(cycle["canceled"]) if cycle else False,
            "created_at": None if cycle is None else cycle["created_at"],
        }

    async def result_refs(self, cycle_id: str) -> list[dict[str, Any]]:
        """Return only small metadata refs; observation payloads remain in CAS."""
        return await self._run(self._result_refs_sync, cycle_id)

    def _result_refs_sync(self, cycle_id: str) -> list[dict[str, Any]]:
        rows = self._conn().execute(
            """SELECT t.task_id,t.source_name,t.state,t.error,b.batch_id,b.sha256,b.observation_count,b.byte_count
               FROM secure_tasks t LEFT JOIN secure_batches b ON b.task_id=t.task_id
               WHERE t.cycle_id=? ORDER BY t.source_name,b.created_at,b.batch_id""",
            (cycle_id,),
        ).fetchall()
        return [{
            "task_id": row["task_id"], "source_name": row["source_name"], "state": row["state"],
            "error": row["error"] or "", "batch_id": row["batch_id"], "sha256": row["sha256"],
            "observation_count": row["observation_count"] or 0, "byte_count": row["byte_count"] or 0,
        } for row in rows]

    async def backup(self, destination: Path | str) -> Path:
        destination = Path(destination)
        return await self._run(self._backup_sync, destination)

    def _backup_sync(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(destination)
        try:
            self._conn().backup(target)
            target.commit()
        finally:
            target.close()
        return destination

    async def referenced_hashes(self) -> set[str]:
        return set(await self._run(lambda: [str(row[0]) for row in self._conn().execute("SELECT DISTINCT sha256 FROM secure_batches").fetchall()]))
