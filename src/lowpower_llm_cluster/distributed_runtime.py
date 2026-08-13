from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Sequence

from aiohttp import ClientSession, web

from .discovery import ProductObservation

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
CREATE TABLE IF NOT EXISTS cycles(cycle_id TEXT PRIMARY KEY, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tasks(
  task_id TEXT PRIMARY KEY, task_key TEXT NOT NULL UNIQUE, cycle_id TEXT NOT NULL,
  source_name TEXT NOT NULL, payload_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
  lease_owner TEXT, lease_expires_at REAL, heartbeat_at REAL, attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_state_created ON tasks(state, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_cycle ON tasks(cycle_id);
CREATE TABLE IF NOT EXISTS batches(
  task_id TEXT NOT NULL, batch_id TEXT NOT NULL, payload_json TEXT NOT NULL, created_at REAL NOT NULL,
  PRIMARY KEY(task_id, batch_id)
);
"""


class DistributedTaskStore:
    """Durable single-writer coordinator store for leases, heartbeats and idempotent batches."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lpllm-dist-sqlite")
        self._connection: sqlite3.Connection | None = None
        self._closed = False

    async def __aenter__(self) -> "DistributedTaskStore":
        await self.initialize()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def _run(self, function: Callable[..., Any], *args: Any) -> Any:
        if self._closed:
            raise RuntimeError("distributed task store closed")
        return await asyncio.get_running_loop().run_in_executor(self._executor, partial(function, *args))

    def _conn(self) -> sqlite3.Connection:
        if self._connection is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=30.0)
            connection.row_factory = sqlite3.Row
            connection.executescript(_SCHEMA)
            connection.commit()
            self._connection = connection
        return self._connection

    async def initialize(self) -> None:
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

    async def submit_cycle(self, sources: Sequence[dict[str, Any]], *, cycle_id: str | None = None) -> dict[str, Any]:
        return await self._run(self._submit_cycle_sync, tuple(sources), cycle_id or uuid.uuid4().hex)

    def _submit_cycle_sync(self, sources: Sequence[dict[str, Any]], cycle_id: str) -> dict[str, Any]:
        connection = self._conn()
        now = time.time()
        connection.execute("INSERT OR IGNORE INTO cycles(cycle_id,created_at) VALUES (?,?)", (cycle_id, now))
        task_ids: list[str] = []
        for source in sources:
            name = str(source["name"])
            task_key = f"{cycle_id}:{name}"
            task_id = uuid.uuid5(uuid.NAMESPACE_URL, task_key).hex
            connection.execute(
                """INSERT OR IGNORE INTO tasks(task_id,task_key,cycle_id,source_name,payload_json,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (task_id, task_key, cycle_id, name, json.dumps(source, sort_keys=True), now, now),
            )
            task_ids.append(task_id)
        connection.commit()
        return {"cycle_id": cycle_id, "task_ids": task_ids}

    async def lease(self, worker_id: str, *, lease_s: float = 60.0) -> dict[str, Any] | None:
        if lease_s <= 0:
            raise ValueError("lease_s must be positive")
        return await self._run(self._lease_sync, worker_id, float(lease_s))

    def _lease_sync(self, worker_id: str, lease_s: float) -> dict[str, Any] | None:
        connection = self._conn()
        now = time.time()
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """UPDATE tasks SET state='queued', lease_owner=NULL, lease_expires_at=NULL, updated_at=?
                   WHERE state='leased' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?""",
                (now, now),
            )
            row = connection.execute("SELECT * FROM tasks WHERE state='queued' ORDER BY created_at, task_id LIMIT 1").fetchone()
            if row is None:
                connection.commit()
                return None
            connection.execute(
                """UPDATE tasks SET state='leased',lease_owner=?,lease_expires_at=?,heartbeat_at=?,attempts=attempts+1,updated_at=?
                   WHERE task_id=?""",
                (worker_id, now + lease_s, now, now, row["task_id"]),
            )
            connection.commit()
            return {
                "task_id": row["task_id"], "task_key": row["task_key"], "cycle_id": row["cycle_id"],
                "source_name": row["source_name"], "payload": json.loads(row["payload_json"]),
                "attempt": int(row["attempts"]) + 1, "lease_expires_at": now + lease_s,
            }
        except BaseException:
            connection.rollback()
            raise

    async def heartbeat(self, task_id: str, worker_id: str, *, lease_s: float = 60.0) -> bool:
        return bool(await self._run(self._heartbeat_sync, task_id, worker_id, float(lease_s)))

    def _heartbeat_sync(self, task_id: str, worker_id: str, lease_s: float) -> bool:
        connection = self._conn()
        now = time.time()
        cursor = connection.execute(
            """UPDATE tasks SET heartbeat_at=?,lease_expires_at=?,updated_at=?
               WHERE task_id=? AND state='leased' AND lease_owner=? AND lease_expires_at>?""",
            (now, now + lease_s, now, task_id, worker_id, now),
        )
        connection.commit()
        return cursor.rowcount == 1

    async def add_batch(self, task_id: str, worker_id: str, batch_id: str, observations: Sequence[ProductObservation | dict[str, Any]]) -> bool:
        return bool(await self._run(self._add_batch_sync, task_id, worker_id, batch_id, tuple(observations)))

    def _add_batch_sync(self, task_id: str, worker_id: str, batch_id: str, observations: Sequence[ProductObservation | dict[str, Any]]) -> bool:
        payload = [asdict(item) if isinstance(item, ProductObservation) else dict(item) for item in observations]
        payload_json = json.dumps(payload, separators=(",", ":"), default=str)
        connection = self._conn()
        row = connection.execute("SELECT state,lease_owner,lease_expires_at FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        now = time.time()
        if row is None or row["state"] != "leased" or row["lease_owner"] != worker_id or float(row["lease_expires_at"] or 0) <= now:
            raise PermissionError("worker does not hold task lease")
        cursor = connection.execute("INSERT OR IGNORE INTO batches(task_id,batch_id,payload_json,created_at) VALUES (?,?,?,?)", (task_id, batch_id, payload_json, now))
        connection.commit()
        return cursor.rowcount == 1

    async def complete(self, task_id: str, worker_id: str) -> bool:
        return bool(await self._run(self._complete_sync, task_id, worker_id))

    def _complete_sync(self, task_id: str, worker_id: str) -> bool:
        connection = self._conn()
        now = time.time()
        cursor = connection.execute(
            """UPDATE tasks SET state='completed',lease_owner=NULL,lease_expires_at=NULL,updated_at=?
               WHERE task_id=? AND state='leased' AND lease_owner=? AND lease_expires_at>?""",
            (now, task_id, worker_id, now),
        )
        connection.commit()
        return cursor.rowcount == 1

    async def fail(self, task_id: str, worker_id: str, error: str, *, requeue: bool = True) -> bool:
        return bool(await self._run(self._fail_sync, task_id, worker_id, error, bool(requeue)))

    def _fail_sync(self, task_id: str, worker_id: str, error: str, requeue: bool) -> bool:
        connection = self._conn()
        now = time.time()
        state = "queued" if requeue else "failed"
        cursor = connection.execute(
            """UPDATE tasks SET state=?,error=?,lease_owner=NULL,lease_expires_at=NULL,updated_at=?
               WHERE task_id=? AND state='leased' AND lease_owner=? AND lease_expires_at>?""",
            (state, error[:2000], now, task_id, worker_id, now),
        )
        connection.commit()
        return cursor.rowcount == 1

    async def cycle_status(self, cycle_id: str) -> dict[str, Any]:
        return await self._run(self._cycle_status_sync, cycle_id)

    def _cycle_status_sync(self, cycle_id: str) -> dict[str, Any]:
        rows = self._conn().execute("SELECT state,COUNT(*) n FROM tasks WHERE cycle_id=? GROUP BY state", (cycle_id,)).fetchall()
        counts = {row["state"]: int(row["n"]) for row in rows}
        total = sum(counts.values())
        terminal = counts.get("completed", 0) + counts.get("failed", 0)
        return {"cycle_id": cycle_id, "counts": counts, "total": total, "terminal": terminal, "done": total > 0 and terminal == total}

    async def cycle_results(self, cycle_id: str) -> list[dict[str, Any]]:
        return await self._run(self._cycle_results_sync, cycle_id)

    def _cycle_results_sync(self, cycle_id: str) -> list[dict[str, Any]]:
        rows = self._conn().execute(
            """SELECT t.task_id,t.source_name,t.state,t.error,b.batch_id,b.payload_json
               FROM tasks t LEFT JOIN batches b ON b.task_id=t.task_id
               WHERE t.cycle_id=? ORDER BY t.source_name,b.created_at,b.batch_id""",
            (cycle_id,),
        ).fetchall()
        return [{
            "task_id": row["task_id"], "source_name": row["source_name"], "state": row["state"],
            "error": row["error"] or "", "batch_id": row["batch_id"],
            "observations": [] if row["payload_json"] is None else json.loads(row["payload_json"]),
        } for row in rows]


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), default=str).encode("utf-8")


def _decode_json_bytes(value: bytes) -> Any:
    return json.loads(value.decode("utf-8"))


class CoordinatorHttpServer:
    def __init__(self, store: DistributedTaskStore, *, host: str = "127.0.0.1", port: int = 8788) -> None:
        self.store = store
        self.host = host
        self.port = port
        self.runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application(client_max_size=64 * 1024 * 1024)
        app.add_routes([
            web.get("/healthz", self._health), web.get("/readyz", self._health),
            web.post("/v1/cycles", self._cycles), web.get("/v1/cycles/{cycle_id}", self._cycle),
            web.get("/v1/cycles/{cycle_id}/results", self._results), web.post("/v1/tasks/lease", self._lease),
            web.post("/v1/tasks/{task_id}/heartbeat", self._heartbeat), web.post("/v1/tasks/{task_id}/batches", self._batch),
            web.post("/v1/tasks/{task_id}/complete", self._complete), web.post("/v1/tasks/{task_id}/fail", self._fail),
        ])
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, self.host, self.port).start()

    async def close(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None

    async def _json(self, request: web.Request) -> dict[str, Any]:
        value = await asyncio.to_thread(_decode_json_bytes, await request.read())
        if not isinstance(value, dict):
            raise web.HTTPBadRequest(text="JSON object required")
        return value

    async def _response(self, value: Any, *, status: int = 200) -> web.Response:
        return web.Response(body=await asyncio.to_thread(_json_bytes, value), status=status, content_type="application/json")

    async def _health(self, _: web.Request) -> web.Response:
        return await self._response({"ok": True})
    async def _cycles(self, request: web.Request) -> web.Response:
        payload = await self._json(request)
        return await self._response(await self.store.submit_cycle(payload.get("sources", []), cycle_id=payload.get("cycle_id")))
    async def _cycle(self, request: web.Request) -> web.Response:
        return await self._response(await self.store.cycle_status(request.match_info["cycle_id"]))
    async def _results(self, request: web.Request) -> web.Response:
        return await self._response({"results": await self.store.cycle_results(request.match_info["cycle_id"])})
    async def _lease(self, request: web.Request) -> web.Response:
        payload = await self._json(request)
        return await self._response({"task": await self.store.lease(str(payload["worker_id"]), lease_s=float(payload.get("lease_s", 60)))})
    async def _heartbeat(self, request: web.Request) -> web.Response:
        payload = await self._json(request)
        ok = await self.store.heartbeat(request.match_info["task_id"], str(payload["worker_id"]), lease_s=float(payload.get("lease_s", 60)))
        return await self._response({"ok": ok}, status=200 if ok else 409)
    async def _batch(self, request: web.Request) -> web.Response:
        payload = await self._json(request)
        try:
            inserted = await self.store.add_batch(request.match_info["task_id"], str(payload["worker_id"]), str(payload["batch_id"]), payload.get("observations", []))
        except PermissionError as exc:
            return await self._response({"error": str(exc)}, status=409)
        return await self._response({"inserted": inserted})
    async def _complete(self, request: web.Request) -> web.Response:
        payload = await self._json(request)
        ok = await self.store.complete(request.match_info["task_id"], str(payload["worker_id"]))
        return await self._response({"ok": ok}, status=200 if ok else 409)
    async def _fail(self, request: web.Request) -> web.Response:
        payload = await self._json(request)
        ok = await self.store.fail(request.match_info["task_id"], str(payload["worker_id"]), str(payload.get("error", "")), requeue=bool(payload.get("requeue", True)))
        return await self._response({"ok": ok}, status=200 if ok else 409)


class CoordinatorClient:
    def __init__(self, base_url: str, session: ClientSession | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session
        self._owned = False

    async def __aenter__(self) -> "CoordinatorClient":
        if self.session is None:
            self.session = ClientSession()
            self._owned = True
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owned and self.session is not None:
            await self.session.close()

    async def _decode(self, response: Any) -> Any:
        return await asyncio.to_thread(_decode_json_bytes, await response.read())

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.session is not None
        body = await asyncio.to_thread(_json_bytes, payload)
        async with self.session.post(self.base_url + path, data=body, headers={"Content-Type": "application/json"}) as response:
            response.raise_for_status()
            value = await self._decode(response)
            if not isinstance(value, dict):
                raise RuntimeError("coordinator returned non-object JSON")
            return value

    async def submit_cycle(self, sources: Sequence[dict[str, Any]], cycle_id: str | None = None) -> dict[str, Any]:
        return await self._post("/v1/cycles", {"sources": list(sources), "cycle_id": cycle_id})
    async def cycle_status(self, cycle_id: str) -> dict[str, Any]:
        assert self.session is not None
        async with self.session.get(self.base_url + f"/v1/cycles/{cycle_id}") as response:
            response.raise_for_status()
            value = await self._decode(response)
            return value if isinstance(value, dict) else {}
    async def cycle_results(self, cycle_id: str) -> list[dict[str, Any]]:
        assert self.session is not None
        async with self.session.get(self.base_url + f"/v1/cycles/{cycle_id}/results") as response:
            response.raise_for_status()
            value = await self._decode(response)
            return list(value.get("results", [])) if isinstance(value, dict) else []
    async def lease(self, worker_id: str, lease_s: float) -> dict[str, Any] | None:
        return (await self._post("/v1/tasks/lease", {"worker_id": worker_id, "lease_s": lease_s})).get("task")
    async def heartbeat(self, task_id: str, worker_id: str, lease_s: float) -> None:
        await self._post(f"/v1/tasks/{task_id}/heartbeat", {"worker_id": worker_id, "lease_s": lease_s})
    async def batch(self, task_id: str, worker_id: str, batch_id: str, observations: Sequence[ProductObservation]) -> bool:
        payload = await asyncio.to_thread(lambda: {"worker_id": worker_id, "batch_id": batch_id, "observations": [asdict(item) for item in observations]})
        return bool((await self._post(f"/v1/tasks/{task_id}/batches", payload)).get("inserted"))
    async def complete(self, task_id: str, worker_id: str) -> None:
        await self._post(f"/v1/tasks/{task_id}/complete", {"worker_id": worker_id})
    async def fail(self, task_id: str, worker_id: str, error: str, requeue: bool = True) -> None:
        await self._post(f"/v1/tasks/{task_id}/fail", {"worker_id": worker_id, "error": error, "requeue": requeue})


BatchExecutor = Callable[[dict[str, Any]], AsyncIterator[Sequence[ProductObservation]]]


class DistributedWorker:
    def __init__(self, client: CoordinatorClient, worker_id: str, executor: BatchExecutor, *, lease_s: float = 60, heartbeat_s: float = 20, poll_s: float = 2, max_attempts: int = 5) -> None:
        if heartbeat_s <= 0 or lease_s <= heartbeat_s:
            raise ValueError("lease_s must exceed heartbeat_s")
        self.client = client
        self.worker_id = worker_id
        self.executor = executor
        self.lease_s = lease_s
        self.heartbeat_s = heartbeat_s
        self.poll_s = poll_s
        self.max_attempts = max_attempts

    async def run_one(self) -> bool:
        task = await self.client.lease(self.worker_id, self.lease_s)
        if task is None:
            return False
        stop = asyncio.Event()
        lease_lost = asyncio.Event()
        heartbeat_error: list[str] = []

        async def heartbeat() -> None:
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self.heartbeat_s)
                    return
                except TimeoutError:
                    try:
                        await self.client.heartbeat(task["task_id"], self.worker_id, self.lease_s)
                    except Exception as exc:
                        heartbeat_error.append(f"{type(exc).__name__}: {exc}")
                        lease_lost.set()
                        return

        heartbeat_task = asyncio.create_task(heartbeat())
        try:
            index = 0
            async for batch in self.executor(task["payload"]):
                if lease_lost.is_set():
                    raise RuntimeError(f"task lease heartbeat failed: {heartbeat_error[-1]}")
                batch_id = f"{task['task_key']}:{index:08d}"
                await self.client.batch(task["task_id"], self.worker_id, batch_id, batch)
                index += 1
            if lease_lost.is_set():
                raise RuntimeError(f"task lease heartbeat failed: {heartbeat_error[-1]}")
            await self.client.complete(task["task_id"], self.worker_id)
            return True
        except Exception as exc:
            try:
                await self.client.fail(task["task_id"], self.worker_id, f"{type(exc).__name__}: {exc}", requeue=int(task.get("attempt", 1)) < self.max_attempts)
            except Exception:
                pass
            return True
        finally:
            stop.set()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
