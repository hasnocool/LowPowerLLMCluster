from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class EventJournal:
    """Append-only JSONL event journal with lightweight async tailing support."""

    def __init__(self, path: str | Path = "results/events.jsonl", *, max_bytes: int = 8 * 1024 * 1024) -> None:
        self.path = Path(path).expanduser().resolve()
        self.max_bytes = max_bytes
        self._lock = asyncio.Lock()
        self._sequence = 0

    async def emit(self, event: str, **fields: Any) -> dict[str, Any]:
        async with self._lock:
            self._sequence += 1
            payload = {"seq": self._sequence, "ts": datetime.now(UTC).isoformat(), "event": event, **fields}
            await asyncio.to_thread(self._append_sync, payload)
            return payload

    def _append_sync(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size >= self.max_bytes:
            rotated = self.path.with_suffix(self.path.suffix + ".1")
            rotated.unlink(missing_ok=True)
            self.path.replace(rotated)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")

    async def tail(self, limit: int = 200) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        return await asyncio.to_thread(self._tail_sync, limit)

    def _tail_sync(self, limit: int) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows

    async def follow(self, *, poll_s: float = 0.25, start_at_end: bool = True) -> AsyncIterator[dict[str, Any]]:
        offset = self.path.stat().st_size if start_at_end and self.path.exists() else 0
        while True:
            if not self.path.exists():
                await asyncio.sleep(poll_s)
                continue
            size = self.path.stat().st_size
            if size < offset:
                offset = 0
            if size == offset:
                await asyncio.sleep(poll_s)
                continue
            chunk, offset = await asyncio.to_thread(self._read_from, offset)
            for line in chunk.splitlines():
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    yield payload

    def _read_from(self, offset: int) -> tuple[str, int]:
        with self.path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(offset)
            chunk = handle.read()
            return chunk, handle.tell()
