from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any, AsyncIterator, Mapping, Sequence

from aiohttp import ClientSession, TCPConnector

from .discovery import ProductObservation
from .distributed_security import signed_worker_headers
from .secure_store import _decode_json_bytes, _json_bytes

class SecureCoordinatorClient:
    def __init__(
        self, base_url: str, *, admin_token: str | None = None, worker_id: str | None = None,
        worker_secret: str | None = None, ssl_context: Any = None, session: ClientSession | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_token, self.worker_id, self.worker_secret = admin_token, worker_id, worker_secret
        self.ssl_context, self._session, self._owned = ssl_context, session, session is None

    async def __aenter__(self) -> "SecureCoordinatorClient":
        if self._session is None:
            self._session = ClientSession(connector=TCPConnector(ssl=self.ssl_context))
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owned and self._session is not None:
            await self._session.close()
            self._session = None

    def _session_required(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("secure coordinator client not started")
        return self._session

    def _admin_headers(self) -> dict[str, str]:
        if not self.admin_token:
            raise RuntimeError("admin token required")
        return {"Authorization": f"Bearer {self.admin_token}"}

    async def _json_request(self, method: str, path: str, payload: Mapping[str, Any] | None = None, *, worker: bool = False, admin: bool = False, allow_conflict: bool = False) -> dict[str, Any]:
        body = b"" if payload is None else await asyncio.to_thread(_json_bytes, dict(payload))
        headers = {"Content-Type": "application/json"} if body else {}
        if admin:
            headers.update(self._admin_headers())
        if worker:
            if not self.worker_id or not self.worker_secret:
                raise RuntimeError("worker identity and secret required")
            headers.update(signed_worker_headers(self.worker_id, self.worker_secret, method=method, path_qs=path, body=body))
        async with self._session_required().request(method, self.base_url + path, data=body if body else None, headers=headers) as response:
            raw = await response.read()
            if response.status >= 400 and not (allow_conflict and response.status == 409):
                raise RuntimeError(f"coordinator {method} {path} failed {response.status}: {raw[:500]!r}")
            value = await asyncio.to_thread(_decode_json_bytes, raw or b"{}")
            return dict(value)

    async def submit_cycle(self, sources: Sequence[dict[str, Any]], cycle_id: str | None = None) -> dict[str, Any]:
        return await self._json_request("POST", "/v2/cycles", {"sources": list(sources), "cycle_id": cycle_id}, admin=True)

    async def cycle_status(self, cycle_id: str) -> dict[str, Any]:
        return await self._json_request("GET", f"/v2/cycles/{cycle_id}", admin=True)

    async def cancel_cycle(self, cycle_id: str) -> bool:
        return bool((await self._json_request("POST", f"/v2/cycles/{cycle_id}/cancel", {}, admin=True)).get("ok"))

    async def workers(self) -> list[dict[str, Any]]:
        return list((await self._json_request("GET", "/v2/workers", admin=True)).get("workers", ()))

    async def set_drain(self, worker_id: str, draining: bool) -> bool:
        verb = "drain" if draining else "undrain"
        return bool((await self._json_request("POST", f"/v2/workers/{worker_id}/{verb}", {}, admin=True)).get("ok"))

    async def backup(self, destination: str) -> dict[str, Any]:
        return await self._json_request("POST", "/v2/backup", {"destination": destination}, admin=True)

    async def register(self, *, capabilities: Sequence[str], labels: Mapping[str, str], resources: Mapping[str, Any]) -> dict[str, Any]:
        return await self._json_request("POST", "/v2/workers/register", {"capabilities": list(capabilities), "labels": dict(labels), "resources": dict(resources)}, worker=True)

    async def self_drain(self) -> bool:
        return bool((await self._json_request("POST", "/v2/workers/self/drain", {}, worker=True)).get("ok"))

    async def lease(self, *, lease_s: float, capabilities: Sequence[str], labels: Mapping[str, str], resources: Mapping[str, Any], work_steal_after_s: float = 60.0) -> dict[str, Any] | None:
        response = await self._json_request("POST", "/v2/tasks/lease", {"lease_s": lease_s, "capabilities": list(capabilities), "labels": dict(labels), "resources": dict(resources), "work_steal_after_s": work_steal_after_s}, worker=True)
        return response.get("task")

    async def heartbeat(self, task_id: str, *, epoch: int, lease_s: float, resources: Mapping[str, Any]) -> bool:
        response = await self._json_request("POST", f"/v2/tasks/{task_id}/heartbeat", {"epoch": epoch, "lease_s": lease_s, "resources": dict(resources)}, worker=True, allow_conflict=True)
        return bool(response.get("ok"))

    async def add_batch(self, task_id: str, *, epoch: int, batch_id: str, observations: Sequence[ProductObservation | dict[str, Any]]) -> bool:
        values = [asdict(item) if isinstance(item, ProductObservation) else dict(item) for item in observations]
        response = await self._json_request("POST", f"/v2/tasks/{task_id}/batches", {"epoch": epoch, "batch_id": batch_id, "observations": values}, worker=True, allow_conflict=True)
        return bool(response.get("inserted"))

    async def complete(self, task_id: str, *, epoch: int) -> bool:
        response = await self._json_request("POST", f"/v2/tasks/{task_id}/complete", {"epoch": epoch}, worker=True, allow_conflict=True)
        return bool(response.get("ok"))

    async def fail(self, task_id: str, *, epoch: int, error: str, requeue: bool = True) -> bool:
        response = await self._json_request("POST", f"/v2/tasks/{task_id}/fail", {"epoch": epoch, "error": error, "requeue": requeue}, worker=True, allow_conflict=True)
        return bool(response.get("ok"))

    async def iter_cycle_results(self, cycle_id: str) -> AsyncIterator[dict[str, Any]]:
        path = f"/v2/cycles/{cycle_id}/results.ndjson"
        async with self._session_required().get(self.base_url + path, headers=self._admin_headers()) as response:
            response.raise_for_status()
            buffer = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                buffer.extend(chunk)
                while b"\n" in buffer:
                    line, _, rest = buffer.partition(b"\n")
                    buffer = bytearray(rest)
                    if line:
                        value = await asyncio.to_thread(_decode_json_bytes, bytes(line))
                        yield dict(value)
            if buffer:
                value = await asyncio.to_thread(_decode_json_bytes, bytes(buffer))
                yield dict(value)
