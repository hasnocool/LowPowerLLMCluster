from __future__ import annotations

from typing import Any, Mapping

from .content_store import ContentAddressedStore
from .http_runtime import AdaptiveConcurrency, AsyncHttpClient, HttpResponse


class SnapshottingHttpClient(AsyncHttpClient):
    """Async HTTP client that records immutable successful response bodies in CAS.

    Snapshot reuse is explicit and freshness-bounded. It is intended for shared worker
    filesystems and does not silently replace live network requests.
    """

    def __init__(self, *args: Any, snapshot_store: ContentAddressedStore | None = None, snapshot_max_age_s: float | None = None, prefer_snapshot: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.snapshot_store = snapshot_store
        self.snapshot_max_age_s = snapshot_max_age_s
        self.prefer_snapshot = prefer_snapshot
        self._snapshot_hits = 0
        self._snapshot_writes = 0

    async def start(self) -> None:
        await super().start()
        if self.snapshot_store is not None:
            await self.snapshot_store.initialize()

    async def get_response(self, url: str, *, validators: Mapping[str, str] | None = None, source: str = "", adaptive: AdaptiveConcurrency | None = None) -> HttpResponse:
        if self.snapshot_store is not None and self.prefer_snapshot:
            entry = await self.snapshot_store.source_snapshot(url, max_age_s=self.snapshot_max_age_s)
            if entry is not None:
                payload = await self.snapshot_store.get(str(entry["sha256"]))
                self._snapshot_hits += 1
                return HttpResponse(200, payload, {
                    "etag": str(entry.get("etag", "")),
                    "last-modified": str(entry.get("last_modified", "")),
                    "x-lpllm-snapshot": "1",
                }, 0, 0.0, False)
        response = await super().get_response(url, validators=validators, source=source, adaptive=adaptive)
        if self.snapshot_store is not None and response.status == 200 and response.payload:
            ref = await self.snapshot_store.put(response.payload)
            await self.snapshot_store.note_source_snapshot(url, ref, headers=response.headers)
            self._snapshot_writes += 1
        return response

    def metrics(self) -> dict[str, Any]:
        result = super().metrics()
        result["source_snapshots"] = {"hits": self._snapshot_hits, "writes": self._snapshot_writes, "enabled": self.snapshot_store is not None}
        return result
