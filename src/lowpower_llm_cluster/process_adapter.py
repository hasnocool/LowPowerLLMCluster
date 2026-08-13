from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Sequence

from .discovery import ProductObservation
from .resilience_runtime import AdaptiveBatchSizer


def _encode_config(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, separators=(",", ":")) + "\n").encode()


@dataclass(slots=True)
class ProcessAdapter:
    """Isolated third-party adapter protocol over JSON stdin / JSONL stdout."""
    name: str
    command: Sequence[str]
    source_config: dict[str, Any]
    timeout_s: float = 120.0
    batch_size: int = 256
    max_line_bytes: int = 2 * 1024 * 1024
    batch_sizer: AdaptiveBatchSizer | None = None

    async def discover_batches(self) -> AsyncIterator[Sequence[ProductObservation]]:
        if not self.command or self.timeout_s <= 0 or self.batch_size < 1 or self.max_line_bytes < 1024:
            raise ValueError("invalid process adapter configuration")
        proc = await asyncio.create_subprocess_exec(*self.command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
        config_line = await asyncio.to_thread(_encode_config, self.source_config)
        proc.stdin.write(config_line)
        await proc.stdin.drain()
        proc.stdin.close()
        batch: list[ProductObservation] = []
        output: asyncio.Queue[Sequence[ProductObservation] | BaseException | None] = asyncio.Queue(maxsize=4)

        async def read_all() -> None:
            nonlocal batch
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                if len(line) > self.max_line_bytes:
                    raise ValueError("process adapter emitted an oversized JSONL line")
                raw = await asyncio.to_thread(json.loads, line)
                values = raw.get("observations", []) if isinstance(raw, dict) and "observations" in raw else [raw]
                for item in values:
                    observation = ProductObservation(**item)
                    if observation.source != self.name:
                        observation = ProductObservation(**{**item, "source": self.name})
                    batch.append(observation)
                    target = self.batch_sizer.current if self.batch_sizer else self.batch_size
                    if len(batch) >= target:
                        await output.put(tuple(batch))
                        batch = []
            if batch:
                await output.put(tuple(batch))
                batch = []

        async def pump() -> None:
            try:
                await read_all()
                code = await proc.wait()
                if code != 0:
                    stderr = (await proc.stderr.read(64 * 1024)).decode("utf-8", "replace")
                    raise RuntimeError(f"process adapter exited {code}: {stderr.strip()}")
            except BaseException as exc:
                await output.put(exc)
            finally:
                await output.put(None)

        task = asyncio.create_task(pump())
        try:
            async with asyncio.timeout(self.timeout_s):
                while True:
                    value = await output.get()
                    if value is None:
                        break
                    if isinstance(value, BaseException):
                        raise value
                    yield value
            await task
        except BaseException:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def discover(self) -> Sequence[ProductObservation]:
        result: list[ProductObservation] = []
        async for batch in self.discover_batches():
            result.extend(batch)
        return result
