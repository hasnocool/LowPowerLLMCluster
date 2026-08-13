from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Mapping


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_bytes(path, _json_bytes(value) + b"\n")


@dataclass(frozen=True, slots=True)
class ContentRef:
    sha256: str
    size: int


class ContentAddressedStore:
    """Immutable SHA-256 blobs plus per-URL atomic snapshot indexes.

    Blobs never mutate. Each URL index is a separate atomic file, so workers writing
    unrelated URLs do not race through one global mutable index document.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.blob_root = self.root / "blobs" / "sha256"
        self.url_index_root = self.root / "indexes" / "url"

    async def initialize(self) -> None:
        await asyncio.to_thread(self.blob_root.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self.url_index_root.mkdir, parents=True, exist_ok=True)

    def blob_path(self, sha256: str) -> Path:
        if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256.lower()):
            raise ValueError("invalid sha256")
        digest = sha256.lower()
        return self.blob_root / digest[:2] / digest[2:]

    def source_index_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.url_index_root / digest[:2] / f"{digest[2:]}.json"

    async def put(self, payload: bytes) -> ContentRef:
        digest = hashlib.sha256(payload).hexdigest()
        path = self.blob_path(digest)
        if not await asyncio.to_thread(path.exists):
            await asyncio.to_thread(_atomic_bytes, path, payload)
        return ContentRef(digest, len(payload))

    async def put_json(self, value: Any) -> ContentRef:
        payload = await asyncio.to_thread(_json_bytes, value)
        return await self.put(payload)

    async def get(self, sha256: str) -> bytes:
        return await asyncio.to_thread(self.blob_path(sha256).read_bytes)

    async def get_json(self, sha256: str) -> Any:
        payload = await self.get(sha256)
        return await asyncio.to_thread(json.loads, payload.decode("utf-8"))

    async def iter_bytes(self, sha256: str, *, chunk_size: int = 64 * 1024) -> AsyncIterator[bytes]:
        path = self.blob_path(sha256)
        handle = await asyncio.to_thread(path.open, "rb")
        try:
            while True:
                chunk = await asyncio.to_thread(handle.read, chunk_size)
                if not chunk: break
                yield chunk
        finally:
            await asyncio.to_thread(handle.close)

    async def note_source_snapshot(self, url: str, ref: ContentRef, *, headers: Mapping[str, str] | None = None, observed_at: float | None = None) -> None:
        entry = {
            "url": str(url), "sha256": ref.sha256, "size": ref.size,
            "observed_at": float(time.time() if observed_at is None else observed_at),
            "etag": str((headers or {}).get("etag", "")),
            "last_modified": str((headers or {}).get("last-modified", "")),
        }
        await asyncio.to_thread(_atomic_json, self.source_index_path(str(url)), entry)

    async def source_snapshot(self, url: str, *, max_age_s: float | None = None) -> dict[str, Any] | None:
        index_path = self.source_index_path(str(url))
        if not await asyncio.to_thread(index_path.exists):
            return None
        try:
            entry = await asyncio.to_thread(_read_json, index_path)
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(entry, dict) or entry.get("url") != str(url):
            return None
        if max_age_s is not None and time.time() - float(entry.get("observed_at", 0)) > max_age_s:
            return None
        if not await asyncio.to_thread(self.blob_path(str(entry["sha256"])).exists):
            return None
        return dict(entry)

    async def referenced_source_hashes(self) -> set[str]:
        if not await asyncio.to_thread(self.url_index_root.exists):
            return set()
        paths = await asyncio.to_thread(lambda: [p for p in self.url_index_root.glob("*/*.json") if p.is_file()])
        result: set[str] = set()
        for path in paths:
            try:
                entry = await asyncio.to_thread(_read_json, path)
            except (OSError, ValueError, TypeError):
                continue
            if isinstance(entry, dict) and entry.get("sha256"):
                result.add(str(entry["sha256"]))
        return result

    async def gc(self, *, referenced: set[str], grace_s: float = 86400.0) -> dict[str, int]:
        now = time.time(); removed = kept = 0
        if not await asyncio.to_thread(self.blob_root.exists):
            return {"removed": 0, "kept": 0}
        paths = await asyncio.to_thread(lambda: [p for p in self.blob_root.glob("*/*") if p.is_file()])
        for path in paths:
            digest = path.parent.name + path.name
            if digest in referenced:
                kept += 1; continue
            stat = await asyncio.to_thread(path.stat)
            if now - stat.st_mtime < grace_s:
                kept += 1; continue
            await asyncio.to_thread(path.unlink); removed += 1
        return {"removed": removed, "kept": kept}
