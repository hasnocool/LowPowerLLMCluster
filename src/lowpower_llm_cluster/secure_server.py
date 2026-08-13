from __future__ import annotations

import asyncio
import time
from typing import Any

from aiohttp import web

from .distributed_security import AuthRegistry, ReplayWindow, verify_worker_request
from .secure_store import LeaderState, SecureDistributedStore, _decode_json_bytes, _json_bytes

class SecureCoordinatorServer:
    def __init__(
        self, store: SecureDistributedStore, auth: AuthRegistry, *, host: str = "127.0.0.1", port: int = 8788,
        node_id: str = "coordinator", leader_lease_s: float = 10.0, standby: bool = False, ssl_context: Any = None,
    ) -> None:
        self.store, self.auth = store, auth
        self.host, self.port, self.node_id = host, port, node_id
        self.leader_lease_s, self.standby, self.ssl_context = leader_lease_s, standby, ssl_context
        self.replay = ReplayWindow()
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self._leadership_task: asyncio.Task[None] | None = None
        self._leader = LeaderState(None, 0, 0)
        self._stopping = asyncio.Event()

    @property
    def epoch(self) -> int:
        return self._leader.epoch

    @property
    def active(self) -> bool:
        return self._leader.leader_id == self.node_id and self._leader.lease_expires_at > time.time()

    async def start(self) -> None:
        self._leader = await self.store.acquire_leader(self.node_id, lease_s=self.leader_lease_s)
        if not self.active and not self.standby:
            raise RuntimeError(f"coordinator leadership held by {self._leader.leader_id!r}")
        app = web.Application(client_max_size=16 * 1024 * 1024)
        app.add_routes([
            web.get("/healthz", self._health), web.get("/readyz", self._ready),
            web.post("/v2/cycles", self._cycles), web.get("/v2/cycles/{cycle_id}", self._cycle),
            web.get("/v2/cycles/{cycle_id}/results.ndjson", self._results_stream),
            web.post("/v2/cycles/{cycle_id}/cancel", self._cancel_cycle),
            web.get("/v2/workers", self._workers), web.post("/v2/workers/{worker_id}/drain", self._drain),
            web.post("/v2/workers/{worker_id}/undrain", self._undrain), web.post("/v2/backup", self._backup),
            web.post("/v2/workers/register", self._register), web.post("/v2/workers/self/drain", self._self_drain), web.post("/v2/tasks/lease", self._lease),
            web.post("/v2/tasks/{task_id}/heartbeat", self._heartbeat), web.post("/v2/tasks/{task_id}/batches", self._batch),
            web.post("/v2/tasks/{task_id}/complete", self._complete), web.post("/v2/tasks/{task_id}/fail", self._fail),
        ])
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port, ssl_context=self.ssl_context)
        await self.site.start()
        if self.port == 0 and self.site._server is not None and self.site._server.sockets:  # type: ignore[attr-defined]
            self.port = int(self.site._server.sockets[0].getsockname()[1])  # type: ignore[attr-defined]
        self._leadership_task = asyncio.create_task(self._leadership_loop())

    async def close(self) -> None:
        self._stopping.set()
        if self._leadership_task is not None:
            self._leadership_task.cancel()
            await asyncio.gather(self._leadership_task, return_exceptions=True)
            self._leadership_task = None
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None
            self.site = None

    async def _leadership_loop(self) -> None:
        delay = max(1.0, self.leader_lease_s / 3.0)
        while not self._stopping.is_set():
            try:
                self._leader = await self.store.acquire_leader(self.node_id, lease_s=self.leader_lease_s)
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=delay)
            except TimeoutError:
                pass

    async def _json_response(self, value: Any, *, status: int = 200) -> web.Response:
        body = await asyncio.to_thread(_json_bytes, value)
        return web.Response(body=body, status=status, content_type="application/json")

    async def _json_body(self, request: web.Request) -> tuple[bytes, dict[str, Any]]:
        body = await request.read()
        value = await asyncio.to_thread(_decode_json_bytes, body or b"{}")
        if not isinstance(value, dict):
            raise web.HTTPBadRequest(text="JSON object required")
        return body, value

    def _admin(self, request: web.Request) -> None:
        authorization = request.headers.get("Authorization", "")
        token = authorization[7:] if authorization.startswith("Bearer ") else ""
        if not self.auth.admin_ok(token):
            raise web.HTTPUnauthorized(text="admin bearer token required")

    async def _worker(self, request: web.Request) -> tuple[str, dict[str, Any]]:
        body, value = await self._json_body(request)
        try:
            credential = verify_worker_request(
                self.auth, self.replay, method=request.method, path_qs=request.rel_url.raw_path_qs, body=body, headers=request.headers
            )
        except PermissionError as exc:
            raise web.HTTPUnauthorized(text=str(exc)) from exc
        return credential.worker_id, value

    def _require_active(self) -> None:
        if not self.active:
            raise web.HTTPServiceUnavailable(text="standby coordinator is not active leader")

    async def _health(self, _: web.Request) -> web.Response:
        return await self._json_response({"ok": True, "node_id": self.node_id, "active": self.active, "epoch": self.epoch})

    async def _ready(self, _: web.Request) -> web.Response:
        return await self._json_response({"ready": self.active, "node_id": self.node_id, "epoch": self.epoch}, status=200 if self.active else 503)

    async def _cycles(self, request: web.Request) -> web.Response:
        self._admin(request); self._require_active()
        _, payload = await self._json_body(request)
        return await self._json_response(await self.store.submit_cycle(payload.get("sources", ()), cycle_id=payload.get("cycle_id")))

    async def _cycle(self, request: web.Request) -> web.Response:
        self._admin(request)
        return await self._json_response(await self.store.cycle_status(request.match_info["cycle_id"]))

    async def _results_stream(self, request: web.Request) -> web.StreamResponse:
        self._admin(request)
        response = web.StreamResponse(status=200, headers={"Content-Type": "application/x-ndjson"})
        await response.prepare(request)
        refs = await self.store.result_refs(request.match_info["cycle_id"])
        for ref in refs:
            header = {key: ref[key] for key in ("task_id", "source_name", "state", "error", "batch_id", "sha256", "observation_count", "byte_count")}
            if ref.get("sha256"):
                observations = await self.store.artifacts.get_json(str(ref["sha256"]))
            else:
                observations = []
            line = await asyncio.to_thread(_json_bytes, {**header, "observations": observations})
            await response.write(line + b"\n")
        await response.write_eof()
        return response

    async def _cancel_cycle(self, request: web.Request) -> web.Response:
        self._admin(request); self._require_active()
        ok = await self.store.cancel_cycle(request.match_info["cycle_id"])
        return await self._json_response({"ok": ok}, status=200 if ok else 404)

    async def _workers(self, request: web.Request) -> web.Response:
        self._admin(request)
        return await self._json_response({"workers": await self.store.list_workers()})

    async def _drain(self, request: web.Request) -> web.Response:
        self._admin(request); self._require_active()
        ok = await self.store.set_worker_state(request.match_info["worker_id"], "draining")
        return await self._json_response({"ok": ok}, status=200 if ok else 404)

    async def _undrain(self, request: web.Request) -> web.Response:
        self._admin(request); self._require_active()
        ok = await self.store.set_worker_state(request.match_info["worker_id"], "active")
        return await self._json_response({"ok": ok}, status=200 if ok else 404)

    async def _backup(self, request: web.Request) -> web.Response:
        self._admin(request); self._require_active()
        _, payload = await self._json_body(request)
        destination = str(payload.get("destination", ""))
        if not destination:
            raise web.HTTPBadRequest(text="destination is required")
        path = await self.store.backup(destination)
        return await self._json_response({"path": str(path), "epoch": self.epoch})

    async def _register(self, request: web.Request) -> web.Response:
        worker_id, payload = await self._worker(request); self._require_active()
        result = await self.store.register_worker(worker_id, capabilities=payload.get("capabilities", ()), labels=payload.get("labels", {}), resources=payload.get("resources", {}))
        return await self._json_response({**result, "epoch": self.epoch})

    async def _self_drain(self, request: web.Request) -> web.Response:
        worker_id, _ = await self._worker(request); self._require_active()
        ok = await self.store.set_worker_state(worker_id, "draining")
        return await self._json_response({"ok": ok}, status=200 if ok else 404)

    async def _lease(self, request: web.Request) -> web.Response:
        worker_id, payload = await self._worker(request); self._require_active()
        task = await self.store.lease(
            worker_id, epoch=self.epoch, lease_s=float(payload.get("lease_s", 60)), capabilities=payload.get("capabilities", ()),
            labels=payload.get("labels", {}), resources=payload.get("resources", {}), work_steal_after_s=float(payload.get("work_steal_after_s", 60)),
        )
        return await self._json_response({"task": task, "epoch": self.epoch})

    async def _heartbeat(self, request: web.Request) -> web.Response:
        worker_id, payload = await self._worker(request); self._require_active()
        ok = await self.store.heartbeat(request.match_info["task_id"], worker_id, epoch=int(payload["epoch"]), lease_s=float(payload.get("lease_s", 60)), resources=payload.get("resources", {}))
        return await self._json_response({"ok": ok, "epoch": self.epoch}, status=200 if ok else 409)

    async def _batch(self, request: web.Request) -> web.Response:
        worker_id, payload = await self._worker(request); self._require_active()
        try:
            inserted = await self.store.add_batch(request.match_info["task_id"], worker_id, str(payload["batch_id"]), payload.get("observations", ()), epoch=int(payload["epoch"]))
        except PermissionError as exc:
            return await self._json_response({"error": str(exc), "epoch": self.epoch}, status=409)
        return await self._json_response({"inserted": inserted, "epoch": self.epoch})

    async def _complete(self, request: web.Request) -> web.Response:
        worker_id, payload = await self._worker(request); self._require_active()
        ok = await self.store.complete(request.match_info["task_id"], worker_id, epoch=int(payload["epoch"]))
        return await self._json_response({"ok": ok, "epoch": self.epoch}, status=200 if ok else 409)

    async def _fail(self, request: web.Request) -> web.Response:
        worker_id, payload = await self._worker(request); self._require_active()
        ok = await self.store.fail(
            request.match_info["task_id"], worker_id, str(payload.get("error", "")), epoch=int(payload["epoch"]),
            requeue=bool(payload.get("requeue", True)), quarantine_after=int(payload.get("quarantine_after", 3)), quarantine_s=float(payload.get("quarantine_s", 300)),
        )
        return await self._json_response({"ok": ok, "epoch": self.epoch}, status=200 if ok else 409)
